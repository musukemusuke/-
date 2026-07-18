import discord
from discord.ext import commands
import logging

logger = logging.getLogger(__name__)

# グローバル変数（イベントの状態管理）
active_event_channel_id = None
event_owner_id = None

class EventManagementCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        global active_event_channel_id
        global event_owner_id

    @discord.app_commands.command(name="hajimeru", description="イベントチャンネルを作成します")
    @discord.app_commands.guild_only()
    async def start_event(self, interaction: discord.Interaction, content: str):
        # 既存のイベントチャンネルが存在する場合はエラー
        global active_event_channel_id
        if active_event_channel_id is not None:
            await interaction.response.send_message("既にイベントチャンネルが存在します。先に/owariで削除してください。", ephemeral=True)
            return

        await interaction.response.send_message("イベントチャンネルを作成中です...", ephemeral=True)
        guild = interaction.guild
        if not guild:
            await interaction.edit_original_response(content="ギルドが見つかりません。")
            return

        try:
            # カテゴリなしの最上部にテキストチャンネルを作成
            new_channel = await guild.create_text_channel(f"📅イベント開催中-{content}")
            
            # 既存のカテゴリなしチャンネルを全て取得して位置を下げる
            categoryless_channels = [ch for ch in guild.channels if ch.category is None]
            # 新しいチャンネルを0番目に配置するため、既存のチャンネルを順番に下げる
            for i, channel in enumerate(categoryless_channels):
                if channel.id != new_channel.id:
                    await channel.edit(position=i+1)
            await new_channel.edit(position=0)

            # @everyoneの書き込み権限を無効化
            await new_channel.set_permissions(guild.default_role, send_messages=False, add_reactions=False)
            
            # 管理者、イベント作成者、Botのみ書き込み可能に
            await new_channel.set_permissions(interaction.user, send_messages=True, add_reactions=True)
            event_owner_id = interaction.user.id
            if guild.me:
                await new_channel.set_permissions(guild.me, send_messages=True, add_reactions=True, manage_channels=True)
            
            # 全ての非管理者ロールの権限を一括で無効化
            for role in guild.roles:
                if not role.permissions.administrator and role != guild.default_role and role.id != interaction.user.top_role.id:
                    await new_channel.set_permissions(role, send_messages=False, add_reactions=False)

            active_event_channel_id = new_channel.id
            await interaction.edit_original_response(content=f"✅ イベントチャンネル「{new_channel.name}」を最上部に作成しました！あなたのみ書き込み可能です。")
            logger.info(f"イベントチャンネル {new_channel.name} (ID: {new_channel.id}) をギルド {guild.name} に作成しました。作成者: {interaction.user}")

        except Exception as e:
            logger.error(f"イベントチャンネルの作成中にエラーが発生しました: {e}")
            await interaction.edit_original_response(content=f"❌ イベントチャンネルの作成に失敗しました: {str(e)}")

    @discord.app_commands.command(name="owari", description="イベントチャンネルを削除します")
    @discord.app_commands.guild_only()
    async def end_event(self, interaction: discord.Interaction):
        global active_event_channel_id, event_owner_id
        if active_event_channel_id is None:
            await interaction.response.send_message("現在アクティブなイベントチャンネルが存在しません。", ephemeral=True)
            return

        # イベント作成者または管理者のみ実行可能
        if not interaction.user.guild_permissions.administrator and interaction.user.id != event_owner_id:
            await interaction.response.send_message("このコマンドはイベント作成者または管理者のみ実行できます。", ephemeral=True)
            return

        await interaction.response.send_message("イベントチャンネルを削除中です...", ephemeral=True)
        guild = interaction.guild
        if not guild:
            await interaction.edit_original_response(content="ギルドが見つかりません。")
            return

        event_channel = guild.get_channel(active_event_channel_id)
        if not event_channel:
            await interaction.edit_original_response(content="イベントチャンネルが見つかりません。状態をリセットします。")
            active_event_channel_id = None
            event_owner_id = None
            return

        try:
            await event_channel.delete()
            # グローバル変数をリセット
            active_event_channel_id = None
            event_owner_id = None
            await interaction.edit_original_response(content=f"✅ イベントチャンネル「{event_channel.name}」を削除しました。")
            logger.info(f"イベントチャンネル {event_channel.name} をギルド {guild.name} から削除しました。")

        except Exception as e:
            logger.error(f"イベントチャンネルの削除中にエラーが発生しました: {e}")
            await interaction.edit_original_response(content=f"❌ イベントチャンネルの削除に失敗しました: {str(e)}")

    # /syncコマンドはbot.pyのコアに直接登録したので、ここでは定義しない（重複防止）

# 必須のsetup関数：CogをBotにロードするために必要
async def setup(bot: commands.Bot):
    await bot.add_cog(EventManagementCog(bot))
    logger.info("EventManagementCogが正常にロードされました")