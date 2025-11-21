import discord
from discord.ext import commands
from discord import ui, Interaction
import json

from database import (
    connect_db,
    save_role_message,
    load_all_role_messages,
)

# ============================
# SELECT MENU
# ============================
class RoleSelect(ui.Select):
    def __init__(self, roles_map, single_mode, custom_id):
        self.roles_map = roles_map
        self.single_mode = single_mode

        options = [
            discord.SelectOption(
                label=role.name,
                emoji=emoji,
                value=str(role.id)
            )
            for role, emoji in roles_map.items()
        ]

        # MODE SETTINGS
        if single_mode:
            min_v = 1
            max_v = 1
        else:
            min_v = 0
            max_v = len(options)

        super().__init__(
            placeholder="Pilih role kamu...",
            min_values=min_v,
            max_values=max_v,
            options=options,
            custom_id=custom_id
        )

    async def callback(self, interaction: Interaction):
        try:
            user = interaction.user
            guild = interaction.guild

            selected_role_ids = [int(v) for v in self.values]
            current_roles = [r.id for r in user.roles]

            target_role_ids = [r.id for r in self.roles_map.keys()]

            # ROLES to ADD
            add_roles = [
                guild.get_role(rid)
                for rid in selected_role_ids
                if rid in target_role_ids and rid not in current_roles
            ]

            # ROLES to REMOVE
            remove_roles = [
                guild.get_role(rid)
                for rid in target_role_ids
                if rid not in selected_role_ids and rid in current_roles
            ]

            # SINGLE MODE
            if self.single_mode:
                # remove all first
                for rid in target_role_ids:
                    if rid not in selected_role_ids:
                        role = guild.get_role(rid)
                        if role and role in user.roles:
                            try:
                                await user.remove_roles(role)
                            except discord.Forbidden:
                                return await interaction.response.send_message(
                                    "❌ Bot tidak punya izin untuk mencopot role ini.",
                                    ephemeral=True
                                )

                # add new one
                for role in add_roles:
                    try:
                        await user.add_roles(role)
                    except discord.Forbidden:
                        return await interaction.response.send_message(
                            "❌ Bot tidak punya izin untuk menambahkan role ini.",
                            ephemeral=True
                        )

                return await interaction.response.send_message(
                    "🔄 Role kamu diperbarui!",
                    ephemeral=True
                )

            # MULTI MODE
            for role in add_roles:
                try:
                    await user.add_roles(role)
                except discord.Forbidden:
                    return await interaction.response.send_message(
                        "❌ Bot tidak punya izin untuk menambahkan role ini.",
                        ephemeral=True
                    )

            for role in remove_roles:
                try:
                    await user.remove_roles(role)
                except discord.Forbidden:
                    return await interaction.response.send_message(
                        "❌ Bot tidak punya izin untuk mencopot role ini.",
                        ephemeral=True
                    )

            await interaction.response.send_message(
                "✔️ Role berhasil diperbarui!",
                ephemeral=True
            )

        except Exception as e:
            print("ERROR in RoleSelect callback:", e)
            import traceback
            traceback.print_exc()
            return await interaction.response.send_message(
                "❌ Internal error (lihat console bot).",
                ephemeral=True
            )


class RoleSelectView(ui.View):
    def __init__(self, roles_map, single_mode, custom_id):
        super().__init__(timeout=None)
        self.add_item(RoleSelect(roles_map, single_mode, custom_id))


# ============================
#   MAIN COG
# ============================
class RoleSelectCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db

    # ==================================================
    # COMMAND SELECTROLE
    # ==================================================
    @commands.command(name="selectrole")
    @commands.has_permissions(administrator=True)
    async def selectrole(self, ctx, *, args):
        """
        selectrole single/multi | title | message | @role emoji, ...
        """

        try:
            mode, title, desc, roles_raw = [x.strip() for x in args.split("|")]
            mode = mode.lower()
            if mode not in ["single", "multi"]:
                return await ctx.send("❌ Mode harus `single` atau `multi`.")
        except ValueError:
            return await ctx.send("❌ Format salah!")

        parts = [x.strip() for x in roles_raw.replace("\n", " ").split(",")]
        roles_map = {}

        for part in parts:
            if not part:
                continue  # skip kosong akibat koma ganda atau newline

            tokens = part.split(" ")
            if len(tokens) < 2:
                return await ctx.send(f"❌ Format salah di bagian: `{part}`")

            emoji = tokens[-1]
            role_part = " ".join(tokens[:-1]).strip()

            # cari role mention dari message
            role = None
            for rm in ctx.message.role_mentions:
                if f"<@&{rm.id}>" in role_part:
                    role = rm
                    break

            if not role:
                return await ctx.send(f"❌ Role tidak valid: `{role_part}`")

            roles_map[role] = emoji



        embed = discord.Embed(
            title=title,
            description=desc,
            color=discord.Color.orange()
        )

        for role, emoji in roles_map.items():
            embed.add_field(
                name=f"{emoji} {role.name}",
                value=role.mention,
                inline=False
            )

        # create dummy first to get message_id
        dummy_msg = await ctx.send("⏳ Membuat menu…")

        custom_id = f"selectrole_{dummy_msg.id}"
        view = RoleSelectView(roles_map, mode == "single", custom_id)

        await dummy_msg.edit(content=None, embed=embed, view=view)

        # save to DB
        save_role_message(
            self.db,
            mode,
            ctx.guild.id,
            ctx.channel.id,
            dummy_msg.id,
            title,
            desc,
            roles_map
        )

        await ctx.send("✅ **Select role berhasil dibuat & disimpan!**", delete_after=5)

    # ==================================================
    # RESTORE PERSISTENT VIEW
    # ==================================================
    @commands.Cog.listener()
    async def on_ready(self):
        rows = load_all_role_messages(self.db)

        for row in rows:
            guild = self.bot.get_guild(row["guild_id"])
            channel = guild.get_channel(row["channel_id"])
            single_mode = bool(row["single_mode"])

            if not guild or not channel:
                continue

            roles_data = json.loads(row["roles_json"])
            roles_map = {
                guild.get_role(int(rid)): emoji
                for rid, emoji in roles_data.items()
                if guild.get_role(int(rid))
            }

            custom_id = f"selectrole_{row['message_id']}"
            view = RoleSelectView(roles_map, single_mode, custom_id)

            # try:
            #     self.bot.add_view(view, message_id=row["message_id"])
            #     print(f"[RESTORE] SelectRole restored for {row['message_id']}")
            # except Exception as e:
            #     print("Restore error:", e)


async def setup(bot):
    await bot.add_cog(RoleSelectCog(bot))
