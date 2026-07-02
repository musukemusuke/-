import asyncio
import logging
import os
import json
from dotenv import load_dotenv

# メトリクス用のグローバルカウンター
metrics = {
    'permission_errors': 0,
    'cache_saves': 0,
    'members_processed': 0,
    'roles_created': 0
}

# 全モジュールで共通して使用するロガーを設定
def setup_logger(name=__name__):
    # 環境変数からログレベルを取得（デフォルトはINFO）
    log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
    level = getattr(logging, log_level, logging.INFO)
    
    logger = logging.getLogger(name)
    logger.setLevel(level)
    # 既にハンドラーが追加されている場合は重複追加を防ぐ
    if not logger.handlers:
        # コンソール出力用ハンドラー
        console_handler = logging.StreamHandler()
        # ファイル出力用ハンドラー（logsディレクトリに日別ログファイルを作成）
        os.makedirs('logs', exist_ok=True)
        from datetime import datetime
        log_file = f"logs/bot_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        file_handler.setFormatter(formatter)
        
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)
    return logger

# .envファイルから環境変数を読み込み（全モジュールで共通）
load_dotenv()

# 環境変数からリトライ設定を読み込み
MAX_RETRY_COUNT = int(os.getenv('MAX_RETRY_COUNT', 3))
RETRY_INTERVAL_SECONDS = int(os.getenv('RETRY_INTERVAL_SECONDS', 3))

# 権限設定をリトライ付きで実行する共通ヘルパー関数
async def set_permissions_with_retry(channel, target, permissions, max_retries=MAX_RETRY_COUNT, logger=None):
    if not logger:
        logger = setup_logger(__name__)
    for retry in range(max_retries):
        try:
            await channel.set_permissions(target, **permissions)
            return True
        except Exception as e:
            if retry < max_retries - 1:
                logger.warning(f"権限設定に失敗（{retry+1}回目/{max_retries}回）: {e}。{RETRY_INTERVAL_SECONDS}秒後にリトライします...")
                await asyncio.sleep(RETRY_INTERVAL_SECONDS)
            else:
                error_msg = f"チャンネル{channel.name}(ID:{channel.id})での権限設定が{max_retries}回失敗しました: {e}"
                logger.error(error_msg)
                # 権限エラーのメトリクスをインクリメント
                metrics['permission_errors'] += 1
                # Botインスタンスが存在する場合のみエラー通知を送信
                if hasattr(channel, 'guild') and channel.guild and channel.guild.me:
                    await send_error_notification(channel.guild.me.bot, error_msg, "ERROR")
                return False

# キャッシュ操作用の共通関数
CACHE_FILE = "voice_bot_cache.json"

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
                return set(cache.get('archived_channel_ids', [])), set(cache.get('processed_special_channels', []))
        except Exception as e:
            logger = setup_logger(__name__)
            logger.warning(f"キャッシュファイルの読み込みに失敗: {e}")
    return set(), set()

def save_cache(archived_channel_ids, processed_special_channels):
    # キャッシュ保存前に既存のキャッシュファイルをバックアップ
    if os.path.exists(CACHE_FILE):
        try:
            from datetime import datetime
            os.makedirs('cache_backups', exist_ok=True)
            backup_file = f"voice_bot_cache_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json.bak"
            backup_path = os.path.join('cache_backups', backup_file)
            # コピーしてバックアップを作成
            import shutil
            shutil.copy2(CACHE_FILE, backup_path)
            # 古いバックアップを削除（最大10個保持）
            backup_files = sorted([os.path.join('cache_backups', f) for f in os.listdir('cache_backups') if f.startswith('voice_bot_cache_')])
            if len(backup_files) > 10:
                for old_file in backup_files[:-10]:
                    os.remove(old_file)
            logger = setup_logger(__name__)
            logger.debug(f"キャッシュのバックアップを作成しました: {backup_path}")
        except Exception as e:
            logger = setup_logger(__name__)
            logger.warning(f"キャッシュのバックアップ作成に失敗: {e}")
    
    # 新しいキャッシュを保存
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                'archived_channel_ids': list(archived_channel_ids),
                'processed_special_channels': list(processed_special_channels)
            }, f, ensure_ascii=False, indent=2)
        logger = setup_logger(__name__)
         logger.debug(f"キャッシュを保存しました。アーカイブ済みチャンネル数: {len(archived_channel_ids)}")
         # キャッシュ保存のメトリクスをインクリメント
         metrics['cache_saves'] += 1
    except Exception as e:
        logger = setup_logger(__name__)
        logger.warning(f"キャッシュファイルの保存に失敗: {e}")

def add_to_cache(cache_set, value, archived_channel_ids, processed_special_channels):
    cache_set.add(value)
    save_cache(archived_channel_ids, processed_special_channels)

def remove_from_cache(cache_set, value, archived_channel_ids, processed_special_channels):
    if value in cache_set:
        cache_set.remove(value)
        save_cache(archived_channel_ids, processed_special_channels)

# 環境変数からIDリストを読み込む共通ヘルパー
def get_ids_from_env(env_name, default=None):
    default = default or []
    env_value = os.getenv(env_name, '')
    if env_value:
        return [int(id.strip()) for id in env_value.split(',') if id.strip()]
    return default

# エラー通知を送信する共通関数
async def send_error_notification(bot, error_message, error_level="ERROR"):
    # 環境変数から通知先チャンネルIDを取得
    error_channel_id = int(os.getenv('ERROR_NOTIFICATION_CHANNEL_ID', 0))
    if not error_channel_id:
        # 通知先が設定されていない場合は通知しない
        return
    
    try:
        channel = await bot.fetch_channel(error_channel_id)
        if channel:
            # エラーレベルに応じた絵文字を設定
            emoji = "⚠️" if error_level == "WARNING" else "🚨"
            await channel.send(f"{emoji} Botで{error_level}エラーが発生しました\n```{error_message[:1000]}```")  # 長すぎる場合は切り詰め
            logger = setup_logger(__name__)
            logger.debug(f"エラー通知を送信しました: {error_message[:50]}...")
    except Exception as e:
        logger = setup_logger(__name__)
        logger.warning(f"エラー通知の送信に失敗しました: {e}")