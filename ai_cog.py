import discord
from discord.ext import commands
import google.generativeai as genai
import os
import requests
import uuid
import asyncio
from dotenv import load_dotenv

load_dotenv()

class GeminiCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.deepai_key = os.getenv("DEEPAI_API_KEY")
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = genai.GenerativeModel("models/gemini-2.0-flash-lite-001")
        print("[GeminiCog] Loaded successfully")

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
