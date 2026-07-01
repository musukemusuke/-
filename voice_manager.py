import discord
from archive import archive_text_channel_history

# 休止ボイスチャンネルIDリスト
IGNORE_VOICE_CHANNEL_IDS = [
    # 休止ボイスチャンネルのIDをここに記載
]

def setup_voice_events(bot):
    # ボイスチャンネルの状態が変更されたときのイベント（誰かが入退室したときに発火）
    @bot.event
    async def on_voice_state_update(member, before, after):
        # 休止チャンネルでは聞き専用チャンネルを作成しない
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
                        await archive_text_channel_history(channel, bot)
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
                        await archive_text_channel_history(channel, bot)
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
                    await archive_text_channel_history(text_channel, bot)
                    await text_channel.delete()
                    print(f"ボイスチャンネル {channel.name} が削除されたので、紐づくテキストチャンネル {text_channel.name} も削除しました。")