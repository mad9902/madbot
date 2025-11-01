import discord
from discord.ext import commands
import google.generativeai as genai
import os
import requests
import uuid
import json
import asyncio
import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
from dotenv import load_dotenv

load_dotenv()

# ===== Model untuk SplitBill =====
@dataclass
class Item:
    id: int
    name: str
    qty: int
    unit_price: int

@dataclass
class BillState:
    id: int
    thread_id: int
    created_by: int
    currency: str = "IDR"
    items: List[Item] = field(default_factory=list)
    taxes: Dict[str, int] = field(default_factory=lambda: {"tax": 0, "service": 0, "tips": 0})
    participants: Dict[int, str] = field(default_factory=dict)
    name_index: Dict[str, int] = field(default_factory=dict)
    claims: List[Tuple[int, int, float]] = field(default_factory=list)
    _next_pid: int = 1

    def ensure_participant(self, display_name: str) -> int:
        key = display_name.strip().lower()
        if key in self.name_index:
            return self.name_index[key]
        pid = self._next_pid
        self._next_pid += 1
        self.participants[pid] = display_name
        self.name_index[key] = pid
        return pid

def allocate(bill: BillState):
    pre = {pid: 0 for pid in bill.participants}
    total_pre = 0
    for it in bill.items:
        total_item = it.qty * it.unit_price
        claims = [(pid, w) for (iid, pid, w) in bill.claims if iid == it.id]
        if not claims:
            continue
        sum_w = sum(w for _, w in claims)
        for pid, w in claims:
            pre[pid] += round(total_item * (w / sum_w))
        total_pre += total_item
    taxes_sum = sum(bill.taxes.values())
    by_user = pre.copy()
    if taxes_sum and total_pre:
        for pid in by_user:
            by_user[pid] += round(pre[pid] / total_pre * taxes_sum)
    return by_user, pre, total_pre

# ==== UTIL UI ====
def _idr(n: int) -> str:
    return f"Rp{n:,}".replace(",", ".")

def _item_claimers(bill: BillState, item_id: int) -> str:
    # return daftar nama yg klaim item ini
    pid_weights = [(pid, w) for (iid, pid, w) in bill.claims if iid == item_id]
    if not pid_weights:
        return "-"
    names = [bill.participants.get(pid, f"U{pid}") for (pid, _) in pid_weights]
    return ", ".join(names)

def _compute_totals(bill: BillState):
    by_user, pre, total_pre = allocate(bill)
    taxes_sum = sum(bill.taxes.values())
    grand = total_pre + taxes_sum
    return by_user, pre, total_pre, taxes_sum, grand

def _render_summary_embed(bill: BillState) -> discord.Embed:
    by_user, pre, total_pre, taxes_sum, grand = _compute_totals(bill)

    em = discord.Embed(
        title="🧾 Split Bill (Gemini)",
        description=f"**Currency:** {bill.currency}",
        color=0x2ecc71
    )

    # fees
    em.add_field(
        name="Biaya",
        value=(
            f"- Tax: {_idr(bill.taxes['tax'])}\n"
            f"- Service: {_idr(bill.taxes['service'])}\n"
            f"- Tips: {_idr(bill.taxes['tips'])}\n"
            f"**Subtotal:** {_idr(total_pre)}\n"
            f"**Grand Total:** {_idr(grand)}"
        ),
        inline=False
    )

    # items + claimers (dipangkas bila panjang)
    lines = []
    for it in bill.items:
        lines.append(
            f"**{it.id}. {it.name}** — x{it.qty} × {_idr(it.unit_price)} "
            f"= {_idr(it.qty * it.unit_price)}\n"
            f"└─ Claimed by: {_item_claimers(bill, it.id)}"
        )

    items_block = "\n".join(lines)
    if len(items_block) > 1024:
        # kalau terlalu panjang, potong biar embed nggak error
        items_block = items_block[:1000] + "\n… (dipotong)"
    em.add_field(name="Items", value=items_block or "_(belum ada)_", inline=False)

    # participants ringkas
    if bill.participants:
        names = ", ".join(sorted(bill.participants.values(), key=str.lower))
        if len(names) > 1024:
            names = names[:1000] + "…"
        em.add_field(name="Peserta", value=names, inline=False)

    em.set_footer(text="Gunakan: m items, m claim <id> Nama1, Nama2 | m setfee tax=.. service=.. tips=.. | m finalize")
    return em

