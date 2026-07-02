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
    # Discord標準のボイスチャンネル専用テキストチャンネルを利用したアーカイブ処理
    # ボイスチャンネルの状態が変更されたときのイベント（誰かが入退室したときに発火）
    @bot.event
    async def on_voice_state_update(member, before, after):
        # ボイスチャンネルから完全に退出し、誰も残っていない場合にアーカイブ処理を実行
        if after.channel is None and before.channel is not None:
            # 休止チャンネルはアーカイブ処理をスキップ
            if before.channel.id in IGNORE_VOICE_CHANNEL_IDS or "休止" in before.channel.name or "個室を作る" in before.channel.name:
                return
            
            # ボイスチャンネルに残っている人間メンバーを確認
            remaining_humans = [m for m in before.channel.members if not m.bot]
            if len(remaining_humans) == 0:
                # Discord標準のボイスチャンネル専用テキストチャンネルを取得
                text_channel = before.channel.text_channel
                if text_channel and text_channel.id not in archived_channel_ids:
                    archived_channel_ids.add(text_channel.id)
                    print(f"ボイスチャンネル{before.channel.name}に誰もいなくなったので、標準テキストチャンネル{text_channel.name}をアーカイブ開始")
                    # メッセージ履歴をPDFにアーカイブ
                    await archive_text_channel_history(text_channel, bot)
                    print(f"アーカイブ完了: {before.channel.name}のテキストチャンネル履歴を保存しました")
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
            
            # 削除されたボイスチャンネルの標準テキストチャンネルを取得
            text_channel = channel.text_channel
            if text_channel and text_channel.id not in archived_channel_ids:
                archived_channel_ids.add(text_channel.id)
                print(f"ボイスチャンネル{channel.name}が削除されたので、標準テキストチャンネル{text_channel.name}をアーカイブ開始")
                # メッセージ履歴をPDFにアーカイブ
                await archive_text_channel_history(text_channel, bot)
                print(f"アーカイブ完了: {channel.name}のテキストチャンネル履歴を保存しました")