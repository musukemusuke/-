import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

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
                    await channel.delete()
                    print(f"チャンネル {before.channel.name} にbot以外のメンバーがいなくなったので、聞き専用テキストチャンネル {channel.name} を削除しました。")

if not DISCORD_TOKEN:
    raise ValueError("環境変数にDISCORD_TOKENが設定されていません。.envファイルを確認してください。")

bot.run(DISCORD_TOKEN)