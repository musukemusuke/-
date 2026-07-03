import sys
import os
import asyncio
import discord
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

PRIVATE_THREAD_ALLOWED_CHANNEL_IDS = get_ids_from_env('PRIVATE_THREAD_ALLOWED_CHANNEL_IDS')
if not PRIVATE_THREAD_ALLOWED_CHANNEL_IDS:
    logger.error("PRIVATE_THREAD_ALLOWED_CHANNEL_IDSが環境変数に設定されていないか、無効なIDが含まれています。プライベートスレッド作成機能が動作しません。")

# アーカイブチャンネルIDのバリデーション
ARCHIVE_CHANNEL_ID = int(os.getenv('ARCHIVE_CHANNEL_ID', '0'))
if ARCHIVE_CHANNEL_ID == 0:
    logger.error("ARCHIVE_CHANNEL_IDが環境変数に設定されていないか、無効なIDです。アーカイブチャンネルの権限保護をスキップします。")

# スレッドの自動アーカイブ期間を環境変数で設定可能に（Discordの制約に沿って検証）
THREAD_AUTO_ARCHIVE_MINUTES = int(os.getenv('THREAD_AUTO_ARCHIVE_MINUTES', '60'))
valid_archive_durations = [60, 1440, 4320, 10080]  # Discordで許可されている値
if THREAD_AUTO_ARCHIVE_MINUTES not in valid_archive_durations:
    logger.warning(f"THREAD_AUTO_ARCHIVE_MINUTESに無効な値({THREAD_AUTO_ARCHIVE_MINUTES})が設定されています。デフォルトの60分を使用します。有効な値: {valid_archive_durations}")
    THREAD_AUTO_ARCHIVE_MINUTES = 60

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
# コマンド機能を使わないため、基本的なdiscord.Clientを使用
bot = discord.Client(intents=intents)

# utilsからメトリクスをインポート
from utils import metrics

# 個人ロールを作成・付与する非同期関数（並列処理用）
async def process_member(member, guild):
    if member.bot:
        return
    # 処理したメンバー数のメトリクスをインクリメント
    metrics['members_processed'] += 1
    
    # メンバーが自分の名前のロールを持っているか確認
    role_name = member.display_name[:100]  # ロール名は最大100文字
    has_role = any(role.name == role_name for role in member.roles)
    
    if not has_role:
        logger.info(f"メンバー {member.display_name} にロールが付与されていないので作成します...")
        role_color = discord.Color.random()
        member_permissions = discord.Permissions()
        member_permissions.view_channel = True
        member_permissions.send_messages = True
        member_permissions.read_message_history = True
        member_permissions.add_reactions = True
        member_permissions.embed_links = True
        member_permissions.attach_files = True
        member_permissions.external_emojis = True
        member_permissions.external_stickers = True
        member_permissions.send_messages_in_threads = True
        member_permissions.send_polls = True
        member_permissions.use_application_commands = True
        member_permissions.mention_everyone = False
        member_permissions.connect = True
        member_permissions.speak = True
        member_permissions.stream = True
        member_permissions.use_voice_activation = True
        member_permissions.set_voice_channel_status = True
        member_permissions.use_embedded_activities = True
        member_permissions.create_expressions = True # エクスプレッションを作成権限を追加
        member_permissions.change_nickname = True

        # ロール作成時のエラーハンドリングを強化
        try:
            new_role = await guild.create_role(
                name=role_name,
                color=role_color,
                permissions=member_permissions,
                reason=f"Bot起動時にロールがなかったため {member.display_name} の個人ロールを作成"
            )
            await member.add_roles(new_role)
            logger.info(f"メンバー {member.display_name} に新しい個人ロールを付与しました。ロールID: {new_role.id}")
        except discord.Forbidden:
            logger.error(f"権限不足でメンバー {member.display_name} の個人ロールを作成できません。Botのロールがサーバー内で最上位に配置されているか、ロール管理権限が有効になっているか確認してください。")
        except discord.HTTPException as e:
            logger.error(f"メンバー {member.display_name} の個人ロール作成中にDiscord APIエラーが発生しました。ステータスコード: {e.status}, エラーメッセージ: {e.text}")
        except Exception as e:
            logger.error(f"メンバー {member.display_name} の個人ロール作成中に予期せぬエラーが発生しました: {type(e).__name__}: {str(e)}")

        # アーカイブチャンネルは権限設定の対象から除外（サーバーオーナーとBotだけが閲覧可能）
        # ARCHIVE_CHANNEL_IDが0の場合はスキップ
        if ARCHIVE_CHANNEL_ID != 0:
            # 全チャンネルの権限をリトライ付きで設定
            for channel in guild.channels:
                # アーカイブチャンネルは権限設定をスキップ
                if channel.id == ARCHIVE_CHANNEL_ID:
                    continue
                if channel.id in read_only_channel_ids:
                    await set_permissions_with_retry(channel, new_role, {"view_channel": True, "send_messages": False}, logger=logger)
                else:
                    await set_permissions_with_retry(channel, new_role, {"view_channel": True, "send_messages": True}, logger=logger)
                logger.debug(f"チャンネル {channel.name} で {new_role.name} の権限を設定しました。")
    
