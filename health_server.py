from aiohttp import web
import os
import logging

from utils import metrics, setup_logger

logger = setup_logger(__name__)

# ヘルスチェック用エンドポイント
async def health_check(request):
    return web.Response(text="Bot is running", status=200)

# メトリクス用エンドポイント（Prometheus形式で出力）
async def metrics_endpoint(request):
    prometheus_output = (
        f"# HELP bot_permission_errors_total 権限設定エラーの合計回数\n"
        f"# TYPE bot_permission_errors_total counter\n"
        f"bot_permission_errors_total {metrics['permission_errors']}\n"
        f"\n# HELP bot_cache_saves_total キャッシュ保存の合計回数\n"
        f"# TYPE bot_cache_saves_total counter\n"
        f"bot_cache_saves_total {metrics['cache_saves']}\n"
        f"\n# HELP bot_members_processed_total 処理したメンバーの合計数\n"
        f"# TYPE bot_members_processed_total counter\n"
        f"bot_members_processed_total {metrics['members_processed']}\n"
        f"\n# HELP bot_roles_created_total 作成したロールの合計数\n"
        f"# TYPE bot_roles_created_total counter\n"
        f"bot_roles_created_total {metrics['roles_created']}\n"
    )
    return web.Response(text=prometheus_output, content_type='text/plain; version=0.0.4')

async def start_health_server():
    health_port = int(os.getenv('HEALTH_CHECK_PORT', 8080))
    app = web.Application()
    app.add_routes([
        web.get('/health', health_check),
        web.get('/metrics', metrics_endpoint)
    ])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', health_port)
    await site.start()
    logger.info(f'ヘルスチェック・メトリクスサーバーを起動しました。ポート: {health_port}')