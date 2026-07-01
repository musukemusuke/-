import discord
from archive import archive_text_channel_history

# ボイスチャンネル関連の処理を管理するモジュール
async def handle_guild_channel_update(bot, before, after):
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

async def handle_voice_state_update(bot, member, before, after, IGNORE_VOICE_CHANNEL_IDS, ARCHIVE_CHANNEL_ID):
    # ボイスチャンネル間を移動した場合（前のチャンネルも後のチャンネルも存在する）
    if before.channel is not None and after.channel is not None and before.channel.id != after.channel.id:
        # 移動元のチャンネルの聞き専用テキストチャンネルの権限を削除
        before_category = before.channel.category
        before_listen_channel = None
        # 移動元のカテゴリ内に「聞き専用-チャンネル名」のテキストチャンネルが存在するか確認
        for text_channel in before_category.text_channels:
            if text_channel.name == f"聞き専用-{before.channel.name}":
                before_listen_channel = text_channel
                break
        if before_listen_channel:
            # 全員が退出したら権限を削除してアーカイブ
            if len(before.channel.members) == 0:
                try:
                    # チャンネルをアーカイブ（履歴を保存）
                    await archive_text_channel_history(bot, before_listen_channel, ARCHIVE_CHANNEL_ID)
                    # 聞き専用チャンネルを削除
                    await before_listen_channel.delete()
                    print(f"{before_listen_channel.name} を削除しました（移動後に空になったため）")
                except Exception as e:
                    print(f"移動元の聞き専用チャンネル処理でエラー: {e}")
        # 移動先のチャンネルに聞き専用テキストチャンネルを作成
        after_category = after.channel.category
        after_listen_channel = None
        # 移動先のカテゴリ内に「聞き専用-チャンネル名」のテキストチャンネルが存在するか確認
        for text_channel in after_category.text_channels:
            if text_channel.name == f"聞き専用-{after.channel.name}":
                after_listen_channel = text_channel
                break
        if not after_listen_channel:
            # チャンネルが存在しない場合は新規作成
            overwrites = {
                after_category.guild.default_role: discord.PermissionOverwrite(send_messages=False),
                member: discord.PermissionOverwrite(send_messages=True)
            }
            # ボイスチャンネルにいる全メンバーに送信権限を付与
            for voice_member in after.channel.members:
                overwrites[voice_member] = discord.PermissionOverwrite(send_messages=True)
            try:
                new_channel = await after_category.create_text_channel(
                    name=f"聞き専用-{after.channel.name}",
                    overwrites=overwrites,
                    topic=f"{after.channel.name} の聞き専用チャンネルです。"
                )
                await new_channel.send(f"🔊 {after.channel.name} の聞き専用チャンネルが作成されました。参加しているメンバーはメッセージを送信できます。")
                print(f"{new_channel.name} を作成しました（{member.display_name} が {after.channel.name} に移動したため）")
            except Exception as e:
                print(f"移動先の聞き専用チャンネル作成でエラー: {e}")
    # 誰かがボイスチャンネルに入室した場合
    elif before.channel is None and after.channel is not None:
        # 休止チャンネルの場合は処理しない
        if after.channel.id in IGNORE_VOICE_CHANNEL_IDS:
            return
        category = after.channel.category
        listen_channel = None
        # カテゴリ内に「聞き専用-チャンネル名」のテキストチャンネルが存在するか確認
        for text_channel in category.text_channels:
            if text_channel.name == f"聞き専用-{after.channel.name}":
                listen_channel = text_channel
                break
        if not listen_channel:
            # チャンネルが存在しない場合は新規作成
            overwrites = {
                category.guild.default_role: discord.PermissionOverwrite(send_messages=False),
                member: discord.PermissionOverwrite(send_messages=True)
            }
            # 現在ボイスチャンネルにいる全メンバーに送信権限を付与
            for voice_member in after.channel.members:
                overwrites[voice_member] = discord.PermissionOverwrite(send_messages=True)
            try:
                new_channel = await category.create_text_channel(
                    name=f"聞き専用-{after.channel.name}",
                    overwrites=overwrites,
                    topic=f"{after.channel.name} の聞き専用チャンネルです。"
                )
                await new_channel.send(f"🔊 {after.channel.name} の聞き専用チャンネルが作成されました。参加しているメンバーはメッセージを送信できます。")
                print(f"{new_channel.name} を作成しました（{member.display_name} が入室したため）")
            except Exception as e:
                print(f"聞き専用チャンネル作成でエラー: {e}")
        else:
            # 既存のチャンネルが存在する場合は権限に入室したメンバーを追加
            overwrites = listen_channel.overwrites
            if member not in overwrites:
                overwrites[member] = discord.PermissionOverwrite(send_messages=True)
                await listen_channel.edit(overwrites=overwrites)
                print(f"{listen_channel.name} に {member.display_name} の権限を追加しました")
    # 誰かがボイスチャンネルから退室した場合
    elif before.channel is not None and after.channel is None:
        # 休止チャンネルの場合は処理しない
        if before.channel.id in IGNORE_VOICE_CHANNEL_IDS:
            return
        category = before.channel.category
        listen_channel = None
        # カテゴリ内に「聞き専用-チャンネル名」のテキストチャンネルが存在するか確認
        for text_channel in category.text_channels:
            if text_channel.name == f"聞き専用-{before.channel.name}":
                listen_channel = text_channel
                break
        if listen_channel:
            # 全員が退出したら権限を削除してアーカイブ
            if len(before.channel.members) == 0:
                try:
                    # チャンネルをアーカイブ（履歴を保存）
                    await archive_text_channel_history(bot, listen_channel, ARCHIVE_CHANNEL_ID)
                    # 聞き専用チャンネルを削除
                    await listen_channel.delete()
                    print(f"{listen_channel.name} を削除しました（全員が退室したため）")
                except Exception as e:
                    print(f"退室時の聞き専用チャンネル処理でエラー: {e}")
            else:
                # 退室したメンバーの権限を削除
                overwrites = listen_channel.overwrites
                if member in overwrites:
                    del overwrites[member]
                    await listen_channel.edit(overwrites=overwrites)
                    print(f"{listen_channel.name} から {member.display_name} の権限を削除しました")

async def handle_guild_channel_delete(bot, channel, ARCHIVE_CHANNEL_ID):
    # ボイスチャンネルが削除された場合、対応する聞き専用テキストチャンネルもアーカイブして削除
    if isinstance(channel, discord.VoiceChannel):
        category = channel.category
        listen_channel = None
        for text_channel in category.text_channels:
            if text_channel.name == f"聞き専用-{channel.name}":
                listen_channel = text_channel
                break
        if listen_channel:
            try:
                # チャンネルをアーカイブ（履歴を保存）
                await archive_text_channel_history(bot, listen_channel, ARCHIVE_CHANNEL_ID)
                # 聞き専用チャンネルを削除
                await listen_channel.delete()
                print(f"{listen_channel.name} を削除しました（元のボイスチャンネルが削除されたため）")
            except Exception as e:
                print(f"ボイスチャンネル削除時の聞き専用チャンネル処理でエラー: {e}")