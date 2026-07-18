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

# 最初に全てのモジュールをインポート
from health_server import start_health_server

# 全てのCogをロードするsetup_hook
async def setup_hook():
    # cogフォルダ内のCogをロード
    await bot.load_extension('cog.role_cog')       # 個人ロール管理
    await bot.load_extension('cog.voice_cog')      # ボイスチャンネル管理
    await bot.load_extension('cog.event_cog')      # イベントチャンネル管理
    logger.info("✅ 全てのCogが正常にロードされました")

bot.setup_hook = setup_hook

# 絶対に表示させるため、手動同期コマンドをコアに直接登録
@bot.tree.command(name="sync", description="スラッシュコマンドを手動で同期します（管理者のみ）")
@discord.app_commands.guild_only()
async def sync_commands(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("このコマンドは管理者のみ実行できます。", ephemeral=True)
        return
    
    await interaction.response.send_message("コマンドを同期中です...数秒で完了します！", ephemeral=True)
    
    try:
        await bot.tree.sync()
        await bot.tree.sync(guild=discord.Object(id=interaction.guild_id))
        registered = [cmd.name for cmd in bot.tree.get_commands()]
        await interaction.edit_original_response(content=f"✅ 同期完了！登録コマンド: {registered}\nこれでDiscordに全てのコマンドが表示されます。")
        logger.info(f"✅ ギルド {interaction.guild.name} で管理者が手動同期を実行しました。登録コマンド: {registered}")
    except Exception as e:
        await interaction.edit_original_response(content=f"❌ 同期に失敗しました: {str(e)}")
        logger.error(f"手動同期中にエラーが発生しました: {e}")

# 最小限のコアロジックだけをbot.pyに残す
@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user} (ID: {bot.user.id})')
    logger.info('Botが正常に起動しました！')
    logger.info('------')
    
    # ヘルスチェックサーバーを最初に起動（競合防止）
    await start_health_server(logger)
    
    # 登録されているコマンドの一覧を最初にログに出力（デバッグ用）
    registered_commands = [cmd.name for cmd in bot.tree.get_commands()]
    logger.info(f"✅ コード上に登録されている全スラッシュコマンド: {registered_commands}")
    logger.info(f"✅ 登録されているコマンド数: {len(registered_commands)}")
    
    if len(registered_commands) == 0:
        logger.error("❌ コマンドが一つも登録されていません！setup_hookが正常に実行されなかった可能性があります")
    else:
        # グローバル同期を実行
        await bot.tree.sync()
        logger.info("✅ グローバルスラッシュコマンドの同期が完了しました")
        
        # 各ギルドに個別に同期して即時反映（全サーバーで数分以内に表示）
        for guild in bot.guilds:
            await bot.tree.sync(guild=discord.Object(id=guild.id))
            logger.info(f"✅ ギルド {guild.name} ({guild.id}) にスラッシュコマンドを個別同期しました")
        logger.info("✅ 全てのサーバーへのスラッシュコマンド同期が完了しました")

if not DISCORD_TOKEN:
    raise ValueError("環境変数にDISCORD_TOKENが設定されていません。.envファイルを確認してください。")


# Botを起動
bot.run(DISCORD_TOKEN)