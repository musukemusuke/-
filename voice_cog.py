import discord
from discord.ext import commands
import logging
from voice_manager import setup_voice_events

logger = logging.getLogger(__name__)

class VoiceManagementCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # ボイスイベントをセットアップ
        setup_voice_events(bot)
        logger.info("VoiceManagementCogのボイスイベントがセットアップされました")

async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceManagementCog(bot))
    logger.info("VoiceManagementCogが正常にロードされました")