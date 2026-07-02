import asyncio
import discord
import os
from utils import (
    setup_logger,
    set_permissions_with_retry,
    load_cache,
    save_cache,
    add_to_cache as utils_add_to_cache,
    remove_from_cache as utils_remove_from_cache,
    get_ids_from_env
)
from archive import archive_text_channel_history

# ロガーの初期化
logger = setup_logger(__name__)

# キャッシュの初期化
archived_channel_ids, processed_special_channels = load_cache()

# キャッシュ操作用のラッパー（引数をvoice_manager.pyの既存コードに合わせて調整）
def add_to_cache(cache_set, value):
    utils_add_to_cache(cache_set, value, archived_channel_ids, processed_special_channels)

def remove_from_cache(cache_set, value):
    utils_remove_from_cache(cache_set, value, archived_channel_ids, processed_special_channels)

# 休止ボイスチャンネルIDリスト（環境変数から読み込み、カンマ区切りで複数指定可能）
IGNORE_VOICE_CHANNEL_IDS = get_ids_from_env('IGNORE_VOICE_CHANNEL_IDS')

# 常設ボイスチャンネルの名前ホワイトリスト（環境変数から読み込み）
PERMANENT_VOICE_NAMES = os.getenv('PERMANENT_VOICE_NAMES', 'フリー,まったり').split(',')
PERMANENT_VOICE_NAMES = [name.strip() for name in PERMANENT_VOICE_NAMES]

