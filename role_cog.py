import os
import discord
from discord.ext import commands
import asyncio
import logging
from role_manager import (
    process_member, 
    process_guild, 
    ensure_personal_roles_exist, 
    cleanup_orphaned_roles
)
from utils import set_permissions_with_retry, get_ids_from_env

logger = logging.getLogger(__name__)

class RoleManagementCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # 環境変数から各種IDを読み込み
        self.read_only_channel_ids = get_ids_from_env('READ_ONLY_CHANNEL_IDS')
        self.ARCHIVE_CHANNEL_ID = int(os.getenv('ARCHIVE_CHANNEL_ID', '0'))

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("RoleManagementCogが起動しました")
        # 全ギルドの処理を並列実行
        guild_tasks = [process_guild(self.bot, guild, self.read_only_channel_ids, self.ARCHIVE_CHANNEL_ID) for guild in self.bot.guilds]
        await asyncio.gather(*guild_tasks)

        # 起動時に一度だけ孤立した個人ロールを即座にクリーンアップ
        await cleanup_orphaned_roles(self.bot)

        # 定期タスクの開始
        self.bot.loop.create_task(ensure_personal_roles_exist(self.bot, self.read_only_channel_ids, self.ARCHIVE_CHANNEL_ID))
        self.bot.loop.create_task(cleanup_orphaned_roles(self.bot))

        # 読み取り専用チャンネルの権限設定を明示的に実行
        for guild in self.bot.guilds:
            logger.info(f"ギルド {guild.name} の読み取り専用チャンネル権限を設定しています...")
            for channel_id in self.read_only_channel_ids:
                channel = guild.get_channel(channel_id)
                if channel:
                    try:
                        await set_permissions_with_retry(channel, guild.default_role, {"send_messages": False})
                        logger.info(f"チャンネル {channel.name} ({channel.id}) を @everyone に対して読み取り専用に設定しました。")
                    except Exception as e:
                        logger.error(f"チャンネル {channel.name} ({channel.id}) の @everyone 読み取り専用設定に失敗しました: {e}")

    @commands.Cog.listener()
    async def on_member_join(self, member):
        # メンバーシップスクリーニングに対応するため、参加時の自動処理は行わない
        logger.info(f"メンバー {member.display_name} がサーバーに参加しました。ルール同意後にロールを付与します。")
        pass

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        # Bot自身が更新された場合はスキップ
        if after.bot:
            return

        guild = after.guild

        # メンバーシップスクリーニングをパスしたことを検知
        if before.pending and not after.pending:
            logger.info(f"メンバー {after.display_name} がサーバーのルールに同意しました。個人ロールの処理を開始します。")
            await process_member(self.bot, after, guild, self.read_only_channel_ids, self.ARCHIVE_CHANNEL_ID)

        # ニックネームが変更された場合も個人ロールを更新
        elif before.display_name != after.display_name:
            logger.info(f"メンバー {before.display_name} のニックネームが {after.display_name} に変更されました。個人ロールの更新を試みます。")
            await process_member(self.bot, after, guild, self.read_only_channel_ids, self.ARCHIVE_CHANNEL_ID, old_display_name=before.display_name)

        # ニックネームは変更されていないが、ロールが変更された場合
        elif before.roles != after.roles:
            logger.info(f"メンバー {after.display_name} のロールが変更されました。個人ロールの状態を再確認します。")
            await process_member(self.bot, after, guild, self.read_only_channel_ids, self.ARCHIVE_CHANNEL_ID)

async def setup(bot: commands.Bot):
    await bot.add_cog(RoleManagementCog(bot))
    logger.info("RoleManagementCogが正常にロードされました")