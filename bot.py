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

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('Botが正常に起動しました！')
    print('------')

@bot.event
async def on_member_join(member):
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

    read_only_channel_ids = [
        1520972406234153081,  # # 守ってほしい事
        1520972441151733911   # # お知らせ
    ]
    for channel_id in read_only_channel_ids:
        channel = guild.get_channel(channel_id)
        if channel:
            await channel.set_permissions(new_role, send_messages=False)
            print(f"チャンネル {channel.name} で {new_role.name} のメッセージ送信権限を無効にしました。")

@bot.event
async def on_member_remove(member):
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
    # ニックネームが変更された場合のみ処理
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

        # 読み取り専用チャンネルの権限も再設定
        read_only_channel_ids = [
            1520972406234153081,  # # 守ってほしい事
            1520972441151733911   # # お知らせ
        ]
        for channel_id in read_only_channel_ids:
            channel = guild.get_channel(channel_id)
            if channel:
                await channel.set_permissions(new_role, send_messages=False)
                print(f"チャンネル {channel.name} で {new_role.name} のメッセージ送信権限を無効にしました。")

if not DISCORD_TOKEN:
    raise ValueError("環境変数にDISCORD_TOKENが設定されていません。.envファイルを確認してください。")

bot.run(DISCORD_TOKEN)