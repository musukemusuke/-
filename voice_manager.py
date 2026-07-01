import re
import discord
from archive import archive_text_channel_history

# アーカイブ処理済みのテキストチャンネルIDを保存するセット（重複アーカイブ防止）
archived_channel_ids = set()

# ボイスチャンネルIDと紐づくテキストチャンネルIDのマップ（一時的なボイスチャンネルの名前変更対策）
voice_to_text_channel_map = {}

# 休止ボイスチャンネルIDリスト
IGNORE_VOICE_CHANNEL_IDS = [
    # 休止ボイスチャンネルのIDをここに記載
]

# Discordのチャンネル名は小文字・ハイフン区切りに自動変換されるので、同じように正規化する共通関数
def normalize_channel_name(name):
    # 日本語はそのまま、英数字以外をハイフンに置換して小文字化
    normalized = re.sub(r'[^a-zA-Z0-9\u3040-\u30ff\u4e00-\u9fff]+', '-', name).lower()
    # 連続するハイフンを単一に、先頭末尾のハイフンを削除
    normalized = re.sub(r'-+', '-', normalized).strip('-')
    return normalized

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
                        # 既にアーカイブ済みのチャンネルは処理をスキップ
                        if channel.id not in archived_channel_ids:
                            archived_channel_ids.add(channel.id)
                            # 削除前に履歴をアーカイブ
                            await archive_text_channel_history(channel, bot)
                            await channel.delete()
                            print(f"移動によりチャンネル {before.channel.name} にbot以外のメンバーがいなくなったので、聞き専用テキストチャンネル {channel.name} を削除しました。")
                        else:
                            print(f"テキストチャンネル{channel.name}は既にアーカイブ処理済みのため、重複処理をスキップしました。")
        
        # 新しくボイスチャンネルに参加した場合、または別チャンネルから移動してきた場合
        if after.channel is not None:
            # 休止チャンネルや「個室を作る」チャンネルでは処理をスキップ
            if after.channel.id in IGNORE_VOICE_CHANNEL_IDS or "休止" in after.channel.name or "個室を作る" in after.channel.name:
                return
            # 現在のボイスチャンネルの親カテゴリーを取得
            category = after.channel.category
            current_channel_normalized = normalize_channel_name(after.channel.name)
            # 対象の聞き専用テキストチャンネルを探す（名前が正規化後と完全一致するものを優先）
            listen_channel = None
            # まずdiscord.utils.getで直接検索を試みる（最も確実）
            listen_channel = discord.utils.get(category.text_channels, name=f"聞き専用-{current_channel_normalized}")
            # 見つからなければループで検索
            if not listen_channel:
                for channel in category.text_channels:
                    if channel.name.startswith("聞き専用-"):
                        channel_suffix = channel.name[len("聞き専用-"):]
                        if channel_suffix == current_channel_normalized:
                            listen_channel = channel
                            break
            print(f"ボイスチャンネル{after.channel.name}({current_channel_normalized})の入室処理: 既存テキストチャンネル={listen_channel.name if listen_channel else '未発見'}")
            
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
                    name=f"聞き専用-{current_channel_normalized}",
                    overwrites=permissions,
                    reason=f"{member.display_name}が{after.channel.name}に参加したので聞き専用テキストチャンネルを作成"
                )
                # ボイスチャンネルIDとテキストチャンネルIDを紐付けて保存（一時的なボイスチャンネル対策）
                voice_to_text_channel_map[after.channel.id] = listen_channel.id
                # 作成したチャンネルに案内メッセージを投稿
                await listen_channel.send(f"📢 こちらは{after.channel.mention}の聞き専用テキストチャンネルです。チャンネル内の会話を聞きながら、テキストでコメントしたい方はこちらで交流できます！")
                print(f"メンバー {member.display_name} が{after.channel.name}に参加したので、聞き専用テキストチャンネル {listen_channel.name} を作成しました。ボイスチャンネルID{after.channel.id}と紐付けました。")
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
                # 退出したボイスチャンネルに紐づく聞き専用テキストチャンネルを探す
                category = before.channel.category
                before_channel_normalized = normalize_channel_name(before.channel.name)
                listen_channel = None
                # まずdiscord.utils.getで直接検索を試みる
                listen_channel = discord.utils.get(category.text_channels, name=f"聞き専用-{before_channel_normalized}")
                # 見つからなければループで検索
                if not listen_channel:
                    for channel in category.text_channels:
                        if channel.name.startswith("聞き専用-"):
                            channel_suffix = channel.name[len("聞き専用-"):]
                            if channel_suffix == before_channel_normalized:
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
            # 一時的なボイスチャンネル（名前変更可能なチャンネル）の場合は、テキストチャンネルの名前更新だけを行い、重複作成を完全に防止
            # Discordの一時的なボイスチャンネルは名前変更時に内部的に削除→作成されることがあるため、既存のテキストチャンネルを再利用
            # 元の名前の聞き専用テキストチャンネルを探す（Discordのチャンネル名仕様に合わせて正規化）
            category = after.category
            before_normalized = normalize_channel_name(before.name)
            print(f"ボイスチャンネル名前変更検知: {before.name}→{after.name} (正規化前後: {before_normalized}→{normalize_channel_name(after.name)})")
            # カテゴリ内の全聞き専用チャンネルをログ出力（デバッグ用）
            all_listen_channels = [c.name for c in category.text_channels if c.name.startswith("聞き専用-")]
            print(f"現在のカテゴリ内の聞き専用チャンネル一覧: {all_listen_channels}")
            
            # まずdiscord.utils.getで完全一致検索を最初に試行（最も確実）
            old_listen_channel = discord.utils.get(category.text_channels, name=f"聞き専用-{before_normalized}")
            # 見つからなければループで全ての可能性を検索
            if not old_listen_channel:
                for channel in category.text_channels:
                    if channel.name.startswith("聞き専用-"):
                        # テキストチャンネル名の末尾部分を抽出して正規化後の名前と比較
                        channel_suffix = channel.name[len("聞き専用-"):]
                        print(f"チェック中: {channel.name} (suffix: {channel_suffix}) vs 検索条件: {before_normalized}")
                        if channel_suffix == before_normalized or channel_suffix == before.name.lower() or before_normalized in channel_suffix:
                            old_listen_channel = channel
                            print(f"一致する古いチャンネルを発見(ループ検索): {old_listen_channel.name}")
                            break
            # それでも見つからなければ、チャンネル名の前方一致で検索
            if not old_listen_channel:
                for channel in category.text_channels:
                    if channel.name.startswith(f"聞き専用-{before_normalized[:10]}"):
                        old_listen_channel = channel
                        print(f"前方一致で古いチャンネルを発見: {old_listen_channel.name}")
                        break
            if old_listen_channel is None:
                print(f"警告: 古い名前に一致するテキストチャンネルが見つかりませんでした。新規作成します。")
            # 常に古いテキストチャンネルを名前変更するだけにして、新規作成は絶対に行わない
            # これにより重複するテキストチャンネルの作成を完全に防止
            if old_listen_channel is not None:
                after_normalized = normalize_channel_name(after.name)
                new_name = f"聞き専用-{after_normalized}"
                await old_listen_channel.edit(name=new_name)
                # 名前変更時にボイスチャンネルのIDが変わっている場合、マップの紐付けを更新（Discordの一時的ボイスチャンネル対策）
                # 古いIDのマッピングが存在する場合は削除し、新しいIDに再紐付け
                if before.id in voice_to_text_channel_map:
                    del voice_to_text_channel_map[before.id]
                    print(f"古いボイスチャンネルID{before.id}のマッピングを削除しました")
                # 新しいボイスチャンネルIDにテキストチャンネルIDを紐付け
                voice_to_text_channel_map[after.id] = old_listen_channel.id
                print(f"新しいボイスチャンネルID{after.id}にテキストチャンネル{old_listen_channel.name}({old_listen_channel.id})を紐付けました")
                print(f"ボイスチャンネル {before.name} ({before_normalized}) が{after.name} ({after_normalized})に名前変更されたので、テキストチャンネルを{new_name}に変更しました。")
                # チャンネルのトピックやメッセージも更新（必要に応じて）
                await old_listen_channel.send(f"🔄 ボイスチャンネルの名前が{after.mention}に変更されたので、このテキストチャンネルの名前も{new_name}に更新しました！")
            else:
                # 古いチャンネルが見つからなくても、新規作成は行わずにログだけ出力
                print(f"警告: ボイスチャンネル{before.name}の名前を{after.name}に変更しましたが、紐づく古いテキストチャンネルが見つかりませんでした。重複作成を防ぐため新規作成はスキップします。")
                # 既存のテキストチャンネルの中に新しい名前のものが既に存在するか確認
                after_normalized = normalize_channel_name(after.name)
                new_name = f"聞き専用-{after_normalized}"
                existing_channel = discord.utils.get(category.text_channels, name=new_name)
                if existing_channel:
                    print(f"既に新しい名前のテキストチャンネル{new_name}が存在するため、処理を終了します。")

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
            deleted_channel_normalized = normalize_channel_name(channel.name)
            # マップに紐付けられたテキストチャンネルを優先的に取得（一時的なボイスチャンネル対策）
            text_channel = None
            if channel.id in voice_to_text_channel_map:
                # マップに登録されているテキストチャンネルIDからチャンネルを取得
                text_channel_id = voice_to_text_channel_map[channel.id]
                text_channel = discord.utils.get(category.text_channels, id=text_channel_id)
                print(f"マップから紐づくテキストチャンネルを発見: ID={text_channel_id}, 名前={text_channel.name if text_channel else '未発見'}")
                # 処理が終わったらマップから削除
                del voice_to_text_channel_map[channel.id]
            # マップになければ通常の名前検索
            if not text_channel:
                text_channel = discord.utils.get(category.text_channels, name=f"聞き専用-{deleted_channel_normalized}")
            if text_channel:
                # 既にアーカイブ済みのチャンネルは処理をスキップ
                if text_channel.id not in archived_channel_ids:
                    archived_channel_ids.add(text_channel.id)
                    try:
                        # 削除前に履歴をアーカイブ
                        await archive_text_channel_history(text_channel, bot)
                        await text_channel.delete()
                        print(f"ボイスチャンネル {channel.name} ({deleted_channel_normalized}) が削除されたので、紐づくテキストチャンネル {text_channel.name} も削除しました。")
                    except discord.errors.NotFound:
                        print(f"ボイスチャンネル {channel.name} に紐づくテキストチャンネルが既に削除されていたため、処理をスキップしました。")
                else:
                    print(f"テキストチャンネル{text_channel.name}は既にアーカイブ処理済みのため、重複処理をスキップしました。")
            else:
                # 直接検索で見つからなければループで検索
                for c in category.text_channels:
                    if c.name.startswith("聞き専用-"):
                        channel_suffix = c.name[len("聞き専用-"):]
                        if channel_suffix == deleted_channel_normalized:
                             # 既にアーカイブ済みのチャンネルは処理をスキップ
                             if c.id not in archived_channel_ids:
                                 archived_channel_ids.add(c.id)
                                 try:
                                     # 削除前に履歴をアーカイブ
                                     await archive_text_channel_history(c, bot)
                                     await c.delete()
                                     print(f"ボイスチャンネル {channel.name} ({deleted_channel_normalized}) が削除されたので、紐づくテキストチャンネル {c.name} も削除しました。")
                                 except discord.errors.NotFound:
                                     print(f"ボイスチャンネル {channel.name} に紐づくテキストチャンネルが既に削除されていたため、処理をスキップしました。")
                             else:
                                 print(f"テキストチャンネル{c.name}は既にアーカイブ処理済みのため、重複処理をスキップしました。")