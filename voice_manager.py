import asyncio
import discord
from archive import archive_text_channel_history

# アーカイブ処理済みのテキストチャンネルIDを保存するセット（重複アーカイブ防止）
archived_channel_ids = set()
# 特殊チャンネルの処理済みIDをキャッシュ（重複処理防止）
processed_special_channels = set()

# 休止ボイスチャンネルIDリスト
IGNORE_VOICE_CHANNEL_IDS = [
    # 休止ボイスチャンネルのIDをここに記載
]

# 常設ボイスチャンネルの名前ホワイトリスト（このリストに含まれるチャンネルのみメッセージクリアを実行）
PERMANENT_VOICE_NAMES = ["フリー", "まったり"]

def setup_voice_events(bot):
    # 休止チャンネルと個室作成チャンネルのテキストチャットを使用不可にする初期化処理
    async def disable_chat_for_special_channels(guild):
        # Discordのvoice_channel属性で直接検索することでループ回数を削減
        for text_channel in guild.text_channels:
            if hasattr(text_channel, 'voice_channel') and text_channel.voice_channel:
                voice_channel = text_channel.voice_channel
                if voice_channel.id not in processed_special_channels and ("休止" in voice_channel.name or "個室を作る" in voice_channel.name):
                    processed_special_channels.add(voice_channel.id)
                    await text_channel.set_permissions(guild.default_role, send_messages=False, read_messages=True)
                    print(f"特殊チャンネル{voice_channel.name}のテキストチャット送信権限を無効化しました")

    # Discord標準のボイスチャンネル専用テキストチャンネルを利用したアーカイブ処理
    # ボイスチャンネルの状態が変更されたときのイベント（誰かが入退室したときに発火）
    @bot.event
    async def on_voice_state_update(member, before, after):
        # 参加時の重複権限設定処理を削除（Bot起動時に1回だけ実行済み）
        # ボイスチャンネルから完全に退出し、誰も残っていない場合にアーカイブ処理を実行
        if after.channel is None and before.channel is not None:
            # 休止チャンネルはアーカイブ処理をスキップ
            if before.channel.id in IGNORE_VOICE_CHANNEL_IDS or "休止" in before.channel.name or "個室を作る" in before.channel.name:
                return
            
            # ボイスチャンネルに残っている人間メンバーを確認（ジェネレータで効率化）
            remaining_humans = sum(1 for m in before.channel.members if not m.bot)
            if remaining_humans == 0:
                print(f"[デバッグ] {before.channel.name} の人間メンバーが0になったのでアーカイブ処理を開始")
                # ボイスチャンネル自体を対象に、ボイスチャンネル内のチャットをアーカイブ
                target_channel = before.channel
                if target_channel and target_channel.id not in archived_channel_ids:
                    archived_channel_ids.add(target_channel.id)
                    print(f"ボイスチャンネル{before.channel.name}に誰もいなくなったので、ボイスチャンネル本体のチャットをアーカイブ開始")
                    try:
                        # メッセージ履歴をPDFにアーカイブ（ボイスチャンネルでもhistory()が使用可能）
                        await archive_text_channel_history(target_channel, bot)
                        print(f"アーカイブ完了: {before.channel.name}のボイスチャット履歴を保存しました")
                        # 常設ボイスの場合はメッセージだけ削除して次回に備える（ホワイトリストで判定）
                        if any(name in before.channel.name for name in PERMANENT_VOICE_NAMES):
                            try:
                                # チャンネルがまだ存在するか確認してからpurgeを実行
                                channel_exists = any(c.id == target_channel.id for c in target_channel.guild.voice_channels)
                                if channel_exists:
                                    await target_channel.purge()
                                    print(f"常設ボイスチャンネル{before.channel.name}のチャットメッセージをクリアしました")
                                else:
                                    print(f"[警告] 常設ボイスチャンネル{before.channel.name}が既に削除されていたため、メッセージクリアをスキップしました")
                            except Exception as e:
                                print(f"[エラー] 常設ボイスチャンネル{before.channel.name}のメッセージクリア中にエラーが発生: {e}")
                    except Exception as e:
                        print(f"[エラー] ボイスチャンネル{before.channel.name}のアーカイブ処理中にエラーが発生: {e}")
                    finally:
                        # アーカイブ完了後（エラーが発生しても）、次回会話用にIDをマップから削除して再アーカイブ可能に
                        if target_channel.id in archived_channel_ids:
                            archived_channel_ids.remove(target_channel.id)

    # ボイスチャンネルが削除されたときのイベント（一時的なボイスチャンネルの削除に対応）
    @bot.event
    async def on_guild_channel_delete(channel):
        if isinstance(channel, discord.VoiceChannel):
            # 休止チャンネルはアーカイブ処理をスキップ
            if channel.id in IGNORE_VOICE_CHANNEL_IDS or "休止" in channel.name or "個室を作る" in channel.name:
                return
            
            print(f"ボイスチャンネル{channel.name}が削除されたので、ボイスチャンネル本体のチャットをアーカイブ開始")
            # ボイスチャンネル自体を対象にメッセージ履歴をPDFにアーカイブ
            if channel.id not in archived_channel_ids:
                archived_channel_ids.add(channel.id)
                try:
                    await archive_text_channel_history(channel, bot)
                    print(f"アーカイブ完了: {channel.name}のボイスチャット履歴を保存しました")
                except Exception as e:
                    print(f"[エラー] 削除されたボイスチャンネル{channel.name}のアーカイブ処理中にエラーが発生: {e}")
                finally:
                    if channel.id in archived_channel_ids:
                        archived_channel_ids.remove(channel.id)

    # Bot起動時に全サーバーの特殊チャンネルの権限を一括設定
    @bot.event
    async def on_ready():
        print("Botが起動しました。特殊チャンネルのテキストチャット権限を設定します...")
        for guild in bot.guilds:
            await disable_chat_for_special_channels(guild)
        print("全ての特殊チャンネルの権限設定が完了しました。")