import asyncio
import discord

# ボイスチャンネルの監視を行うクラス
class VoiceChannelMonitor:
    def __init__(self, bot, ignore_voice_channel_ids):
        self.bot = bot
        self.IGNORE_VOICE_CHANNEL_IDS = ignore_voice_channel_ids
        self.timers = {}  # ボイスチャンネルごとのタイマーを管理
    
    async def check_and_create_listen_channel(self, member, before, after):
        """ボイスチャンネルに誰かが入ったときに聞き専用チャンネルを作成する"""
        # 新しくボイスチャンネルに参加した場合
        if after.channel is not None:
            # 無視リストにあるチャンネルは処理しない
            if after.channel.id in self.IGNORE_VOICE_CHANNEL_IDS:
                return
            # すでに聞き専用チャンネルが存在するか確認
            guild = after.channel.guild
            listen_channel_name = f"聞き専用-{after.channel.name}"
            existing_channel = discord.utils.get(guild.channels, name=listen_channel_name)
            if not existing_channel:
                print(f"聞き専用チャンネルを作成します: {listen_channel_name}")
                # カテゴリーは元のボイスチャンネルと同じものを使用
                category = after.channel.category
                # テキストチャンネルを作成
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                    # 必要に応じて権限を調整可能
                }
                await guild.create_text_channel(listen_channel_name, category=category, overwrites=overwrites)
                print(f"聞き専用チャンネルの作成完了: {listen_channel_name}")
    
    async def check_and_delete_listen_channel(self, member, before, after):
        """ボイスチャンネルが空になったら、指定時間後に聞き専用チャンネルを削除する"""
        # ボイスチャンネルから誰かが退出した場合
        if before.channel is not None:
            # 無視リストにあるチャンネルは処理しない
            if before.channel.id in self.IGNORE_VOICE_CHANNEL_IDS:
                return
            # ボイスチャンネルの現在のメンバー数を確認（botを除く）
            human_members = [m for m in before.channel.members if not m.bot]
            if len(human_members) == 0:
                # 空になったのでタイマーをセット（5分後に削除）
                channel_id = before.channel.id
                if channel_id in self.timers:
                    # 既存のタイマーをキャンセル
                    self.timers[channel_id].cancel()
                # 新しいタイマーを作成
                self.timers[channel_id] = asyncio.create_task(
                    self.delete_listen_channel_after_delay(before.channel, 300)  # 300秒 = 5分
                )
            else:
                # まだメンバーがいるのでタイマーをキャンセル（もしあれば）
                channel_id = before.channel.id
                if channel_id in self.timers:
                    self.timers[channel_id].cancel()
                    del self.timers[channel_id]
    
    async def delete_listen_channel_after_delay(self, voice_channel, delay):
        """指定時間後に聞き専用チャンネルを削除する"""
        await asyncio.sleep(delay)
        # 再度チェックして、まだ誰も入っていなければ削除
        human_members = [m for m in voice_channel.members if not m.bot]
        if len(human_members) == 0:
            # 対応する聞き専用テキストチャンネルを探して削除
            guild = voice_channel.guild
            listen_channel_name = f"聞き専用-{voice_channel.name}"
            listen_channel = discord.utils.get(guild.channels, name=listen_channel_name)
            if listen_channel:
                # アーカイブ処理は別途呼び出し元で行うので、ここではチャンネルIDだけ返す
                print(f"聞き専用チャンネルを削除します: {listen_channel_name}")
                # タイマーを削除
                if voice_channel.id in self.timers:
                    del self.timers[voice_channel.id]
                return listen_channel
        # メンバーがいれば何もしない
        if voice_channel.id in self.timers:
            del self.timers[voice_channel.id]
        return None