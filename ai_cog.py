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
