from discord import Attachment
from discord.ext import commands
from typing import Optional

async def extract_image_attachment(ctx: commands.Context) -> Optional[Attachment]:
    # Cek attachment di pesan saat ini
    if ctx.message.attachments:
        for attachment in ctx.message.attachments:
            if attachment.content_type and attachment.content_type.startswith("image/"):
                return attachment

    # Cek jika pesan membalas pesan lain yang mengandung gambar
    if ctx.message.reference:
        message_id = ctx.message.reference.message_id
        if message_id is not None:
            try:
                replied = await ctx.channel.fetch_message(message_id)
                for attachment in replied.attachments:
                    if attachment.content_type and attachment.content_type.startswith("image/"):
                        return attachment
            except Exception as e:
                print(f"Failed to fetch replied message: {e}")

    return None
