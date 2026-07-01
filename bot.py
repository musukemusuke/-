import os
import traceback
import discord
from discord.ext import commands
from dotenv import load_dotenv
from archive_utils import create_chat_archive
from voice_utils import VoiceChannelMonitor

# .envファイルから環境変数を読み込み
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# 読み取り専用にするチャンネルIDを定義（グローバルで統一管理）
read_only_channel_ids = [
    1520972406234153081,  # # 守ってほしい事
    1520972441151733911   # # お知らせ
]
# プライベートスレッド作成を許可するチャンネルID（愚痴チャンネルと独り言チャンネルの2つを追加）
PRIVATE_THREAD_ALLOWED_CHANNEL_IDS = [
    1519537043921834094,  # #独り言チャンネル
    1519537065992126485   # #愚痴チャンネル
]

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('Botが正常に起動しました！')
    print('------')

    # Bot起動時に、すでにサーバーにいるのに個人ロールがないメンバーをチェックして付与
    for guild in bot.guilds:
        print(f"サーバー {guild.name} のメンバーをチェックしています...")
        for member in guild.members:
            # Botはスキップ、すでに個人ロールを持っているメンバーもスキップ
            if member.bot:
                continue
            # メンバーが自分の名前のロールを持っているか確認
            # ロール名は最大100文字なので切り詰める
            role_name = member.display_name[:100]
            has_role = any(role.name == role_name for role in member.roles)
            if not has_role:
                print(f"メンバー {member.display_name} にロールが付与されていないので作成します...")
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
                print(f"メンバー {member.display_name} に新しい個人ロールを付与しました。")

                # 全チャンネルの権限を設定
                for channel in guild.channels:
                    if channel.id in read_only_channel_ids:
                        await channel.set_permissions(new_role, view_channel=True, send_messages=False)
                    else:
                        await channel.set_permissions(new_role, view_channel=True, send_messages=True)
                    print(f"チャンネル {channel.name} で {new_role.name} の権限を設定しました。")
        print(f"サーバー {guild.name} のメンバーチェックが完了しました。")

@bot.event
async def on_member_join(member):
    # Botは処理をスキップ
    if member.bot:
        return
    guild = member.guild
    role_name = member.display_name
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

    # すべてのチャンネルで閲覧権限を確実に有効化
    for channel in guild.channels:
        if channel.id in read_only_channel_ids:
            # 読み取り専用チャンネルは閲覧可、送信不可
            await channel.set_permissions(new_role, view_channel=True, send_messages=False)
        else:
            # 通常チャンネルは閲覧も送信も可
            await channel.set_permissions(new_role, view_channel=True, send_messages=True)
        print(f"チャンネル {channel.name} で {new_role.name} の権限を設定しました。")

@bot.event
async def on_member_remove(member):
    # Botは処理をスキップ
    if member.bot:
        return
    guild = member.guild
    # 退出したメンバーの名前と一致するロールを検索して削除
    for role in guild.roles:
        if role.name == member.display_name:
            # Bot自身より下位のロールのみ削除可能（権限の問題を回避）
            if role < guild.me.top_role:
                await role.delete(reason=f"メンバー {member.display_name} が退出したため個人ロールを削除")
                print(f"メンバー {member.display_name} が退出したため、ロール {role.name} を削除しました。")
                break

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
                    print(f"メンバー {old_role_name} のニックネームが変更されたため、古いロール {old_role_name} を削除しました。")
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
            auto_archive_duration=1440,  # 1日間メッセージがなければアーカイブ
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
    await bot.process_commands(message)

# 聞き専用テキストチャンネルの履歴をアーカイブするチャンネルID
ARCHIVE_CHANNEL_ID = 1521780512795132015  # アーカイブ用チャンネルのID

# ボイスチャンネル監視で無視するチャンネルID（休憩所などの常設ボイスチャンネル）
IGNORE_VOICE_CHANNEL_IDS = [
    # ここに休憩所などの常設ボイスチャンネルIDを追加してください
]

# VoiceChannelMonitorのインスタンスを作成
voice_monitor = VoiceChannelMonitor(bot, IGNORE_VOICE_CHANNEL_IDS)