# ヘルスチェック用エンドポイント
async def health_check(request):
    return web.Response(text="Bot is running", status=200)

# メトリクス用エンドポイント（Prometheus形式で出力）
async def metrics_endpoint(request):
    # Prometheusのフォーマットに変換して出力
    prometheus_output = (
        f"# HELP bot_permission_errors_total 権限設定エラーの合計回数\n"
        f"# TYPE bot_permission_errors_total counter\n"
        f"bot_permission_errors_total {metrics['permission_errors']}\n"
        f"\n# HELP bot_cache_saves_total キャッシュ保存の合計回数\n"
        f"# TYPE bot_cache_saves_total counter\n"
        f"bot_cache_saves_total {metrics['cache_saves']}\n"
        f"\n# HELP bot_members_processed_total 処理したメンバーの合計数\n"
        f"# TYPE bot_members_processed_total counter\n"
        f"bot_members_processed_total {metrics['members_processed']}\n"
        f"\n# HELP bot_roles_created_total 作成したロールの合計数\n"
        f"# TYPE bot_roles_created_total counter\n"
        f"bot_roles_created_total {metrics['roles_created']}\n"
    )
    return web.Response(text=prometheus_output, content_type='text/plain; version=0.0.4')

async def start_health_server():
    # 環境変数からヘルスチェック用ポートを取得（デフォルト8080）
    health_port = int(os.getenv('HEALTH_CHECK_PORT', 8080))
    app = web.Application()
    app.add_routes([
        web.get('/health', health_check),
        web.get('/metrics', metrics_endpoint)
    ])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', health_port)
    await site.start()
    logger.info(f'ヘルスチェック・メトリクスサーバーを起動しました。ポート: {health_port}')

# ギルドごとのメンバー処理を並列実行
async def process_guild(guild):
    logger.info(f"サーバー {guild.name} のメンバーをチェックしています...")
    # 全メンバーの処理を並列実行
    tasks = [process_member(member, guild) for member in guild.members]
    await asyncio.gather(*tasks)
    logger.info(f"サーバー {guild.name} のメンバーチェックが完了しました。")

# 定期的に個人ロールの存在を確認し、不足していれば付与するタスク
async def ensure_personal_roles_exist():
    while True:
        logger.info("定期タスク: 個人ロールの存在確認を開始します。")
        for guild in bot.guilds:
            logger.info(f"ギルド {guild.name} のメンバーの個人ロールを確認中...")
            tasks = [process_member(member, guild) for member in guild.members]
            await asyncio.gather(*tasks)
            logger.info(f"ギルド {guild.name} の個人ロール確認が完了しました。")
        # 24時間ごとに実行
        await asyncio.sleep(24 * 60 * 60)

# 定期的に孤立した個人ロールをクリーンアップするタスク
async def cleanup_orphaned_roles():
    await bot.wait_until_ready()
    while not bot.is_closed():
        for guild in bot.guilds:
            logger.info(f"ギルド {guild.name} の孤立した個人ロールのクリーンアップを開始します。")
            # 現在の全メンバーが持っているロールのIDを収集
            all_member_role_ids = set()
            for member in guild.members:
                if not member.bot:
                    for role in member.roles:
                        all_member_role_ids.add(role.id)
            
            # Botより下のロールで、誰も持っていないロールを削除
            for role in guild.roles:
                if role.id not in all_member_role_ids and role < guild.me.top_role and role != guild.default_role:
                    try:
                        await role.delete(reason="誰も保持していない孤立した個人ロールのため削除")
                        logger.info(f"孤立した個人ロール {role.name} を削除しました。")
                    except Exception as e:
                        logger.error(f"孤立ロール {role.name} の削除に失敗しました: {e}")
        # 24時間ごとにクリーンアップを実行
        await asyncio.sleep(86400)


