import discord
from discord.ext import commands
import logging

logger = logging.getLogger(__name__)

# グローバル変数（イベントの状態管理）
active_event_channel_id = None
event_owner_id = None

class EventManagementCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("EventManagementCogが初期化されました（コマンドはbot.pyに統合）")
    
    # 全てのスラッシュコマンドはbot.pyに統合したため、ここには定義しません（重複防止）

# 必須のsetup関数：CogをBotにロードするために必要
async def setup(bot: commands.Bot):
    await bot.add_cog(EventManagementCog(bot))
    logger.info("EventManagementCogが正常にロードされました")