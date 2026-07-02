import asyncio
import discord
from archive import archive_text_channel_history

# アーカイブ処理済みのテキストチャンネルIDを保存するセット（重複アーカイブ防止）
archived_channel_ids = set()

# 休止ボイスチャンネルIDリスト
IGNORE_VOICE_CHANNEL_IDS = [
    # 休止ボイスチャンネルのIDをここに記載
]

def setup_voice_events(bot):
    # 休止チャンネルと個室作成チャンネルのテキストチャットを使用不可にする初期化処理
    async def disable_chat_for_special_channels(guild):
        for voice_channel in guild.voice_channels:
            if "休止" in voice_channel.name or "個室を作る" in voice_channel.name:
                # 紐づくテキストチャンネルを検索（サーバー全体から検索）
                text_channel = None
                all_text_channels = [c for c in guild.text_channels]
                for channel in all_text_channels:
                    if hasattr(channel, 'voice_channel') and channel.voice_channel == voice_channel:
                        text_channel = channel
                        break
                if not text_channel:
                    for channel in all_text_channels:
                        if channel.name == voice_channel.name or channel.name.startswith(voice_channel.name):
                            text_channel = channel
                            break
                # テキストチャンネルが存在すればeveryoneの送信権限を無効化
                if text_channel:
                    await text_channel.set_permissions(guild.default_role, send_messages=False, read_messages=True)
                    print(f"特殊チャンネル{voice_channel.name}のテキストチャット送信権限を無効化しました")

    # Discord標準のボイスチャンネル専用テキストチャンネルを利用したアーカイブ処理
    # ボイスチャンネルの状態が変更されたときのイベント（誰かが入退室したときに発火）
    @bot.event
    async def on_voice_state_update(member, before, after):
        # ボイスチャンネルに誰かが参加したタイミングで特殊チャンネルの権限を再確認
        if after.channel is not None:
            if "休止" in after.channel.name or "個室を作る" in after.channel.name:
                text_channel = None
                # サーバー全体の全テキストチャンネルから検索
                all_text_channels = [c for c in after.channel.guild.text_channels]
                for channel in all_text_channels:
                    if hasattr(channel, 'voice_channel') and channel.voice_channel == after.channel:
                        text_channel = channel
                        break
                if not text_channel:
                    for channel in all_text_channels:
                        if channel.name == after.channel.name or channel.name.startswith(after.channel.name):
                            text_channel = channel
                            break
                if text_channel:
                    await text_channel.set_permissions(after.channel.guild.default_role, send_messages=False, read_messages=True)
        # ボイスチャンネルから完全に退出し、誰も残っていない場合にアーカイブ処理を実行
        if after.channel is None and before.channel is not None:
            # 休止チャンネルはアーカイブ処理をスキップ
            if before.channel.id in IGNORE_VOICE_CHANNEL_IDS or "休止" in before.channel.name or "個室を作る" in before.channel.name:
                return
            
            # ボイスチャンネルに残っている人間メンバーを確認
            remaining_humans = [m for m in before.channel.members if not m.bot]
            print(f"[デバッグ] {before.channel.name} 退出検知: 残りの人間メンバー数={len(remaining_humans)}, メンバー一覧={[m.display_name for m in remaining_humans]}")
            if len(remaining_humans) == 0:
                print(f"[デバッグ] {before.channel.name} の人間メンバーが0になったのでアーカイブ処理を開始")
                # ボイスチャンネルに紐づく標準テキストチャンネルを検索（discord.pyバージョン互換性対策）
                text_channel = None
                # サーバー全体の全テキストチャンネルから検索（カテゴリーが分かれていても検出可能）
                all_text_channels = [c for c in before.channel.guild.text_channels]
                all_categories = [c.name for c in before.channel.guild.categories]
                print(f"[デバッグ] サーバー内の全カテゴリー一覧: {all_categories}")
                print(f"[デバッグ] サーバー内の全テキストチャンネル一覧: {[c.name for c in all_text_channels]}")
                # 全テキストチャンネルから、ボイスチャンネルに紐づくものを探す
                for channel in all_text_channels:
                    # Discord標準のボイス専用テキストチャンネルは、元のボイスチャンネルの名前を基に作成され、かつvoice_channel属性で紐付けられている
                    print(f"[デバッグ] チェック中: {channel.name}, hasattr(voice_channel)={hasattr(channel, 'voice_channel')}")
                    if hasattr(channel, 'voice_channel') and channel.voice_channel == before.channel:
                        text_channel = channel
                        print(f"[デバッグ] voice_channel属性でテキストチャンネルを発見: {text_channel.name}")
                        break
                # 旧バージョンでvoice_channel属性がない場合は名前で推測して検索
                if not text_channel:
                    print(f"[デバッグ] voice_channel属性が見つからなかったので名前で検索開始")
                    for channel in all_text_channels:
                        if channel.name == before.channel.name or channel.name.startswith(before.channel.name) or before.channel.name in channel.name:
                            text_channel = channel
                            print(f"[デバッグ] 名前一致でテキストチャンネルを発見: {text_channel.name}")
                            break
                if not text_channel:
                    print(f"[エラー] {before.channel.name} に紐づくテキストチャンネルが見つかりませんでした。アーカイブ処理をスキップします。")
                
                if text_channel and text_channel.id not in archived_channel_ids:
                    archived_channel_ids.add(text_channel.id)
                    print(f"ボイスチャンネル{before.channel.name}に誰もいなくなったので、ボイス紐付きテキストチャンネル{text_channel.name}をアーカイブ開始")
                    # メッセージ履歴をPDFにアーカイブ
                    await archive_text_channel_history(text_channel, bot)
                    print(f"アーカイブ完了: {before.channel.name}のボイスチャット履歴を保存しました")
                    # 常設ボイスでない場合（一時的なボイス）はテキストチャンネルも削除
                    if "フリー" in before.channel.name or "まったり" in before.channel.name or "一時的" in before.channel.name:
                        await text_channel.delete()
                        print(f"一時的ボイスチャンネル{before.channel.name}に紐づくテキストチャンネルを削除しました")
                    # 常設ボイスの場合はメッセージだけ削除して次回に備える
                    else:
                        await text_channel.purge()
                        print(f"常設ボイスチャンネル{before.channel.name}のテキストチャンネルのメッセージをクリアしました")
                    # アーカイブ完了後、次回会話用にテキストチャンネルのIDをマップから削除して再アーカイブ可能に
                    if text_channel.id in archived_channel_ids:
                        archived_channel_ids.remove(text_channel.id)

    # ボイスチャンネルが削除されたときのイベント（一時的なボイスチャンネルの削除に対応）
    @bot.event
    async def on_guild_channel_delete(channel):
        if isinstance(channel, discord.VoiceChannel):
            # 休止チャンネルはアーカイブ処理をスキップ
            if channel.id in IGNORE_VOICE_CHANNEL_IDS or "休止" in channel.name or "個室を作る" in channel.name:
                return
            
            # 削除されたボイスチャンネルに紐づく標準テキストチャンネルを検索（discord.pyバージョン互換性対策）
            text_channel = None
            # サーバー全体の全テキストチャンネルから検索（カテゴリが分かれていても検出可能）
            all_text_channels = [c for c in channel.guild.text_channels]
            print(f"[デバッグ] 削除されたボイスチャンネル{channel.name}の検索: サーバー内全テキストチャンネル={[c.name for c in all_text_channels]}")
            # 全テキストチャンネルから、ボイスチャンネルに紐づくものを探す
            for category_channel in all_text_channels:
                if hasattr(category_channel, 'voice_channel') and category_channel.voice_channel == channel:
                    text_channel = category_channel
                    print(f"[デバッグ] 削除ボイスに紐づくテキストチャンネルを発見: {text_channel.name}")
                    break
            # 旧バージョンでvoice_channel属性がない場合は名前で推測して検索
            if not text_channel:
                for category_channel in all_text_channels:
                    if category_channel.name == channel.name or category_channel.name.startswith(channel.name) or channel.name in category_channel.name:
                        text_channel = category_channel
                        print(f"[デバッグ] 名前一致で削除ボイスのテキストチャンネルを発見: {text_channel.name}")
                        break
            
            if text_channel and text_channel.id not in archived_channel_ids:
                archived_channel_ids.add(text_channel.id)
                print(f"ボイスチャンネル{channel.name}が削除されたので、ボイス紐付きテキストチャンネル{text_channel.name}をアーカイブ開始")
                # メッセージ履歴をPDFにアーカイブ
                await archive_text_channel_history(text_channel, bot)
                print(f"アーカイブ完了: {channel.name}のボイスチャット履歴を保存しました")
                # 常設ボイスでない場合（一時的なボイス）はテキストチャンネルも削除
                if "フリー" in channel.name or "まったり" in channel.name or "一時的" in channel.name:
                    await text_channel.delete()
                    print(f"一時的ボイスチャンネル{channel.name}に紐づくテキストチャンネルを削除しました")
                # 常設ボイスの場合はメッセージだけ削除して次回に備える
                else:
                    await text_channel.purge()
                    print(f"常設ボイスチャンネル{channel.name}のテキストチャンネルのメッセージをクリアしました")
                # アーカイブ完了後、次回会話用にテキストチャンネルのIDをマップから削除して再アーカイブ可能に
                if text_channel.id in archived_channel_ids:
                    archived_channel_ids.remove(text_channel.id)

    # Bot起動時に全サーバーの特殊チャンネルの権限を一括設定
    @bot.event
    async def on_ready():
        print("Botが起動しました。特殊チャンネルのテキストチャット権限を設定します...")
        for guild in bot.guilds:
            await disable_chat_for_special_channels(guild)
        print("全ての特殊チャンネルの権限設定が完了しました。")