import discord
from discord.ext import commands
import logging
from health_server import start_health_server

logger = logging.getLogger(__name__)

class HealthCheckCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        # ヘルスチェックサーバーを起動
        await start_health_server(logger)
        logger.info("HealthCheckCogが起動しました：ヘルスサーバーが開始されました")

async def setup(bot: commands.Bot):
    await bot.add_cog(HealthCheckCog(bot))
    logger.info("HealthCheckCogが正常にロードされました")