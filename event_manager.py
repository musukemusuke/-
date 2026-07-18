import discord
import logging
import asyncio
from utils import set_permissions_with_retry

logger = logging.getLogger(__name__)

# アクティブなイベントを保存する辞書
# キー: チャンネルID, 値: 作成者ID
active_events = {}

async def handle_event_start(bot, message, event_name):
    """!event_start コマンドの処理 - イベント用チャンネルを作成"""
    
    guild = message.guild
    if not guild:
        await message.channel.send("このコマンドはサーバー内でのみ使用できます。")
        return
    
    # 同名のチャンネルが存在するか確認（仮のチェック用に生成）
    check_channel_name = f"ｲﾍﾞﾝﾄ開催中_{event_name.replace(' ', '_')}"
    if len(check_channel_name) > 100:
        check_channel_name = check_channel_name[:97] + "..."
    existing_channel = discord.utils.get(guild.channels, name=check_channel_name)
    if existing_channel:
        await message.channel.send(f"チャンネル `{check_channel_name}` は既に存在します。")
        return
    
    try:
        safe_event_name = event_name.replace(' ', '_')
        display_channel_name = safe_event_name
        if len(display_channel_name) > 100:
            display_channel_name = display_channel_name[:97] + "..."
        
        category = discord.utils.get(guild.categories, name="イベント開催中")
        pin_category = next((c for c in guild.categories if "📌" in c.name), None)
        target_pos = max(0, pin_category.position - 1) if pin_category else 0
        
        if category is None:
            category = await guild.create_category("イベント開催中")
        
        try:
            if category.position != target_pos:
                await category.edit(position=target_pos)
        except Exception as e:
            logger.warning(f"カテゴリー位置の変更に失敗: {e}")
        
        await set_permissions_with_retry(
            category, 
            guild.default_role, 
            {"send_messages": False},
            logger=logger
        )
        for member in guild.members:
            if member.bot:
                continue
            for role in member.roles:
                if role.is_default():
                    continue
                await set_permissions_with_retry(
                    category, 
                    role, 
                    {"send_messages": False},
                    logger=logger
                )
        
        new_channel = await guild.create_text_channel(
            name=display_channel_name,
            category=category,
            position=0
        )
        
        # @everyoneの書き込み権限を無効に設定
        await set_permissions_with_retry(
            new_channel, 
            guild.default_role, 
            {"send_messages": False},
            logger=logger
        )
        
        # サーバー内の全てのメンバーの個人ロールを取得し、作成者以外の書き込み権限を無効に
        for member in guild.members:
            if member.bot:
                continue
            # 作成者自身はスキップ
            if member.id == message.author.id:
                continue
            # メンバーが持っている個人ロールを全て取得
            for role in member.roles:
                # デフォルトの@everyoneロールは既に処理済みなのでスキップ
                if role.is_default():
                    continue
                # 個人ロールに対して書き込み権限を無効に設定
                await set_permissions_with_retry(
                    new_channel, 
                    role, 
                    {"send_messages": False},
                    logger=logger
                )
        
        # イベントの作成者には書き込み権限を付与
        await set_permissions_with_retry(
            new_channel, 
            message.author, 
            {"send_messages": True},
            logger=logger
        )
        
        # アクティブなイベントとして記録
        active_events[new_channel.id] = message.author.id
        
        logger.info(f"イベントチャンネル {display_channel_name} を {message.author} が作成しました（作成者には書き込み権限を付与）")
        
        # コマンドを実行したメッセージ自体を削除
        try:
            await message.delete()
        except discord.Forbidden:
            logger.warning(f"コマンドメッセージの削除権限がないため、!event_startのメッセージを削除できませんでした")
        except Exception as e:
            logger.error(f"コマンドメッセージ削除中にエラーが発生: {e}")
        
    except discord.Forbidden:
        await message.channel.send("チャンネルを作成する権限がありません。")
        logger.error(f"チャンネル作成権限がないため、{channel_name} を作成できませんでした")
    except Exception as e:
        await message.channel.send("チャンネルの作成中にエラーが発生しました。")
        logger.error(f"イベントチャンネル作成中にエラーが発生: {e}")

async def handle_event_end(bot, message):
    """!event_end コマンドの処理 - イベントチャンネルを削除"""
    channel_id = message.channel.id
    
    # このチャンネルがアクティブなイベントか確認
    if channel_id not in active_events:
        channel = message.channel
        category = getattr(channel, "category", None)
        if category and category.name.strip() == "イベント開催中":
            active_events[channel_id] = None
        else:
            logger.warning(f"イベント終了失敗: category={getattr(category, 'name', None)}, channel={channel.name}")
            await message.channel.send("このチャンネルはイベントチャンネルではないか、既に終了しています。")
            return
    
    # イベントの作成者か、サーバーの管理者か確認
    creator_id = active_events[channel_id]
    is_creator = creator_id is None or message.author.id == creator_id
    is_admin = any(role.permissions.administrator for role in message.author.roles)
    
    if not (is_creator or is_admin):
        # コマンドメッセージを削除してからエラー通知
        try:
            await message.delete()
        except:
            pass
        await message.channel.send("このイベントを終了できるのは作成者または管理者のみです。")
        return
    
    # コマンドを実行したメッセージ自体を削除
    try:
        await message.delete()
    except discord.Forbidden:
        logger.warning(f"コマンドメッセージの削除権限がないため、!event_endのメッセージを削除できませんでした")
    except Exception as e:
        logger.error(f"コマンドメッセージ削除中にエラーが発生: {e}")
    
    try:
        # アクティブイベントから削除
        category = message.channel.category
        del active_events[channel_id]
        
        await message.channel.send("このイベントチャンネルを5秒後に削除します...")
        await asyncio.sleep(5)
        
        await message.channel.delete()
        
        if category and len(category.channels) == 0:
            await category.delete()
        
        logger.info(f"イベントチャンネル {message.channel.name} を {message.author} が終了しました")
        
    except discord.Forbidden:
        await message.channel.send("チャンネルを削除する権限がありません。")
        logger.error(f"チャンネル削除権限がないため、{message.channel.name} を削除できませんでした")
    except Exception as e:
        await message.channel.send("チャンネルの削除中にエラーが発生しました。")
        logger.error(f"イベントチャンネル削除中にエラーが発生: {e}")

def register_event_commands(bot):
    """botにイベントコマンドを登録"""
    # discord.pyのコマンドとして登録することでCommandNotFoundエラーを回避
    @bot.command(name='event_start')
    async def event_start(ctx, *, event_name: str = None):
        """!event_start イベント名 - イベントチャンネルを作成"""
        if event_name is None:
            await ctx.send("イベント名を指定してください。例: `!event_start 読書会`")
            return
        await handle_event_start(bot, ctx.message, event_name)
    
    @bot.command(name='event_end')
    async def event_end(ctx):
        """!event_end - 現在のイベントチャンネルを終了"""
        await handle_event_end(bot, ctx.message)