@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user} (ID: {bot.user.id})')
    logger.info('Botが正常に起動しました！')
    logger.info('------')
    
    # ヘルスチェックサーバーを起動
    await start_health_server()

    # 全ギルドの処理を並列実行
    guild_tasks = [process_guild(guild) for guild in bot.guilds]
    await asyncio.gather(*guild_tasks)
    
    # 起動時に一度だけ孤立した個人ロールを即座にクリーンアップ
    for guild in bot.guilds:
        logger.info(f"起動時クリーンアップ: ギルド {guild.name} の孤立ロールを検索します")
        all_member_role_ids = set()
        for member in guild.members:
            if not member.bot:
                for role in member.roles:
                    all_member_role_ids.add(role.id)
        # 孤立したロールを削除
        deleted_count = 0
        for role in guild.roles:
            if role.id not in all_member_role_ids and role < guild.me.top_role and role != guild.default_role:
                try:
                    await role.delete(reason="Bot起動時のクリーンアップで孤立ロールを削除")
                    logger.info(f"起動時クリーンアップでロール {role.name} を削除しました")
                    deleted_count += 1
                except Exception as e:
                    logger.error(f"起動時クリーンアップでの削除に失敗: {role.name}: {e}")
        logger.info(f"起動時クリーンアップ完了: {deleted_count}個の孤立ロールを削除しました")
    
    # 定期タスクを起動
    bot.loop.create_task(ensure_personal_roles_exist())
    bot.loop.create_task(cleanup_orphaned_roles())


@bot.event
async def on_member_join(member):
    # Botは処理をスキップ
    if member.bot:
        return
    guild = member.guild
    role_name = member.display_name[:100]  # ロール名は最大100文字
    
    # 同名のロールが既に存在する場合は、既存のロールを再利用（競合回避）
    existing_role = None
    for role in guild.roles:
        if role.name == role_name and role < guild.me.top_role:
            existing_role = role
            logger.info(f"既存の個人ロール{role.name}を再利用します。")
            break
    
    if not existing_role:
        role_color = discord.Color.random()
        member_permissions = discord.Permissions()
        member_permissions.view_channel = True
        member_permissions.send_messages = True
        member_permissions.read_message_history = True
        member_permissions.add_reactions = True
        member_permissions.embed_links = True
        member_permissions.attach_files = True
        member_permissions.external_emojis = True
        member_permissions.external_stickers = True
        member_permissions.send_messages_in_threads = True
        member_permissions.send_polls = True
        member_permissions.use_application_commands = True
        member_permissions.mention_everyone = False
        member_permissions.connect = True
        member_permissions.speak = True
        member_permissions.stream = True
        member_permissions.use_voice_activation = True
        member_permissions.set_voice_channel_status = True
        member_permissions.use_embedded_activities = True
        member_permissions.create_expressions = True # エクスプレッションを作成権限を追加
        member_permissions.change_nickname = True

        # 新規メンバーのロール作成時もエラーハンドリングを強化
        try:
            new_role = await guild.create_role(
                name=role_name,
                color=role_color,
                permissions=member_permissions,
                reason=f"新規メンバー {member.display_name} の個人ロール作成（基本権限を付与）"
            )
            await member.add_roles(new_role)
            # 作成したロール数のメトリクスをインクリメント
            metrics['roles_created'] += 1
            logger.info(f"メンバー {member.display_name} に個人ロールを付与しました。ロールID: {new_role.id}")
            assigned_role = new_role
        except discord.Forbidden:
            logger.error(f"権限不足で新規メンバー {member.display_name} の個人ロールを作成できません。Botのロールがサーバー内で最上位に配置されているか、ロール管理権限が有効になっているか確認してください。")
            return  # ロール作成失敗時は後続の権限設定処理をスキップ
        except discord.HTTPException as e:
            logger.error(f"新規メンバー {member.display_name} の個人ロール作成中にDiscord APIエラーが発生しました。ステータスコード: {e.status}, エラーメッセージ: {e.text}")
            return
        except Exception as e:
            logger.error(f"新規メンバー {member.display_name} の個人ロール作成中に予期せぬエラーが発生しました: {type(e).__name__}: {str(e)}")
            return
    else:
        await member.add_roles(existing_role)
        logger.info(f"既存の個人ロール{role_name}を{member.display_name}に付与しました。")
        assigned_role = existing_role

    # アーカイブチャンネルは権限設定の対象から除外（サーバーオーナーとBotだけが閲覧可能）
    # ARCHIVE_CHANNEL_IDが0の場合はスキップ
    if ARCHIVE_CHANNEL_ID != 0:
        # すべてのチャンネルで閲覧権限をリトライ付きで設定
        for channel in guild.channels:
            # アーカイブチャンネルは権限設定をスキップ
            if channel.id == ARCHIVE_CHANNEL_ID:
                continue
            if channel.id in read_only_channel_ids:
                # 読み取り専用チャンネルは閲覧可、送信不可
                await set_permissions_with_retry(channel, assigned_role, {"view_channel": True, "send_messages": False}, logger=logger)
            else:
                # 通常チャンネルは閲覧も送信も可
                await set_permissions_with_retry(channel, assigned_role, {"view_channel": True, "send_messages": True}, logger=logger)
            logger.debug(f"チャンネル {channel.name} で {assigned_role.name} の権限を設定しました。")

