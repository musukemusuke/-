import discord
from discord.ext import commands
from discord import ui
import asyncio
import os

import logging

logger = logging.getLogger(__name__)

# ここにボタンを設置したいチャンネルのIDを設定してください
# Discordでチャンネルを右クリックし、「IDをコピー」で取得できます。
BUTTON_CHANNEL_ID = int(os.getenv('BUTTON_CHANNEL_ID', '0'))
if BUTTON_CHANNEL_ID == 0:
    logger.error("BUTTON_CHANNEL_IDが環境変数に設定されていないか、無効なIDです。意見箱ボタンの設置ができません。")
    # ここでBotの起動を停止するか、機能を使えなくするなどの対応が必要になる場合があります。
    # 今回はエラーログを出力するのみとします。

# ------------------------------------------------------------------------------------
# 意見箱入力用モーダル
# ------------------------------------------------------------------------------------
class FeedbackInputModal(ui.Modal, title="意見箱への投稿"):
    feedback_text = ui.TextInput(
        label="あなたの意見や要望を記入してください",
        style=discord.TextStyle.paragraph,
        placeholder="改善点、提案、感想など、ご自由にお書きください。",
        required=True,
        max_length=1000
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True) # 応答を遅延させ、ユーザーには見えないようにする

        guild = interaction.guild
        if not guild:
            await interaction.followup.send("サーバー内でのみ利用可能です。", ephemeral=True)
            return

        # スレッドの作成
        try:
            # スレッド名にユーザー名とタイムスタンプを含める
            thread_name = f"意見箱_{interaction.user.display_name}_{discord.utils.utcnow().strftime('%Y%m%d%H%M')}"
            
            # プライベートスレッドを作成
            # type=discord.ChannelType.private_thread は現在非推奨。
            # type=discord.ChannelType.private_thread の代わりに private=True を使用する。
            # ただし、discord.py 2.xではまだ private=True がサポートされていない可能性があるので、
            # 現状は type=discord.ChannelType.private_thread を使用する。
            # もしエラーが出る場合は、discord.pyのバージョンを確認し、private=True に変更を検討する。
            thread = await interaction.channel.create_thread(
                name=thread_name,
                type=discord.ChannelType.private_thread, # プライベートスレッド
                reason=f"{interaction.user.display_name} からの意見箱スレッド",
                auto_archive_duration=1440 # 24時間後に自動アーカイブ
            )
            logger.info(f"プライベートスレッド '{thread.name}' (ID: {thread.id}) が {interaction.user.display_name} によって作成されました。")

            # スレッドにユーザーとボットを追加
            await thread.add_user(interaction.user)
            await thread.add_user(interaction.guild.me) # ボット自身もスレッドに追加

            # スレッドに最初のメッセージを送信
            embed = discord.Embed(
                title="新しい意見が届きました",
                description=self.feedback_text.value,
                color=discord.Color.blue()
            )
            embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
            embed.add_field(name="投稿者", value=interaction.user.mention, inline=True)
            embed.add_field(name="スレッド開始日時", value=discord.utils.format_dt(discord.utils.utcnow(), "F"), inline=True)
            embed.set_footer(text="このスレッドはあなたと運営者のみが閲覧できます。")

            # スレッドを閉じるボタン付きのViewを送信
            await thread.send(embed=embed, view=ThreadCloseView(thread_starter_id=interaction.user.id))
            logger.info(f"スレッド {thread.id} に初期メッセージと閉じるボタンを送信しました。")

            await interaction.followup.send(f"意見箱スレッドを作成しました！こちらからどうぞ: {thread.mention}", ephemeral=True)
            logger.info(f"ユーザー {interaction.user.display_name} にスレッド作成完了メッセージを送信しました。")

        except discord.Forbidden:
            logger.error(f"プライベートスレッドの作成またはユーザーの追加に失敗しました。Botに適切な権限があるか確認してください。")
            await interaction.followup.send("プライベートスレッドの作成に失敗しました。Botに「スレッドの管理」および「プライベートスレッドの作成」権限があるか確認してください。", ephemeral=True)
        except discord.HTTPException as e:
            logger.error(f"Discord APIエラーが発生しました: {e.status} - {e.text}")
            await interaction.followup.send(f"スレッド作成中にエラーが発生しました: {e.text}", ephemeral=True)
        except Exception as e:
            logger.error(f"予期せぬエラーが発生しました: {type(e).__name__}: {str(e)}")
            await interaction.followup.send("スレッド作成中に予期せぬエラーが発生しました。", ephemeral=True)

