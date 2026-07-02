import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import asyncio
import discord
from aiohttp import web
from utils import (
    setup_logger,
    set_permissions_with_retry,
    get_ids_from_env
)
from voice_manager import setup_voice_events
import os

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

# 環境変数から各種IDを読み込み
read_only_channel_ids = get_ids_from_env('READ_ONLY_CHANNEL_IDS')
PRIVATE_THREAD_ALLOWED_CHANNEL_IDS = get_ids_from_env('PRIVATE_THREAD_ALLOWED_CHANNEL_IDS')

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
# コマンド機能を使わないため、基本的なdiscord.Clientを使用
bot = discord.Client(intents=intents)

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
        member_permissions.change_nickname = True

        new_role = await guild.create_role(
            name=role_name,
            color=role_color,
            permissions=member_permissions,
            reason=f"Bot起動時にロールがなかったため {member.display_name} の個人ロールを作成"
        )
        await member.add_roles(new_role)
        logger.info(f"メンバー {member.display_name} に新しい個人ロールを付与しました。")

        # アーカイブチャンネルは権限設定の対象から除外（サーバーオーナーとBotだけが閲覧可能）
        archive_channel_id = int(os.getenv('ARCHIVE_CHANNEL_ID', '0'))
        # 全チャンネルの権限をリトライ付きで設定
        for channel in guild.channels:
            # アーカイブチャンネルは権限設定をスキップ
            if channel.id == archive_channel_id:
                continue
            if channel.id in read_only_channel_ids:
                await set_permissions_with_retry(channel, new_role, {"view_channel": True, "send_messages": False}, logger=logger)
            else:
                await set_permissions_with_retry(channel, new_role, {"view_channel": True, "send_messages": True}, logger=logger)
            logger.debug(f"チャンネル {channel.name} で {new_role.name} の権限を設定しました。")

# utilsからメトリクスをインポート
from utils import metrics

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
            logger.info(f"既存の個人ロール{role_name}を再利用します。")
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
        member_permissions.change_nickname = True

        new_role = await guild.create_role(
            name=role_name,
            color=role_color,
            permissions=member_permissions,
            reason=f"新規メンバー {member.display_name} の個人ロール作成（基本権限を付与）"
        )
        await member.add_roles(new_role)
        # 作成したロール数のメトリクスをインクリメント
        metrics['roles_created'] += 1
        logger.info(f"メンバー {member.display_name} に個人ロールを付与しました。")
        assigned_role = new_role
    else:
        await member.add_roles(existing_role)
        logger.info(f"既存の個人ロール{role_name}を{member.display_name}に付与しました。")
        assigned_role = existing_role

    # アーカイブチャンネルは権限設定の対象から除外（サーバーオーナーとBotだけが閲覧可能）
    archive_channel_id = int(os.getenv('ARCHIVE_CHANNEL_ID', '0'))
    # すべてのチャンネルで閲覧権限をリトライ付きで設定
    for channel in guild.channels:
        # アーカイブチャンネルは権限設定をスキップ
        if channel.id == archive_channel_id:
            continue
        if channel.id in read_only_channel_ids:
            # 読み取り専用チャンネルは閲覧可、送信不可
            await set_permissions_with_retry(channel, assigned_role, {"view_channel": True, "send_messages": False}, logger=logger)
        else:
            # 通常チャンネルは閲覧も送信も可
            await set_permissions_with_retry(channel, assigned_role, {"view_channel": True, "send_messages": True}, logger=logger)
        logger.debug(f"チャンネル {channel.name} で {assigned_role.name} の権限を設定しました。")

@bot.event
async def on_member_remove(member):
    # Botは処理をスキップ
    if member.bot:
        return
    guild = member.guild
    # ギルド内からメンバーの個人ロールを検索して削除
    # Discordはメンバー退出後にmember.rolesをクリアする場合があるため、ギルドのロール一覧から直接検索
    member_display_name = member.display_name
    logger.info(f"メンバー {member_display_name} が退出したため、個人ロールの検索を開始します。")
    
    for role in guild.roles:
        # Botのロールより下にあるロール、かつメンバーのニックネームと同じ名前のロールを削除
        if role.name == member_display_name and role < guild.me.top_role and role != guild.default_role:
            try:
                await role.delete(reason=f"メンバー {member_display_name} が退出したため個人ロールを削除")
                logger.info(f"メンバー {member_display_name} が退出したため、ロール {role.name} を削除しました。")
                break
            except Exception as e:
                logger.error(f"ロール {role.name} の削除に失敗しました: {e}")
    # 念のため、メンバーが退出前に持っていたロールも確認して削除（二重チェック）
    for role in member.roles:
        if role < guild.me.top_role and role != guild.default_role:
            try:
                await role.delete(reason=f"メンバー {member_display_name} が退出したため補足的に個人ロールを削除")
                logger.info(f"メンバー {member_display_name} の補足処理で、ロール {role.name} を削除しました。")
            except Exception as e:
                logger.debug(f"補足処理でのロール削除に失敗（既に削除済みの可能性があります）: {e}")

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
        for channel in guild.channels:
            # 読み取り専用以外のチャンネルは通常権限、読み取り専用は送信不可
            if channel.id in read_only_channel_ids:
                await channel.set_permissions(new_role, view_channel=True, send_messages=False)
            else:
                await channel.set_permissions(new_role, view_channel=True, send_messages=True)
                print(f"チャンネル {channel.name} で {new_role.name} の権限を設定しました。")

@bot.event
async def on_message(message):
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
        if message.channel.id == 1519537065992126485:  # 愚痴チャンネル
            thread_name = f"{member.display_name}の愚痴"
        else:  # 独り言チャンネル
            thread_name = f"{member.display_name}の独り言"
        
        # プライベートスレッドを作成
        thread = await message.channel.create_thread(
            name=thread_name,
            auto_archive_duration=60,  # 1時間メッセージがなければアーカイブ
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
    
    # 通常のコマンドも処理できるようにする


# ボイスイベントをセットアップ
setup_voice_events(bot)

if not DISCORD_TOKEN:
    raise ValueError("環境変数にDISCORD_TOKENが設定されていません。.envファイルを確認してください。")

bot.run(DISCORD_TOKEN)