@bot.event
async def on_member_update(before, after):
    # Botは処理をスキップ、ニックネームが変更された場合のみ処理
    if after.bot or before.display_name == after.display_name:
        return
    if before.display_name != after.display_name:
        guild = after.guild
        old_role_name = before.display_name
        new_role_name = after.display_name
        member = after

        # 古い名前のロールを検索して削除
        for role in guild.roles:
            if role.name == old_role_name:
                if role < guild.me.top_role:
                    await role.delete(reason=f"メンバー {old_role_name} がニックネームを変更したため古いロールを削除")
                    logger.info(f"メンバー {old_role_name} のニックネームが変更されたため、古いロール {old_role_name} を削除しました。")
                    break

        # 新しい名前で個人ロールを再作成
        role_color = discord.Color.random()
        member_permissions = discord.Permissions()
        member_permissions.view_channel = True
        member_permissions.send_messages = True
        member_permissions.read_message_history = True
        member_permissions.add_reactions = True
        member_permissions.embed_links = True
        member_permissions.attach_files = True
        member_permissions.external_emojis = True
        member_permissions.external_stickers = True
        member_permissions.send_messages_in_threads = True
        member_permissions.send_polls = True
        member_permissions.use_application_commands = True
        member_permissions.mention_everyone = False
        member_permissions.connect = True
        member_permissions.speak = True
        member_permissions.stream = True
        member_permissions.use_voice_activation = True
        member_permissions.set_voice_channel_status = True
        member_permissions.use_embedded_activities = True
        member_permissions.create_expressions = True # エクスプレッションを作成権限を追加
        member_permissions.change_nickname = True

        new_role = await guild.create_role(
            name=new_role_name,
            color=role_color,
            permissions=member_permissions,
            reason=f"メンバー {old_role_name} がニックネームを変更したため新しいロールを作成"
        )
        await member.add_roles(new_role)
        print(f"メンバー {new_role_name} の新しい個人ロール {new_role_name} を作成しました。")

        # まずすべてのチャンネルで閲覧権限を確実に有効化
        # ARCHIVE_CHANNEL_IDが0の場合はスキップ
        if ARCHIVE_CHANNEL_ID != 0:
            for channel in guild.channels:
                # 読み取り専用以外のチャンネルは通常権限、読み取り専用は送信不可
                if channel.id == ARCHIVE_CHANNEL_ID:
                    continue
                if channel.id in read_only_channel_ids:
                    await channel.set_permissions(new_role, view_channel=True, send_messages=False)
                else:
                    await channel.set_permissions(new_role, view_channel=True, send_messages=True)
                print(f"チャンネル {channel.name} で {new_role.name} の権限を設定しました。")

@bot.event
async def on_message(message):
    # デバッグ用: 受信したメッセージの情報をログに出力
    logger.info(f"メッセージ受信: チャンネルID={message.channel.id}, 作者={message.author.display_name}, 内容={message.content[:50]}")
    logger.info(f"PRIVATE_THREAD_ALLOWED_CHANNEL_IDSの値: {PRIVATE_THREAD_ALLOWED_CHANNEL_IDS}")
    
    # Botのメッセージは無視
    if message.author.bot:
        return
    
    # 愚痴・独り言チャンネルの場合の処理
    if message.channel.id in PRIVATE_THREAD_ALLOWED_CHANNEL_IDS:
        # 「プライベートスレッド」以外のメッセージは自動的に削除
        if "プライベートスレッド" not in message.content:
            await message.delete()
            return
        
        # 「プライベートスレッド」が含まれていたらスレッドを作成
        member = message.author
        # どのチャンネルで作成されたかでスレッド名を変える
        if message.channel.id == 1519537065992126485:  # 愚痴チャンネル (このIDは環境変数から取得すべきですが、ここでは仮にハードコード)
            thread_name = f"{member.display_name}の愚痴"
        else:  # 独り言チャンネル
            thread_name = f"{member.display_name}の独り言"
        
        # プライベートスレッドを作成（環境変数で設定したアーカイブ期間を使用）
        thread = await message.channel.create_thread(
            name=thread_name,
            auto_archive_duration=THREAD_AUTO_ARCHIVE_MINUTES,
            type=discord.ChannelType.private_thread
        )
        # スレッドにコマンド実行者を追加
        await thread.add_user(member)
        # スレッド内だけに本人に通知を送る（他の人には見えない）
        await thread.send(f"{member.mention} プライベートスレッドを作成しました！このスレッド内で自由に投稿できます。")
        # コマンドメッセージ自体も削除して誰が作ったか分からないようにする
        await message.delete()
        print(f"メンバー {member.display_name} のプライベートスレッドを作成しました。")
        return

# ボイスイベントをセットアップ
setup_voice_events(bot)

if not DISCORD_TOKEN:
    raise ValueError("環境変数にDISCORD_TOKENが設定されていません。.envファイルを確認してください。")

bot.run(DISCORD_TOKEN)