# ------------------------------------------------------------------------------------
# スレッドを閉じる確認用View
# ------------------------------------------------------------------------------------
class ThreadConfirmCloseView(ui.View):
    def __init__(self, thread_id: int):
        super().__init__(timeout=60) # 60秒でタイムアウト
        self.thread_id = thread_id

    @ui.button(label="はい、閉じます", style=discord.ButtonStyle.danger)
    async def confirm_close(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        thread = interaction.guild.get_channel(self.thread_id)
        if thread and isinstance(thread, discord.Thread):
            try:
                await thread.edit(archived=True, reason=f"{interaction.user.display_name} がスレッドを閉じました。")
                logger.info(f"スレッド '{thread.name}' (ID: {thread.id}) が {interaction.user.display_name} によって閉じられました。")
                await interaction.followup.send("スレッドを閉じました。", ephemeral=True)
                # 元のメッセージのボタンを無効化
                for item in self.children:
                    item.disabled = True
                await interaction.message.edit(view=self)
            except discord.Forbidden:
                logger.error(f"スレッド {thread.id} を閉じる権限がありません。")
                await interaction.followup.send("スレッドを閉じる権限がありません。", ephemeral=True)
            except Exception as e:
                logger.error(f"スレッド {thread.id} を閉じる際に予期せぬエラーが発生しました: {e}")
                await interaction.followup.send("スレッドを閉じる際にエラーが発生しました。", ephemeral=True)
        else:
            await interaction.followup.send("スレッドが見つからないか、既に閉じられています。", ephemeral=True)
        self.stop() # Viewを停止

    @ui.button(label="キャンセル", style=discord.ButtonStyle.secondary)
    async def cancel_close(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("スレッドを閉じるのをキャンセルしました。", ephemeral=True)
        # 元のメッセージのボタンを無効化
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)
        self.stop() # Viewを停止

# ------------------------------------------------------------------------------------
# スレッドを閉じるボタン
# ------------------------------------------------------------------------------------
class ThreadCloseView(ui.View):
    def __init__(self, thread_starter_id: int):
        super().__init__(timeout=None) # 永続View
        self.thread_starter_id = thread_starter_id

    @ui.button(label="スレッドを閉じる", style=discord.ButtonStyle.danger, custom_id="persistent_close_thread_button")
    async def close_thread_button(self, interaction: discord.Interaction, button: ui.Button):
        # スレッド開始者または管理者のみが閉じられるようにする
        if interaction.user.id == self.thread_starter_id or interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("スレッドを閉じます。よろしいですか？", view=ThreadConfirmCloseView(thread_id=interaction.channel_id), ephemeral=True)
        else:
            await interaction.response.send_message("このスレッドを閉じられるのは、スレッドの開始者か管理者のみです。", ephemeral=True)

# ------------------------------------------------------------------------------------
# 意見箱ボタン
# ------------------------------------------------------------------------------------
class FeedbackButtonView(ui.View):
    def __init__(self):
        super().__init__(timeout=None) # 永続View

    @ui.button(label="意見箱に投稿する", style=discord.ButtonStyle.primary, custom_id="persistent_feedback_button")
    async def feedback_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(FeedbackInputModal())

# ------------------------------------------------------------------------------------
# コグ本体
# ------------------------------------------------------------------------------------
class FeedbackThreadCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.persistent_views_added = False

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.persistent_views_added:
            # 永続Viewを登録
            self.bot.add_view(FeedbackButtonView())
            logger.info("永続View: FeedbackButtonView を登録しました。")
            self.bot.add_view(ThreadCloseView(thread_starter_id=0)) # thread_starter_id はダミー
            logger.info("永続View: ThreadCloseView を登録しました。")
            self.persistent_views_added = True

    @commands.command(name="setup_feedback_thread_button", help="意見箱ボタンを設置します（管理者のみ）")
    @commands.has_permissions(administrator=True)
    async def setup_feedback_thread_button(self, ctx: commands.Context):
        if ctx.channel.id != BUTTON_CHANNEL_ID:
            await ctx.send(f"このコマンドは <#{BUTTON_CHANNEL_ID}> でのみ実行できます。", ephemeral=True)
            return

        channel = self.bot.get_channel(BUTTON_CHANNEL_ID)
        if not channel:
            await ctx.send(f"設定されたチャンネルID ({BUTTON_CHANNEL_ID}) が見つかりません。", ephemeral=True)
            return

        try:
            await channel.send("ご意見・ご要望はこちらからどうぞ！", view=FeedbackButtonView())
            await ctx.send("意見箱ボタンを設置しました。", ephemeral=True)
            logger.info(f"意見箱ボタンがチャンネル {channel.name} (ID: {channel.id}) に設置されました。")
        except discord.Forbidden:
            await ctx.send("チャンネルにメッセージを送信する権限がありません。", ephemeral=True)
            logger.error(f"チャンネル {channel.id} に意見箱ボタンを設置する権限がありません。")
        except Exception as e:
            await ctx.send(f"ボタン設置中にエラーが発生しました: {e}", ephemeral=True)
            logger.error(f"意見箱ボタン設置中に予期せぬエラーが発生しました: {type(e).__name__}: {str(e)}")

async def setup(bot: commands.Bot):
    await bot.add_cog(FeedbackThreadCog(bot))
    logger.info("FeedbackThreadCog をロードしました。")