import discord
from discord.ext import commands
import openai
import os

class AICog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        openai.api_key = os.getenv("OPENAI_API_KEY")

    @commands.command(name="ai", help="Tanya apapun ke AI (GPT)")
    async def ai(self, ctx, *, prompt: str):
        await ctx.trigger_typing()

        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",  # atau gpt-3.5-turbo jika tidak punya akses GPT-4
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            reply = response.choices[0].message.content
            if len(reply) > 2000:
                # kalau jawaban terlalu panjang
                for chunk in [reply[i:i+2000] for i in range(0, len(reply), 2000)]:
                    await ctx.send(chunk)
            else:
                await ctx.send(reply)

        except Exception as e:
            await ctx.send(f"❌ Terjadi error: {str(e)}")