# テキストチャンネルのメッセージ履歴を画像でアーカイブチャンネルに送信する関数
async def archive_text_channel_history(channel):
    if ARCHIVE_CHANNEL_ID == 0:
        print("アーカイブチャンネルIDが設定されていないため、履歴を保存できませんでした。")
        return
    archive_channel = bot.get_channel(ARCHIVE_CHANNEL_ID)
    if not archive_channel or not isinstance(archive_channel, discord.TextChannel):
        print("アーカイブチャンネルが見つからないか、テキストチャンネルではありません。")
        return
    
    # チャンネルのメッセージを全て取得（古い順に並べ替え）
    messages = []
    async for message in channel.history(limit=None, oldest_first=True):
        if not message.author.bot:  # botのメッセージは除外
            messages.append(message)
    
    if not messages:
        print(f"{channel.name} のメッセージは0件だったのでアーカイブしませんでした。")
        return
    
    # チャットPDFを生成
    try:
        print(f"PDF生成開始: {channel.name}, メッセージ数: {len(messages)}")
        pdf_file, img_file = create_chat_archive(messages, channel.name)
        print("PDF生成完了、ファイルオブジェクト作成")
        # 添付ファイルを準備
        files = []
        pdf_discord_file = discord.File(pdf_file, filename=f"{channel.name}_archive.pdf")
        files.append(pdf_discord_file)
        # 画像が生成できていれば追加で送信
        if img_file:
            img_discord_file = discord.File(img_file, filename=f"{channel.name}_archive.png")
            files.append(img_discord_file)
        print("discord.File作成完了、送信開始")
        await archive_channel.send(f"📦 **アーカイブ: {channel.name}**（元ボイスチャンネル: {channel.name.replace('聞き専用-', '')}）", files=files)
        print(f"{channel.name} のアーカイブが完了しました。全{len(messages)}件のメッセージを保存しました。")
    except Exception as e:
        print(f"PDF生成中にエラーが発生しました: {e}")
        print(traceback.format_exc())
        # PDF生成に失敗した場合はテキストでフォールバック
        await archive_channel.send(f"📦 **アーカイブ: {channel.name}**（元ボイスチャンネル: {channel.name.replace('聞き専用-', '')}）")
        for message in messages:
            content = f"**{message.author.display_name}**: {message.content}" if message.content else f"**{message.author.display_name}**: (添付ファイル等)"
            if len(content) > 1900:
                for i in range(0, len(content), 1900):
                    await archive_channel.send(content[i:i+1900])
            else:
                await archive_channel.send(content)
        await archive_channel.send(f"✅ {channel.name} のテキストアーカイブが完了しました。全{len(messages)}件のメッセージを保存しました。\n---")

# ボイスチャンネルの状態が変更されたときのイベント（誰かが入退室したときに発火）
@bot.event
async def on_voice_state_update(member, before, after):
    # 聞き専用チャンネルの作成処理
    await voice_monitor.check_and_create_listen_channel(member, before, after)
    # ボイスチャンネルが空になった場合の削除処理
    listen_channel = await voice_monitor.check_and_delete_listen_channel(member, before, after)
    # 削除対象の聞き専用チャンネルが取得できたらアーカイブしてから削除
    if listen_channel:
        await archive_text_channel_history(listen_channel)
        await listen_channel.delete()
        print(f"タイマー経過により聞き専用テキストチャンネル {listen_channel.name} を削除しました。")

# サーバーのチャンネルが更新されたときのイベント（名前変更などを検知）
@bot.event
async def on_guild_channel_update(before, after):
    # ボイスチャンネルの名前が変更された場合
    if isinstance(before, discord.VoiceChannel) and isinstance(after, discord.VoiceChannel) and before.name != after.name:
        # 休止チャンネルや「個室を作る」チャンネルは処理しない
        if "休止" in after.name or "個室を作る" in after.name:
            return
        # 元の名前の聞き専用テキストチャンネルを探す
        category = after.category
        old_listen_channel = None
        for channel in category.text_channels:
            if channel.name.startswith("聞き専用-") and channel.name.endswith(before.name):
                old_listen_channel = channel
                break
        # 古いテキストチャンネルが存在する場合、新しい名前に変更
        if old_listen_channel is not None:
            new_name = f"聞き専用-{after.name}"
            await old_listen_channel.edit(name=new_name)
            print(f"ボイスチャンネル {before.name} が{after.name}に名前変更されたので、テキストチャンネルを{new_name}に変更しました。")
            await old_listen_channel.send(f"🔄 ボイスチャンネルの名前が{after.mention}に変更されたので、このテキストチャンネルの名前も{new_name}に更新しました！")

# サーバーのチャンネルが削除されたときのイベント
@bot.event
async def on_guild_channel_delete(channel):
    # 削除されたのがボイスチャンネルの場合
    if isinstance(channel, discord.VoiceChannel):
        # 休止チャンネルや「個室を作る」チャンネルは処理しない
        if "休止" in channel.name or "個室を作る" in channel.name:
            return
        # 削除されたボイスチャンネルに紐づく聞き専用テキストチャンネルを探して削除
        category = channel.category
        if category is None:
            return
        for text_channel in category.text_channels:
            if text_channel.name.startswith("聞き専用-") and text_channel.name.endswith(channel.name):
                await archive_text_channel_history(text_channel)
                await text_channel.delete()
                print(f"ボイスチャンネル {channel.name} が削除されたので、紐づくテキストチャンネル {text_channel.name} も削除しました。")

if not DISCORD_TOKEN:
    raise ValueError("環境変数にDISCORD_TOKENが設定されていません。.envファイルを確認してください。")

bot.run(DISCORD_TOKEN)