async def _post_or_edit_summary(self, channel: discord.TextChannel, bill: BillState):
    # simpan message id di state supaya bisa diedit setiap ada perubahan
    msg_id = getattr(bill, "summary_message_id", None)
    embed = _render_summary_embed(bill)
    try:
        if msg_id:
            msg = await channel.fetch_message(msg_id)
            await msg.edit(embed=embed)
        else:
            sent = await channel.send(embed=embed)
            bill.summary_message_id = sent.id
    except Exception:
        # kalau gagal fetch (mis. msg sudah hilang), kirim ulang
        sent = await channel.send(embed=embed)
        bill.summary_message_id = sent.id

def _split_by_ratio(total_amt: int, weights: Dict[int, int]) -> Dict[int, int]:
        """
        Bagi total_amt berdasarkan weights (mis. pre-tax per user).
        Hasil dijamin jumlahnya = total_amt (pakai koreksi sisa pembulatan).
        """
        if total_amt <= 0 or not weights:
            return {pid: 0 for pid in weights}

        total_w = sum(max(w, 0) for w in weights.values())
        if total_w == 0:
            return {pid: 0 for pid in weights}

        # hitung pecahan float untuk prioritas sisa
        parts_float = {pid: (weights[pid] / total_w) * total_amt for pid in weights}
        parts_int = {pid: int(parts_float[pid]) for pid in parts_float}
        remainder = total_amt - sum(parts_int.values())

        if remainder != 0:
            # distribusikan sisa ke yang fraksinya terbesar (kalau remainder > 0)
            # atau kurangi dari fraksi terbesar (kalau remainder < 0)
            order = sorted(
                weights.keys(),
                key=lambda pid: parts_float[pid] - int(parts_float[pid]),
                reverse=True
            )
            i = 0
            step = 1 if remainder > 0 else -1
            while remainder != 0 and i < len(order) * 3:  # batas aman
                pid = order[i % len(order)]
                if step < 0 and parts_int[pid] == 0:
                    i += 1
                    continue
                parts_int[pid] += step
                remainder -= step
                i += 1

        return parts_int

class GeminiCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.deepai_key = os.getenv("DEEPAI_API_KEY")
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = genai.GenerativeModel("models/gemini-2.0-flash-lite-001")
        self.state_by_thread: Dict[int, BillState] = {}

    async def _schedule_thread_cleanup(self, thread_id: int, delay_seconds: int = 24*60*60):
        # tidur dulu 24 jam
        await asyncio.sleep(delay_seconds)
        # ambil channel (thread) dari cache atau fetch
        thread = self.bot.get_channel(thread_id)
        if thread is None:
            try:
                thread = await self.bot.fetch_channel(thread_id)
            except Exception:
                thread = None

        if thread is None:
            return  # sudah hilang / tidak bisa diambil

        # coba hapus, kalau gagal (permission), arsipkan + lock
        try:
            await thread.delete(reason="Auto-cleanup splitbill setelah finalize 24 jam")
        except Exception:
            try:
                await thread.edit(archived=True, locked=True, reason="Auto-archive splitbill 24h")
            except Exception:
                pass

        # bersihkan state internal kalau ada
        try:
            self.state_by_thread.pop(thread_id, None)
        except Exception:
            pass

    @commands.command(name="ai", help="Tanya ke AI (Gemini)")
    async def ai_command(self, ctx, *, prompt: str):
        print(f"[Gemini COMMAND] Called by {ctx.author} with prompt: {prompt}")
        async with ctx.typing():
            try:
                response = self.model.generate_content(prompt)
                reply = response.candidates[0].content.parts[0].text.strip()

                if len(reply) > 2000:
                    for chunk in [reply[i:i+2000] for i in range(0, len(reply), 2000)]:
                        await ctx.send(chunk)
                else:
                    await ctx.send(reply)

            except Exception as e:
                print(f"[Gemini ERROR] {e}")
                await ctx.send(f"\u274c Terjadi error: {str(e)}")

    @commands.command(name="anomali", help="Generate kata anomali beserta kisah background berdasarkan nama")
    async def anomali_command(self, ctx, *, name: str):
        prompt = (
            f"cukup satu saja. Buat anomali lucu berdasarkan nama '{name}' yang berisikan 2-5 kata. "
            "Setiap kata anomali harus disertai dengan kisah background singkat yang menjelaskan asal-usul atau makna uniknya dengan minimal 50 kata. "
            "Format:\n"
            "[nama anomali]\n"
            "Kisah: [kisah singkat]\n\n"
        )
        print(f"[Anomali COMMAND] Called by {ctx.author} with name: {name}")
        async with ctx.typing():
            try:
                response = self.model.generate_content(prompt)
                anomali_text = response.candidates[0].content.parts[0].text.strip()

                if len(anomali_text) > 2000:
                    for chunk in [anomali_text[i:i+2000] for i in range(0, len(anomali_text), 2000)]:
                        await ctx.send(chunk)
                else:
                    await ctx.send(f"Anomali dan kisah untuk **{name}**:\n{anomali_text}")

            except Exception as e:
                print(f"[Anomali ERROR] {e}")
                await ctx.send(f"\u274c Terjadi error: {str(e)}")

    @commands.command(name="truth", help="Dapatkan pertanyaan truth dari AI")
    async def truth_command(self, ctx):
        prompt = (
            "Beri aku **satu pertanyaan truth** yang lucu, menantang, atau memalukan. "
            "Hanya tampilkan pertanyaan saja tanpa penjelasan atau kata pembuka/penutup. "
            "Contoh format output: 'Apa hal paling memalukan yang pernah kamu lakukan?'"
        )
        print(f"[Truth COMMAND] Called by {ctx.author}")
        async with ctx.typing():
            try:
                response = self.model.generate_content(prompt)
                truth_question = response.candidates[0].content.parts[0].text.strip()
                await ctx.send(f"**Truth:** {truth_question}")
            except Exception as e:
                print(f"[Truth ERROR] {e}")
                await ctx.send(f"\u274c Terjadi error: {str(e)}")

    @commands.command(name="dare", help="Dapatkan tantangan dare dari AI")
    async def dare_command(self, ctx):
        prompt = (
            "Beri aku **satu tantangan dare** yang lucu, aneh, atau memalukan serta unik, kalau bisa sangat random. "
            "Hanya tampilkan dare-nya saja tanpa kata lain. "
            "Contoh format output: 'Cium benda terdekat dan kirim fotonya.'"
        )
        print(f"[Dare COMMAND] Called by {ctx.author}")
        async with ctx.typing():
            try:
                response = self.model.generate_content(prompt)
                dare_text = response.candidates[0].content.parts[0].text.strip()
                await ctx.send(f"**Dare:** {dare_text}")
            except Exception as e:
                print(f"[Dare ERROR] {e}")
                await ctx.send(f"\u274c Terjadi error: {str(e)}")

    @commands.command(name="rank", help="Buat ranking lucu berdasarkan topik yang kamu kasih")
    async def mrank_command(self, ctx, *, topic: str):
        prompt = (
            f"Buat daftar ranking lucu berdasarkan topik: '{topic}'. "
            "Tampilkan 5 urutan ranking dengan deskripsi singkat yang lucu atau satir. Gunakan format:"
            "1. [Item] - [Deskripsi singkat]\n"
            "2. ... sampai 5."
        )
        print(f"[rank COMMAND] Called by {ctx.author} with topic: {topic}")
        async with ctx.typing():
            try:
                response = self.model.generate_content(prompt)
                ranking_text = response.candidates[0].content.parts[0].text.strip()
                await ctx.send(f"**Ranking untuk topik:** {topic}\n{ranking_text}")
            except Exception as e:
                print(f"[rank ERROR] {e}")
                await ctx.send(f"\u274c Terjadi error: {str(e)}")

    @commands.command(name="image", help="🖼️ Generate gambar AI gratis via Stable Horde")
    async def mimage_command(self, ctx, *, prompt: str):
        await ctx.typing()

        horde_api_key = os.getenv("HORDE_API_KEY")
        if not horde_api_key:
            return await ctx.send("❌ HORDE_API_KEY belum disetel di .env", delete_after=5)

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "apikey": horde_api_key,
            "Client-Agent": "madbot@mad99"
        }

        payload = {
            "prompt": prompt,
            "params": {
                "sampler_name": "k_euler",
                "cfg_scale": 7,
                "steps": 20,
                "width": 512,
                "height": 512
            },
            "nsfw": False,
            "models": ["stable_diffusion"],
            "r2": True,
            "trusted_workers": False,
            "slow_workers": True
        }

        try:
            res = requests.post("https://stablehorde.net/api/v2/generate/async", headers=headers, json=payload)
            res.raise_for_status()
            job_id = res.json()["id"]
        except Exception as e:
            print(f"[mimage ERROR] Submit failed: {e}")
            return await ctx.send("❌ Gagal mengirim permintaan ke Stable Horde. Cek API key atau model.", delete_after=5)

        await ctx.send("🎨 Membuat gambar... Mohon tunggu sebentar...")

        # Poll status
        for _ in range(60):  # max 5 menit
            await asyncio.sleep(5)
            try:
                status = requests.get(f"https://stablehorde.net/api/v2/generate/status/{job_id}", headers=headers)
                status.raise_for_status()
                data = status.json()
                if data.get("done"):
                    break
            except:
                pass
        else:
            return await ctx.send("⏰ Timeout. Server terlalu lama memproses gambar.", delete_after=5)

        try:
            result = requests.get(f"https://stablehorde.net/api/v2/generate/status/{job_id}", headers=headers)
            generations = result.json().get("generations", [])
            if not generations:
                return await ctx.send("⚠️ Tidak ada gambar yang dihasilkan.", delete_after=5)

            image_url = generations[0]["img"]
            img_data = requests.get(image_url).content
            filename = f"{uuid.uuid4().hex}.png"
            with open(filename, "wb") as f:
                f.write(img_data)

            await ctx.send(file=discord.File(filename, filename="mimage.png"))
            os.remove(filename)

        except Exception as e:
            print(f"[mimage ERROR] {e}")
            await ctx.send("❌ Terjadi error saat mengunduh gambar.", delete_after=5)


    @commands.command(name="translate", help="Terjemahkan teks ke bahasa lain. Bisa pakai nama atau kode bahasa.")
    async def translate_command(self, ctx, *, arg: str):
        args = arg.strip().rsplit(" ", 1)
        if len(args) < 2:
            return await ctx.send("❗ Format salah.\nContoh: `mad translate aku lapar en` atau `mad translate aku lapar jepang`")

        text, target_lang = args
        prompt = (
            f"Terjemahkan kalimat berikut ke dalam bahasa '{target_lang}'. "
            f"Tampilkan hanya hasil terjemahannya, tanpa penjelasan atau embel-embel:\n\n"
            f"Teks: {text}"
        )

        print(f"[Translate COMMAND] Called by {ctx.author} → '{text}' → {target_lang}")
        async with ctx.typing():
            try:
                response = self.model.generate_content(prompt)
                translated = response.candidates[0].content.parts[0].text.strip()
                await ctx.send(f"**Hasil terjemahan ke {target_lang}:**\n{translated}")
            except Exception as e:
                print(f"[Translate ERROR] {e}")
                await ctx.send("❌ Terjadi error saat menerjemahkan.")
                
    # ==== FITUR SPLITBILL GEMINI ====
    @commands.command(name="splitbill", help="Split bill otomatis pakai Gemini dari foto struk")
    async def msplitbillgemini_command(self, ctx):
        if not ctx.message.attachments:
            return await ctx.send("❗ Harap attach gambar struk.")
        att = ctx.message.attachments[0]
        if not any(att.filename.lower().endswith(ext) for ext in (".png",".jpg",".jpeg",".webp",".bmp",".tif",".tiff")):
            return await ctx.send("❌ File bukan gambar.")

        await ctx.typing()
        try:
            img_bytes = await att.read()
            prompt = (
                "You are a receipt parser for Indonesian restaurant bills. "
                "Extract line items and fees. STRICT JSON only with keys: currency, items, fees. "
                "items: [{name, qty, unit_price}] (unit_price per item). "
                "fees: {tax, service, tips} in rupiah."
            )
            mime = (att.content_type or "image/png").split(";")[0]
            resp = self.model.generate_content([prompt, {"mime_type": mime, "data": img_bytes}])
            txt = resp.candidates[0].content.parts[0].text.strip()
            m = re.search(r"\{.*\}", txt, re.S)
            data = json.loads(m.group(0) if m else txt)

            # build items (normalisasi: jika unit_price ternyata total utk xN, bagi ke unit)
            items = []
            for it in data.get("items", []):
                name = it.get("name", "?")
                qty = int(it.get("qty") or 1)
                price = int(it.get("unit_price") or 0)
                unit = price // qty if qty > 1 and price % qty == 0 else price
                items.append(Item(id=len(items)+1, name=name, qty=qty, unit_price=unit))

            fees = data.get("fees", {})

            # ganti blok "buat thread & state" di splitbill:
            try:
                thread = await ctx.message.create_thread(
                    name=f"SplitBill-{ctx.message.id}"
                )
            except Exception:
                # fallback: pakai channel sekarang
                thread = ctx.channel
                await ctx.send("⚠️ Gagal membuat thread (izin/tipe channel). Kita lanjut di channel ini ya.")

            bill = BillState(
                id=ctx.message.id,
                thread_id=thread.id,
                created_by=ctx.author.id,
                items=items,
                taxes={
                    "tax": int(fees.get("tax") or 0),
                    "service": int(fees.get("service") or 0),
                    "tips": int(fees.get("tips") or 0),
                }
            )
            bill.ensure_participant(ctx.author.display_name)
            # simpan placeholder untuk message embed
            bill.summary_message_id = None
            self.state_by_thread[thread.id] = bill

            # kirim embed pertama
            await _post_or_edit_summary(self, thread, bill)
            await thread.send("Klaim item dengan: `m claim <item_id> Nama1, Nama2` • Set fee: `m setfee tax=..` • Finalize: `m finalize`")

        except Exception as e:
            await ctx.send(f"❌ Gagal parsing struk: {e}")

    # ---- perintah pendukung (EDIT: semua auto-update embed) ----
    @commands.command(name="items")
    async def items_cmd(self, ctx):
        bill = self.state_by_thread.get(ctx.channel.id)
        if not bill:
            return await ctx.send("Command ini dipakai di thread SplitBill.")
        await _post_or_edit_summary(self, ctx.channel, bill)

    @commands.command(name="claim")
    async def claim_cmd(self, ctx, item_id: int, *, who: str):
        bill = self.state_by_thread.get(ctx.channel.id)
        if not bill:
            return await ctx.send("Command ini dipakai di thread SplitBill.")
        it = next((x for x in bill.items if x.id == item_id), None)
        if not it:
            return await ctx.send("Item tidak ada.")

        # parsing nama (pisah koma/titik koma)
        names = [n.strip() for n in re.split(r"[;,]", who) if n.strip()]
        if not names:
            return await ctx.send("Format: `m claim <item_id> Nama1, Nama2`")

        pids = [bill.ensure_participant(n) for n in names]
        # hapus klaim lama utk peserta2 tsb di item ini
        bill.claims = [(iid,pid,w) for (iid,pid,w) in bill.claims if not (iid==item_id and pid in pids)]
        # bagi rata
        w = 1/len(pids)
        for pid in pids:
            bill.claims.append((item_id, pid, w))

        await _post_or_edit_summary(self, ctx.channel, bill)
        await ctx.message.add_reaction("🧾")

    @commands.command(name="setfee")
    async def setfee_cmd(self, ctx, *, args: str = ""):
        bill = self.state_by_thread.get(ctx.channel.id)
        if not bill:
            return await ctx.send("Command ini dipakai di thread SplitBill.")
        kv = dict(re.findall(r"(?i)\b(tax|service|tips)\s*=\s*([\d\.\,]+)", args))
        if not kv:
            return await ctx.send("Format: `m setfee tax=<angka> service=<angka> tips=<angka>`")
        def to_int(s: str) -> int:
            s = s.replace(".", "").replace(",", "")
            return int(re.sub(r"\D", "", s) or 0)
        for k, v in kv.items():
            bill.taxes[k.lower()] = to_int(v)

        await _post_or_edit_summary(self, ctx.channel, bill)
        await ctx.message.add_reaction("💸")

    @commands.command(name="finalize")
    async def finalize_cmd(self, ctx):
        bill = self.state_by_thread.get(ctx.channel.id)
        if not bill:
            return await ctx.send("Command ini dipakai di thread SplitBill.")

        # Hitung pre-tax per orang dari klaim
        _, pre, total_pre = allocate(bill)
        if total_pre == 0:
            return await ctx.send("Belum ada item yang diklaim.")

        # Total fee (nominal rupiah)
        tax_amt = int(bill.taxes.get("tax", 0) or 0)
        svc_amt = int(bill.taxes.get("service", 0) or 0)
        tips_amt = int(bill.taxes.get("tips", 0) or 0)

        # Distribusi fee proporsional terhadap pre-tax masing-masing orang
        tax_share = _split_by_ratio(tax_amt, pre)
        svc_share = _split_by_ratio(svc_amt, pre)
        tips_share = _split_by_ratio(tips_amt, pre)

        # Total per user = pre + bagiannya (tax + service + tips)
        per_user_total = {}
        for pid in bill.participants:
            per_user_total[pid] = (
                pre.get(pid, 0)
                + tax_share.get(pid, 0)
                + svc_share.get(pid, 0)
                + tips_share.get(pid, 0)
            )

        # Koreksi selisih pembulatan agar pas Grand Total
        grand_total = total_pre + tax_amt + svc_amt + tips_amt
        diff = grand_total - sum(per_user_total.values())
        if diff != 0 and per_user_total:
            target = max(per_user_total, key=per_user_total.get)
            per_user_total[target] += diff

        # Render embed final
        em = discord.Embed(title="✅ Hasil Final", color=0x5865F2)
        em.add_field(name="Subtotal", value=_idr(total_pre), inline=True)
        em.add_field(name="Fee (Tax+Service+Tips)", value=_idr(tax_amt + svc_amt + tips_amt), inline=True)
        em.add_field(name="Grand Total", value=_idr(grand_total), inline=True)

        lines = []
        order = sorted(bill.participants.keys(), key=lambda pid: bill.participants[pid].lower())
        for pid in order:
            name = bill.participants[pid]
            lines.append(
                f"**{name}**: {_idr(per_user_total[pid])} "
                f"(pre-tax {_idr(pre.get(pid,0))}, "
                f"+ tax {_idr(tax_share.get(pid,0))}, "
                f"+ svc {_idr(svc_share.get(pid,0))}, "
                f"+ tips {_idr(tips_share.get(pid,0))})"
            )

        if not lines:
            em.add_field(name="Per Orang", value="-", inline=False)
        else:
            chunk = ""
            first = True
            for ln in lines:
                # +1 untuk newline bila chunk tidak kosong
                add_len = (1 if chunk else 0) + len(ln)
                if len(chunk) + add_len > 1024:
                    em.add_field(name=("Per Orang" if first else "\u200b"), value=chunk, inline=False)
                    first = False
                    chunk = ln
                else:
                    chunk = (f"{chunk}\n{ln}") if chunk else ln
            if chunk:
                em.add_field(name=("Per Orang" if first else "\u200b"), value=chunk, inline=False)
        await ctx.send(embed=em)
                # …setelah kirim embed final
        await ctx.send("🗓️ Thread ini akan dihapus otomatis dalam 24 jam. (Kalau bot tidak punya izin hapus, akan diarsipkan & dikunci.)")

        # jadwalkan cleanup
        if isinstance(ctx.channel, discord.Thread):
            asyncio.create_task(self._schedule_thread_cleanup(ctx.channel.id, 24*60*60))

