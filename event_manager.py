import discord
import logging
from utils import set_permissions_with_retry, setup_logger

logger = setup_logger(__name__)

# アクティブなイベントチャンネルを管理するグローバル変数
active_event_channel_id = None
event_owner_id = None

async def register_event_commands(bot):
    """イベント管理用のスラッシュコマンドを登録"""
    
    @bot.tree.command(name="hajimeru", description="イベント用のチャンネルを作成して開始します")
    @discord.app_commands.guild_only()  # サーバー内でのみ表示・使用可能に設定
    async def hajimeru_command(interaction: discord.Interaction, content: str):
        global active_event_channel_id, event_owner_id
        
        # 既にアクティブなイベントチャンネルが存在する場合はエラー
        if active_event_channel_id is not None:
            await interaction.response.send_message("既にアクティブなイベントチャンネルが存在します。先に/owariで終了してください。", ephemeral=True)
            return

        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("このコマンドはサーバー内でのみ使用できます。", ephemeral=True)
            return

        # チャンネル名を作成
        channel_name = f"📅イベント開催中-{content.replace(' ', '-')}"
        
        # まずインタラクションの応答を送信（処理に時間がかかるので先に返す）
        await interaction.response.send_message(f"イベントチャンネル「{channel_name}」を作成しています...", ephemeral=True)

        try:
            # 既存のカテゴリーなしのテキストチャンネルを取得してpositionを1つずつずらす
            root_channels = [ch for ch in guild.channels if ch.category is None and isinstance(ch, discord.TextChannel)]
            for ch in sorted(root_channels, key=lambda x: x.position):
                await ch.edit(position=ch.position + 1)
            
            # 新しいチャンネルをカテゴリーなしで作成
            new_channel = await guild.create_text_channel(
                name=channel_name,
                position=0  # 最上部に配置
            )
            logger.info(f"イベントチャンネル {new_channel.name} を作成しました (ID: {new_channel.id})")

            # 権限設定：一般ユーザーは書き込めないように
            # まず@everyone（全員）の権限を無効化
            await set_permissions_with_retry(new_channel, guild.default_role, {"send_messages": False})
            # さらにサーバー内の全てのロール（個人ロールを含む）に対しても明示的に無効化
            for role in guild.roles:
                # @everyone、ボットオーナー、管理者以外は全てのロールの送信権限を無効化
                if role != guild.default_role and not (role.is_bot_owner() if hasattr(role, 'is_bot_owner') else False) and not role.permissions.administrator:
                    await set_permissions_with_retry(new_channel, role, {"send_messages": False})
                    logger.debug(f"ロール {role.name} の送信権限を無効化しました")

            # Bot自身、サーバー管理者、そしてイベント作成者だけは書き込み可能に設定
            await set_permissions_with_retry(new_channel, guild.me, {"send_messages": True})
            # コマンドを実行したイベント作成者に書き込み権限を付与（個人ロールがあっても個別に許可）
            await set_permissions_with_retry(new_channel, interaction.user, {"send_messages": True})
            # サーバー管理者全員に書き込み権限を付与
            for member in guild.members:
                if member.guild_permissions.administrator and not member.bot and member.id != interaction.user.id:
                    await set_permissions_with_retry(new_channel, member, {"send_messages": True})
            logger.info(f"イベントチャンネル {new_channel.name} の一般ユーザーの書き込み権限を無効化（作成者・管理者・Botのみ書き込み可）")

            # 作成したチャンネルのIDと所有者をグローバル変数に保存
            active_event_channel_id = new_channel.id
            event_owner_id = interaction.user.id

            # 完了メッセージをチャンネルに送信
            await new_channel.send(f"📅 イベント「{content}」が開始されました！\n作成者: {interaction.user.mention}\nこのチャンネルはイベント終了時に/owariコマンドで削除できます。")
            
            # インタラクションの完了メッセージを更新
            await interaction.edit_original_response(content=f"✅ イベントチャンネル「{channel_name}」を作成しました！{new_channel.mention}")

        except Exception as e:
            logger.error(f"イベントチャンネルの作成中にエラーが発生しました: {e}")
            await interaction.edit_original_response(content=f"❌ イベントチャンネルの作成に失敗しました: {str(e)}")


    @bot.tree.command(name="owari", description="アクティブなイベントチャンネルを終了・削除します")
    @discord.app_commands.guild_only()  # サーバー内でのみ表示・使用可能に設定
    async def owari_command(interaction: discord.Interaction):
        global active_event_channel_id, event_owner_id
        
        # アクティブなイベントチャンネルが存在しない場合
        if active_event_channel_id is None:
            await interaction.response.send_message("現在アクティブなイベントチャンネルは存在しません。", ephemeral=True)
            return

        # イベント作成者または管理者だけが削除可能
        if interaction.user.id != event_owner_id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("このコマンドはイベント作成者または管理者のみ実行できます。", ephemeral=True)
            return

        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("このコマンドはサーバー内でのみ使用できます。", ephemeral=True)
            return

        # チャンネルを取得
        event_channel = guild.get_channel(active_event_channel_id)
        if not event_channel:
            logger.warning(f"イベントチャンネルID {active_event_channel_id} が見つかりませんでした。グローバル変数をリセットします。")
            active_event_channel_id = None
            event_owner_id = None
            await interaction.response.send_message("チャンネルが既に削除されていたため、状態をリセットしました。", ephemeral=True)
            return

        # まずインタラクションの応答を送信
        await interaction.response.send_message(f"イベントチャンネル「{event_channel.name}」を削除しています...", ephemeral=True)

        try:
            # チャンネルを削除
            await event_channel.delete()
            logger.info(f"イベントチャンネル {event_channel.name} を削除しました")
            
            # グローバル変数をリセット
            active_event_channel_id = None
            event_owner_id = None

            # 完了メッセージを更新
            await interaction.edit_original_response(content=f"✅ イベントチャンネル「{event_channel.name}」を削除しました。")

        except Exception as e:
            logger.error(f"イベントチャンネルの削除中にエラーが発生しました: {e}")
            await interaction.edit_original_response(content=f"❌ イベントチャンネルの削除に失敗しました: {str(e)}")