def setup_voice_events(bot):
    # 全てのボイスチャンネルのテキストチャットの権限を設定する初期化処理
    async def setup_voice_text_channel_permissions(guild):
        # ボイスチャンネルごとに紐づくテキストチャット（スレッド含む）を検索
        for voice_channel in guild.voice_channels:
            # ボイスチャンネルに紐づくテキストチャネル/スレッドを全て取得
            linked_channels = []
            # 通常のtext_channelの場合
            for text_channel in guild.text_channels:
                if hasattr(text_channel, 'voice_channel') and text_channel.voice_channel and text_channel.voice_channel.id == voice_channel.id:
                    linked_channels.append(text_channel)
            # スレッドの場合（Discordの新しいボイスチャンネルはスレッドとして作成されることが多い）
            for thread in guild.threads:
                if hasattr(thread, 'voice_channel') and thread.voice_channel and thread.voice_channel.id == voice_channel.id:
                    linked_channels.append(thread)
            
            # 紐づくチャンネルが存在した場合に権限を設定
            for text_channel in linked_channels:
                # まず全てのボイスチャンネルのテキストチャットで、デフォルトロールの送信権限をオフに
                await set_permissions_with_retry(text_channel, guild.default_role, {"send_messages": False, "read_messages": False})
                # 現在ボイスチャンネルに参加しているメンバーには個別に送信・閲覧権限を付与
                for member in voice_channel.members:
                    await set_permissions_with_retry(text_channel, member, {"send_messages": True, "read_messages": True})
                # サーバー内の全メンバーのうち、現在参加していないメンバーは権限を明示的に拒否（個人ロールの影響を無効化）
                for member in guild.members:
                    if member.bot:
                        continue
                    # 現在の権限を取得して、既に正しい設定の場合はスキップ（処理負荷軽減）
                    text_perms = text_channel.permissions_for(member)
                    voice_perms = voice_channel.permissions_for(member)
                    
                    if member not in voice_channel.members:
                        # 既に権限が正しく設定されている場合はAPIコールをスキップ
                        if text_perms.send_messages == False and text_perms.read_messages == False and voice_perms.send_messages == False:
                            continue
                        # 紐づくテキストチャットとボイスチャンネル本体の両方に権限を設定（リトライロジック使用）
                        await set_permissions_with_retry(text_channel, member, {"send_messages": False, "read_messages": False})
                        await set_permissions_with_retry(voice_channel, member, {"send_messages": False})
                    else:
                        # 参加中のメンバーも同様に、既に権限が正しい場合はスキップ
                        if text_perms.send_messages == True and text_perms.read_messages == True and voice_perms.send_messages == True:
                            continue
                        await set_permissions_with_retry(text_channel, member, {"send_messages": True, "read_messages": True})
                        await set_permissions_with_retry(voice_channel, member, {"send_messages": True})
                logger.info(f"ボイスチャンネル{voice_channel.name}のテキストチャット({text_channel.name})の権限を設定しました（参加者限定）")
                  
                # 特殊チャンネル（休止・個室を作る）は閲覧だけ許可して送信は全員不可に統合処理
                if voice_channel.id not in processed_special_channels and ("休止" in voice_channel.name or "個室を作る" in voice_channel.name):
                   add_to_cache(processed_special_channels, voice_channel.id)
                   await set_permissions_with_retry(text_channel, guild.default_role, {"send_messages": False, "read_messages": True})
                   await set_permissions_with_retry(voice_channel, guild.default_role, {"send_messages": False})
                   logger.info(f"特殊チャンネル{voice_channel.name}のテキストチャット送信権限を無効化しました")

    # Discord標準のボイスチャンネル専用テキストチャンネルを利用したアーカイブ処理
    # ボイスチャンネルの状態が変更されたときのイベント（誰かが入退室したときに発火）
    @bot.event
    async def on_voice_state_update(member, before, after):
        # 新しくボイスチャンネルに参加した場合、そのチャンネルのテキストチャット権限を付与
        if after.channel is not None:
            # 参加したボイスチャンネルに紐づくテキストチャンネル/スレッドを検索
            linked_channels = []
            for text_channel in after.channel.guild.text_channels:
                if hasattr(text_channel, 'voice_channel') and text_channel.voice_channel and text_channel.voice_channel.id == after.channel.id:
                    linked_channels.append(text_channel)
            for thread in after.channel.guild.threads:
                if hasattr(thread, 'voice_channel') and thread.voice_channel and thread.voice_channel.id == after.channel.id:
                    linked_channels.append(thread)
            
            # 紐づく全てのチャンネルとボイスチャンネル本体に権限を付与
            for text_channel in linked_channels:
                # 現在の権限を確認して、既に正しい場合はスキップ
                text_perms = text_channel.permissions_for(member)
                voice_perms = after.channel.permissions_for(member)
                if text_perms.send_messages == True and text_perms.read_messages == True and voice_perms.send_messages == True:
                    continue
                # 権限を設定（エラーハンドリング付き）
                try:
                    await set_permissions_with_retry(after.channel, member, {"send_messages": True})
                    await set_permissions_with_retry(text_channel, member, {"send_messages": True, "read_messages": True})
                    logger.info(f"メンバー{member.display_name}が{after.channel.name}に参加したので、テキストチャット({text_channel.name})の権限を付与しました")
         
         # ボイスチャンネルから退出した場合、そのチャンネルのテキストチャット権限を削除
         if before.channel is not None and after.channel != before.channel:
             # 退出したボイスチャンネルに紐づくテキストチャンネル/スレッドを検索
             linked_channels = []
             for text_channel in before.channel.guild.text_channels:
                 if hasattr(text_channel, 'voice_channel') and text_channel.voice_channel and text_channel.voice_channel.id == before.channel.id:
                     linked_channels.append(text_channel)
             for thread in before.channel.guild.threads:
                 if hasattr(thread, 'voice_channel') and thread.voice_channel and thread.voice_channel.id == before.channel.id:
                     linked_channels.append(thread)
             
             # 紐づく全てのチャンネルとボイスチャンネル本体から権限を削除（個人ロールでもメンバー単位の権限が優先されるよう明示的に設定）
             for text_channel in linked_channels:
                 # 現在の権限を確認して、既に正しい場合はスキップ
                 text_perms = text_channel.permissions_for(member)
                 voice_perms = before.channel.permissions_for(member)
                 if text_perms.send_messages == False and text_perms.read_messages == False and voice_perms.send_messages == False:
                     continue
                 # 権限を削除（エラーハンドリング付き）
                 try:
                     await set_permissions_with_retry(before.channel, member, {"send_messages": False})
                     await set_permissions_with_retry(text_channel, member, {"send_messages": False, "read_messages": False})
                     logger.info(f"メンバー{member.display_name}が{before.channel.name}から退出したので、テキストチャット({text_channel.name})の権限を削除しました")
         
         # ボイスチャンネルから完全に退出し、誰も残っていない場合にアーカイブ処理を実行
         if after.channel is None and before.channel is not None:
             # 休止チャンネルはアーカイブ処理をスキップ
             if before.channel.id in IGNORE_VOICE_CHANNEL_IDS or "休止" in before.channel.name or "個室を作る" in before.channel.name:
                 return
             
             # ボイスチャンネルに残っている人間メンバーを確認（ジェネレータで効率化）
             remaining_humans = sum(1 for m in before.channel.members if not m.bot)
             if remaining_humans == 0:
                 logger.debug(f"{before.channel.name} の人間メンバーが0になったのでアーカイブ処理を開始")
                 # ボイスチャンネル自体を対象に、ボイスチャンネル内のチャットをアーカイブ
                 target_channel = before.channel
                 if target_channel and target_channel.id not in archived_channel_ids:
                     add_to_cache(archived_channel_ids, target_channel.id)
                     logger.info(f"ボイスチャンネル{before.channel.name}に誰もいなくなったので、ボイスチャンネル本体のチャットをアーカイブ開始")
                     try:
                         # メッセージ履歴をPDFにアーカイブ（ボイスチャンネルでもhistory()が使用可能）
                         await archive_text_channel_history(target_channel, bot)
                         logger.info(f"アーカイブ完了: {before.channel.name}のボイスチャット履歴を保存しました")
                         # 常設ボイスの場合はメッセージだけ削除して次回に備える（ホワイトリストで判定）
                         if any(name in before.channel.name for name in PERMANENT_VOICE_NAMES):
                             try:
                                 # チャンネルがまだ存在するか確認してからpurgeを実行
                                 channel_exists = any(c.id == target_channel.id for c in target_channel.guild.voice_channels)
                                 if channel_exists:
                                     await target_channel.purge()
                                     logger.info(f"常設ボイスチャンネル{before.channel.name}のチャットメッセージをクリアしました")
                                 else:
                                     logger.warning(f"常設ボイスチャンネル{before.channel.name}が既に削除されていたため、メッセージクリアをスキップしました")
                             except Exception as e:
                                 logger.error(f"常設ボイスチャンネル{before.channel.name}のメッセージクリア中にエラーが発生: {e}")
                     except Exception as e:
                         logger.error(f"ボイスチャンネル{before.channel.name}のアーカイブ処理中にエラーが発生: {e}")
                     finally:
                         # アーカイブ完了後（エラーが発生しても）、次回会話用にIDをマップから削除して再アーカイブ可能に
                         if target_channel.id in archived_channel_ids:
                             remove_from_cache(archived_channel_ids, target_channel.id)

     # ボイスチャンネルが削除されたときのイベント（一時的なボイスチャンネルの削除に対応）
     @bot.event
     async def on_guild_channel_delete(channel):
         if isinstance(channel, discord.VoiceChannel):
             # 休止チャンネルはアーカイブ処理をスキップ
             if channel.id in IGNORE_VOICE_CHANNEL_IDS or "休止" in channel.name or "個室を作る" in channel.name:
                 return
             
             logger.info(f"ボイスチャンネル{channel.name}が削除されたので、ボイスチャンネル本体のチャットをアーカイブ開始")
             # ボイスチャンネル自体を対象にメッセージ履歴をPDFにアーカイブ
             if channel.id not in archived_channel_ids:
                 add_to_cache(archived_channel_ids, channel.id)
                 try:
                     await archive_text_channel_history(channel, bot)
                     logger.info(f"アーカイブ完了: {channel.name}のボイスチャット履歴を保存しました")
                 except Exception as e:
                     logger.error(f"削除されたボイスチャンネル{channel.name}のアーカイブ処理中にエラーが発生: {e}")
                 finally:
                     if channel.id in archived_channel_ids:
                         remove_from_cache(archived_channel_ids, channel.id)

     # 新しいボイスチャンネルが作成されたときに自動的に権限を設定
     @bot.event
     async def on_guild_channel_create(channel):
         if isinstance(channel, discord.VoiceChannel):
             logger.info(f"新しいボイスチャンネル{channel.name}が作成されました。権限設定を実行します。")
             # 少し待機して紐づくテキストチャンネルが作成されるのを待つ
             await asyncio.sleep(1)
             await setup_voice_text_channel_permissions(channel.guild)

     # メンバーがサーバーから脱退したときにキャッシュと全チャンネルの権限をクリーンアップ
     @bot.event
     async def on_member_remove(member):
         logger.info(f"メンバー{member.display_name}がサーバーから脱退しました。権限とキャッシュをクリーンアップします。")
         
         # サーバー内の全てのチャンネルから退出メンバーの権限を削除
         for channel in member.guild.channels:
             try:
                 permissions = channel.overwrites_for(member)
                 # 権限が設定されている場合のみ削除処理を実行
                 if any([permissions.view_channel is not None, 
                        permissions.send_messages is not None,
                        permissions.connect is not None]):
                     await channel.set_permissions(member, overwrite=None)
                     logger.debug(f"チャンネル{channel.name}から{member.display_name}の権限を削除しました。")
             except Exception as e:
                 logger.warning(f"チャンネル{channel.name}の{member.display_name}の権限削除に失敗: {e}")

     # Bot起動時に全サーバーのボイスチャンネルの権限を一括設定
     @bot.event
     async def on_ready():
         logger.info("Botが起動しました。全ボイスチャンネルのテキストチャット権限を設定します...")
         # 起動時の権限設定を並行処理で高速化
         tasks = [setup_voice_text_channel_permissions(guild) for guild in bot.guilds]
         await asyncio.gather(*tasks)
         logger.info("全てのボイスチャンネルの権限設定が完了しました。")