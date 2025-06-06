import discord
from discord.ext import commands
import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()

class GeminiCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
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
                await ctx.send(f"❌ Terjadi error: {str(e)}")

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
                await ctx.send(f"❌ Terjadi error: {str(e)}")

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
                await ctx.send(f"❌ Terjadi error: {str(e)}")

    @commands.command(name="dare", help="Dapatkan tantangan dare dari AI")
    async def dare_command(self, ctx):
        prompt = (
            "Beri aku **satu tantangan dare** yang lucu, aneh, atau memalukan. "
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
                await ctx.send(f"❌ Terjadi error: {str(e)}")

    @commands.command(name="neverhaveiever", aliases=["nhie"], help="Dapatkan satu 'Never Have I Ever' dari AI")
    async def never_have_i_ever_command(self, ctx):
        prompt = (
            "Buat satu kalimat 'Never have I ever' yang unik, lucu, atau aneh. "
            "Tampilkan hanya kalimatnya saja, dalam bahasa Indonesia. "
            "Contoh format output: 'Aku belum pernah makan mie instan pakai selai cokelat.'"
        )
        print(f"[NHIE COMMAND] Called by {ctx.author}")
        async with ctx.typing():
            try:
                response = self.model.generate_content(prompt)
                nhie_text = response.candidates[0].content.parts[0].text.strip()
                await ctx.send(f"**Never Have I Ever:** {nhie_text}")
            except Exception as e:
                print(f"[NHIE ERROR] {e}")
                await ctx.send(f"❌ Terjadi error: {str(e)}")

