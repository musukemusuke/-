import os
import io
import discord
from discord.ext import commands
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

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

# テキストを描画して画像を生成する関数
def create_chat_image(messages, channel_name):
    # 画像の基本設定
    width = 800
    line_height = 30
    padding = 20
    title_height = 50
    # メッセージ1件あたりの行数を計算して高さを算出
    total_lines = sum(len(str(m.content).split('\n')) for m in messages) + 2  # タイトル分+フッター分
    height = title_height + (len(messages) + 2) * line_height + padding * 2
    
    # 背景画像を作成（黒背景のDiscord風）
    img = Image.new('RGB', (width, height), color=(54, 57, 63))
    draw = ImageDraw.Draw(img)
    
    # フォントを読み込み（システムの日本語フォントを使用）
    try:
        font = ImageFont.truetype("msgothic.ttc", 16)
        title_font = ImageFont.truetype("msgothic.ttc", 20)
    except:
        font = ImageFont.load_default()
        title_font = ImageFont.load_default()
    
    # タイトルを描画
    draw.text((padding, padding), f"アーカイブ: {channel_name}", fill=(255,255,255), font=title_font)
    current_y = padding + title_height
    
    # メッセージを1件ずつ描画
    for message in messages:
        author = message.author.display_name
        content = message.content if message.content else "(添付ファイル等)"
        # ユーザー名を青色で描画
        draw.text((padding, current_y), f"{author}:", fill=(114,137,218), font=font)
        # メッセージ内容を白で描画（長い場合は折り返し）
        text_width, _ = draw.textlength(f"{author}: ", font=font)
        draw.text((padding + text_width, current_y), content, fill=(255,255,255), font=font)
        current_y += line_height
    
    # フッターを描画
    draw.text((padding, current_y), f"全{len(messages)}件のメッセージ", fill=(185,187,190), font=font)
    
    # 画像をバイトストリームに保存
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    return img_byte_arr

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
    
    # チャット画像を生成
    try:
        img_file = create_chat_image(messages, channel.name)
        # 画像を添付して送信
        file = discord.File(img_file, filename=f"{channel.name}_archive.png")
        await archive_channel.send(f"📦 **アーカイブ: {channel.name}**（元ボイスチャンネル: {channel.name.replace('聞き専用-', '')}）", file=file)
        print(f"{channel.name} の画像アーカイブが完了しました。全{len(messages)}件のメッセージを画像に保存しました。")
    except Exception as e:
        print(f"画像生成中にエラーが発生しました: {e}")
        # 画像生成に失敗した場合はテキストでフォールバック
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
    # 休止チャンネルでは聞き専用チャンネルを作成しない
    IGNORE_VOICE_CHANNEL_IDS = [
        # 休止ボイスチャンネルのIDをここに記載
    ]
    # ボイスチャンネル間を移動した場合（前のチャンネルも後のチャンネルも存在する）
    if before.channel is not None and after.channel is not None and before.channel.id != after.channel.id:
        # 移動元のチャンネルの聞き専用テキストチャンネルの権限を削除
        before_category = before.channel.category
        before_listen_channel = None
        for channel in before_category.text_channels:
            if channel.name.startswith("聞き専用-") and channel.name.endswith(before.channel.name):
                before_listen_channel = channel
                break
        if before_listen_channel is not None and not member.bot:
            # 移動元メンバーの個人ロールを取得して権限を削除
            member_role = None
            for role in member.roles:
                if role.name == member.display_name:
                    member_role = role
                    break
            if member_role is not None:
                await before_listen_channel.set_permissions(member_role, send_messages=False, read_messages=False, read_message_history=False)
                print(f"メンバー {member.display_name} が{before.channel.name}から移動したので、元のテキストチャンネルの権限を削除しました。")
        
        # 移動後、移動元のチャンネルにbot以外のメンバーが残っているか確認
        before_human_members = [m for m in before.channel.members if not m.bot]
        if len(before_human_members) == 0:
            # 人間が誰もいなくなったら移動元の聞き専用テキストチャンネルを削除
            for channel in before_category.text_channels:
                if channel.name.startswith("聞き専用-") and channel.name.endswith(before.channel.name):
                    # 削除前に履歴をアーカイブ
                    await archive_text_channel_history(channel)
                    await channel.delete()
                    print(f"移動によりチャンネル {before.channel.name} にbot以外のメンバーがいなくなったので、聞き専用テキストチャンネル {channel.name} を削除しました。")
    
    # 新しくボイスチャンネルに参加した場合、または別チャンネルから移動してきた場合
    if after.channel is not None:
        # 休止チャンネルや「個室を作る」チャンネルでは処理をスキップ
        if after.channel.id in IGNORE_VOICE_CHANNEL_IDS or "休止" in after.channel.name or "個室を作る" in after.channel.name:
            return
        # 現在のボイスチャンネルの親カテゴリーを取得
        category = after.channel.category
        # 対象の聞き専用テキストチャンネルを探す
        listen_channel = None
        for channel in category.text_channels:
            if channel.name.startswith("聞き専用-") and channel.name.endswith(after.channel.name):
                listen_channel = channel
                break
        
        # まだ存在しなければテキストチャンネルとして作成
        if listen_channel is None:
            # サーバーのデフォルトロールを取得
            guild = after.channel.guild
            # デフォルトは閲覧も送信も不可、ボイスチャンネルに入っているメンバーだけが利用可能
            permissions = {
                guild.default_role: discord.PermissionOverwrite(
                    send_messages=False,      # デフォルトは送信不可
                    read_messages=False,     # デフォルトは閲覧も不可（入ってない人は見れない）
                    read_message_history=False
                )
            }
            # 現在ボイスチャンネルにいるメンバー全員の個人ロールに送信権限を付与
            for voice_member in after.channel.members:
                # Botは個人ロールを持っていないのでスキップ
                if voice_member.bot:
                    continue
                # メンバーの個人ロールを探す
                voice_member_role = None
                for role in voice_member.roles:
                    if role.name == voice_member.display_name:
                        voice_member_role = role
                        break
                # 個人ロールが見つかったら権限を設定
                if voice_member_role is not None:
                    permissions[voice_member_role] = discord.PermissionOverwrite(
                        send_messages=True,
                        read_messages=True,
                        read_message_history=True
                    )
            listen_channel = await category.create_text_channel(
                name=f"聞き専用-{after.channel.name}",
                overwrites=permissions,
                reason=f"{member.display_name}が{after.channel.name}に参加したので聞き専用テキストチャンネルを作成"
            )
            # 作成したチャンネルに案内メッセージを投稿
            await listen_channel.send(f"📢 こちらは{after.channel.mention}の聞き専用テキストチャンネルです。チャンネル内の会話を聞きながら、テキストでコメントしたい方はこちらで交流できます！")
            print(f"メンバー {member.display_name} が{after.channel.name}に参加したので、聞き専用テキストチャンネル {listen_channel.name} を作成しました。")
        else:
            # Botは個人ロールを持っていないのでスキップ
            if member.bot:
                return
            # メンバーの個人ロールを取得
            member_role = None
            for role in member.roles:
                if role.name == member.display_name:
                    member_role = role
                    break
            # 個人ロールに送信権限を付与
            if member_role is not None:
                await listen_channel.set_permissions(member_role, send_messages=True, read_messages=True, read_message_history=True)
                print(f"メンバー {member.display_name} が{after.channel.name}に参加したので、個人ロール {member_role.name} にテキストチャンネルの権限を付与しました。")
    
    # ボイスチャンネルから完全に退出した場合
    if after.channel is None and before.channel is not None:
        # 元のチャンネルにbot以外のメンバーがまだ残っているか確認
        remaining_humans = [m for m in before.channel.members if not m.bot]
        if len(remaining_humans) > 0:
            # まだ人間が残っているので、退出したメンバーの権限だけ削除
            category = before.channel.category
            listen_channel = None
            for channel in category.text_channels:
                if channel.name.startswith("聞き専用-") and channel.name.endswith(before.channel.name):
                    listen_channel = channel
                    break
            # チャンネルが存在する場合、退出したメンバーの個人ロールの権限を削除
            if listen_channel is not None and not member.bot:
                # メンバーの個人ロールを取得
                member_role = None
                for role in member.roles:
                    if role.name == member.display_name:
                        member_role = role
                        break
                # 個人ロールの権限を削除
                if member_role is not None:
                    await listen_channel.set_permissions(member_role, send_messages=False, read_messages=False, read_message_history=False)
                    print(f"メンバー {member.display_name} が{before.channel.name}から退出したので、個人ロール {member_role.name} のテキストチャンネル権限を削除しました。")
        else:
            # 人間のメンバーが誰もいなくなったので聞き専用テキストチャンネルを削除
            category = before.channel.category
            for channel in category.text_channels:
                if channel.name.startswith("聞き専用-") and channel.name.endswith(before.channel.name):
                    # 削除前に履歴をアーカイブ
                    await archive_text_channel_history(channel)
                    await channel.delete()
                    print(f"チャンネル {before.channel.name} にbot以外のメンバーがいなくなったので、聞き専用テキストチャンネル {channel.name} を削除しました。")

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
            # チャンネルのトピックやメッセージも更新（必要に応じて）
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
                # 削除前に履歴をアーカイブ
                await archive_text_channel_history(text_channel)
                await text_channel.delete()
                print(f"ボイスチャンネル {channel.name} が削除されたので、紐づくテキストチャンネル {text_channel.name} も削除しました。")

if not DISCORD_TOKEN:
    raise ValueError("環境変数にDISCORD_TOKENが設定されていません。.envファイルを確認してください。")

bot.run(DISCORD_TOKEN)