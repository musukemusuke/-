import sys
import os
import asyncio
import discord
from discord.ext import commands
from aiohttp import web
from utils import (
    setup_logger,
    set_permissions_with_retry,
    get_ids_from_env
)
from voice_manager import setup_voice_events

# ロガーの初期化
logger = setup_logger(__name__)

# 必須環境変数の一括バリデーション
required_env_vars = [
    'DISCORD_TOKEN'
]
missing_vars = []
for var in required_env_vars:
    if not os.getenv(var):
        missing_vars.append(var)
if missing_vars:
    logger.error(f"以下の必須環境変数が設定されていません: {', '.join(missing_vars)}")
    exit(1)

# 環境変数からトークンを取得
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

# 環境変数から各種IDを読み込み + バリデーション強化
read_only_channel_ids = get_ids_from_env('READ_ONLY_CHANNEL_IDS')
if not read_only_channel_ids:
    logger.warning("READ_ONLY_CHANNEL_IDSが環境変数に設定されていないか、無効なIDが含まれています。読み取り専用チャンネルの権限設定をスキップします。")

# アーカイブチャンネルIDのバリデーション
ARCHIVE_CHANNEL_ID = int(os.getenv('ARCHIVE_CHANNEL_ID', '0'))
if ARCHIVE_CHANNEL_ID == 0:
    logger.error("ARCHIVE_CHANNEL_IDが環境変数に設定されていないか、無効なIDです。アーカイブチャンネルの権限保護をスキップします。")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
# コマンド機能を使わないため、基本的なdiscord.Clientを使用
bot = commands.Bot(command_prefix='!', intents=intents)

# utilsからメトリクスをインポート
from utils import metrics
from role_manager import process_member, process_guild, ensure_personal_roles_exist, cleanup_orphaned_roles
from health_server import start_health_server
from event_manager import register_event_commands



@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user} (ID: {bot.user.id})')
    logger.info('Botが正常に起動しました！')
    logger.info('------')
    
    # ヘルスチェックサーバーを起動
    await start_health_server(logger)

    # 全ギルドの処理を並列実行
    guild_tasks = [process_guild(bot, guild, read_only_channel_ids, ARCHIVE_CHANNEL_ID) for guild in bot.guilds]
    await asyncio.gather(*guild_tasks)

    # 起動時に一度だけ孤立した個人ロールを即座にクリーンアップ
    await cleanup_orphaned_roles(bot)

    # 定期タスクの開始
    bot.loop.create_task(ensure_personal_roles_exist(bot, read_only_channel_ids, ARCHIVE_CHANNEL_ID))
    bot.loop.create_task(cleanup_orphaned_roles(bot))

    # 読み取り専用チャンネルの権限設定を明示的に実行
    for guild in bot.guilds:
        logger.info(f"ギルド {guild.name} の読み取り専用チャンネル権限を設定しています...")
        logger.debug(f"READ_ONLY_CHANNEL_IDS: {read_only_channel_ids}") # デバッグログ
        for channel_id in read_only_channel_ids:
            channel = guild.get_channel(channel_id)
            if channel:
                logger.debug(f"チャンネル {channel.name} ({channel.id}) の @everyone 権限設定を試みます。") # デバッグログ
                try:
                    # @everyoneロールのメッセージ送信権限を無効にする
                    await set_permissions_with_retry(channel, guild.default_role, {"send_messages": False})
                    logger.info(f"チャンネル {channel.name} ({channel.id}) を @everyone に対して読み取り専用に設定しました。")
                except Exception as e:
                    logger.error(f"チャンネル {channel.name} ({channel.id}) の @everyone 読み取り専用設定に失敗しました: {e}")
            else:
                logger.warning(f"読み取り専用チャンネルID {channel_id} がギルド {guild.name} で見つかりませんでした。")
    
    # 先にイベント管理用コマンドを登録（同期する前に登録が必要）
    await register_event_commands(bot)
    logger.info("イベント管理コマンドの登録が完了しました")
    
    # 特定のギルドにだけスラッシュコマンドを同期（即時反映）
    TARGET_GUILD_ID = 1518079520911921192
    target_guild = discord.Object(id=TARGET_GUILD_ID)
    await bot.tree.sync(guild=target_guild)
    logger.info(f"対象ギルドID {TARGET_GUILD_ID} にスラッシュコマンドを同期しました（即時反映）")
    logger.info("全てのスラッシュコマンドの同期が完了しました")


@bot.event
async def on_member_join(member):
    # メンバーシップスクリーニングに対応するため、参加時の自動処理は行わない
    # ルール同意後の on_member_update で処理する
    logger.info(f"メンバー {member.display_name} がサーバーに参加しました。ルール同意後にロールを付与します。")
    pass

@bot.event
async def on_member_update(before, after):
    # Bot自身が更新された場合はスキップ
    if after.bot:
        return

    guild = after.guild

    # メンバーシップスクリーニングをパスしたことを検知
    if before.pending and not after.pending:
        logger.info(f"メンバー {after.display_name} がサーバーのルールに同意しました。個人ロールの処理を開始します。")
        await process_member(bot, after, guild, read_only_channel_ids, ARCHIVE_CHANNEL_ID)

    # ニックネームが変更された場合も個人ロールを更新
    elif before.display_name != after.display_name:
        logger.info(f"メンバー {before.display_name} のニックネームが {after.display_name} に変更されました。個人ロールの更新を試みます。")
        await process_member(bot, after, guild, read_only_channel_ids, ARCHIVE_CHANNEL_ID, old_display_name=before.display_name)

    # ニックネームは変更されていないが、ロールが変更された場合
    elif before.roles != after.roles:
        logger.info(f"メンバー {after.display_name} のロールが変更されました。個人ロールの状態を再確認します。")
        await process_member(bot, after, guild, read_only_channel_ids, ARCHIVE_CHANNEL_ID)



# ボイスイベントをセットアップ
setup_voice_events(bot)

if not DISCORD_TOKEN:
    raise ValueError("環境変数にDISCORD_TOKENが設定されていません。.envファイルを確認してください。")


# Botを起動
bot.run(DISCORD_TOKEN)