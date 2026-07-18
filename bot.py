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



@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user} (ID: {bot.user.id})')
    logger.info('Botが正常に起動しました！')
    logger.info('------')

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
    
    # スラッシュコマンドをDiscordに同期
    await bot.tree.sync()
    logger.info("スラッシュコマンドを正常に同期しました")


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



# アクティブなイベントチャンネルを管理するグローバル変数
active_event_channel_id = None
event_owner_id = None

# スラッシュコマンドを登録
@bot.tree.command(name="hajimeru", description="イベント用のチャンネルを作成して開始します")
async def hajimeru_command(interaction: discord.Interaction, content: str):
    global active_event_channel_id, event_owner_id
    
    # 既にアクティブなイベントチャンネルが存在する場合はエラー
    if active_event_channel_id is not None:
        await interaction.response.send_message("既にアクティブなイベントチャンネルが存在します。先に/owariで終了してください。", ephemeral=True)
        return

    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("このコマンドはサーバー内でのみ使用できます。", ephemeral=True)
        return

    # チャンネル名を作成
    channel_name = f"📅イベント開催中-{content.replace(' ', '-')}"

    try:
        # 既存のルートチャンネル（カテゴリに属さないチャンネル）をposition順に取得
        root_channels = [ch for ch in guild.channels if ch.category is None and isinstance(ch, discord.TextChannel)]
        # positionでソートして既存のチャンネルを順番に下にずらす
        for ch in sorted(root_channels, key=lambda x: x.position):
            await ch.edit(position=ch.position + 1)
            logger.info(f"既存チャンネル {ch.name} の位置を{ch.position + 1}に更新しました")

        # カテゴリなしでサーバーの最上部に新しいテキストチャンネルを作成
        new_channel = await guild.create_text_channel(
            name=channel_name,
            topic=f"{interaction.user.display_name}さんが「{content}」を始めました。",
            reason=f"{interaction.user.display_name}が「{content}」を開始",
            position=0  # 確実に最上部に配置
        )

        # 念のため再度位置を更新して最上部に固定
        await new_channel.edit(position=0)
        logger.info(f"新規イベントチャンネル {new_channel.name} を作成し、最上部に配置しました")

        # 全てのロールに対してメッセージ送信権限を無効化し、誰も書き込めないようにする
        # まず@everyone（全員）の権限を無効化
        await set_permissions_with_retry(new_channel, guild.default_role, {"send_messages": False})
        # さらにサーバー内の全てのロール（個人ロールを含む）に対しても明示的に無効化
        # 個人ロールはメンバーの表示名と同じ名前で作成されるので、管理者以外の全ロールを対象に
        for role in guild.roles:
            # @everyone、ボットオーナー、管理者以外は全てのロールの送信権限を無効化
            if role != guild.default_role and not (role.is_bot_owner() if hasattr(role, 'is_bot_owner') else False) and not role.permissions.administrator:
                await set_permissions_with_retry(new_channel, role, {"send_messages": False})
                logger.debug(f"ロール {role.name} の送信権限を無効化しました")
        # Bot自身、サーバー管理者、そしてイベント作成者だけは書き込み可能に設定
        await set_permissions_with_retry(new_channel, guild.me, {"send_messages": True})
        # コマンドを実行したイベント作成者に書き込み権限を付与（個人ロールがあっても個別に許可）
        await set_permissions_with_retry(new_channel, interaction.user, {"send_messages": True})
        # サーバー管理者全員に書き込み権限を付与
        for member in guild.members:
            if member.guild_permissions.administrator and not member.bot and member.id != interaction.user.id:
                await set_permissions_with_retry(new_channel, member, {"send_messages": True})
        logger.info(f"イベントチャンネル {new_channel.name} の一般ユーザーの書き込み権限を無効化（作成者・管理者・Botのみ書き込み可）")

        # 作成したチャンネルのIDと所有者をグローバル変数に保存
        active_event_channel_id = new_channel.id
        event_owner_id = interaction.user.id

        await interaction.response.send_message(f"イベントチャンネル {new_channel.mention} を作成しました！イベントを開始します。", ephemeral=False)

    except Exception as e:
        logger.error(f"イベントチャンネルの作成に失敗しました: {e}")
        await interaction.response.send_message(f"チャンネルの作成に失敗しました: {e}", ephemeral=True)

@bot.tree.command(name="owari", description="アクティブなイベントチャンネルを削除して終了します")
async def owari_command(interaction: discord.Interaction):
    global active_event_channel_id, event_owner_id

    # アクティブなチャンネルが存在しない場合
    if active_event_channel_id is None:
        await interaction.response.send_message("現在アクティブなイベントチャンネルは存在しません。", ephemeral=True)
        return

    # チャンネルの所有者または管理者のみが削除可能
    if interaction.user.id != event_owner_id and not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("このコマンドはイベントの作成者または管理者のみが実行できます。", ephemeral=True)
        return

    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("このコマンドはサーバー内でのみ使用できます。", ephemeral=True)
        return

    channel = guild.get_channel(active_event_channel_id)
    if channel:
        try:
            await channel.delete()
            logger.info(f"イベントチャンネル {channel.name} を削除しました")
            await interaction.response.send_message("イベントチャンネルを削除しました。イベントを終了します。", ephemeral=False)
        except Exception as e:
            logger.error(f"イベントチャンネルの削除に失敗しました: {e}")
            await interaction.response.send_message(f"チャンネルの削除に失敗しました: {e}", ephemeral=True)
    else:
        await interaction.response.send_message("チャンネルが見つかりませんでした。", ephemeral=True)

    # グローバル変数をリセット
    active_event_channel_id = None
    event_owner_id = None



# ボイスイベントをセットアップ
setup_voice_events(bot)

if not DISCORD_TOKEN:
    raise ValueError("環境変数にDISCORD_TOKENが設定されていません。.envファイルを確認してください。")


# Botを起動
bot.run(DISCORD_TOKEN)