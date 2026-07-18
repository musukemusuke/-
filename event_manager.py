import discord
import logging
import asyncio

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
        # チャンネル名を「ｲﾍﾞﾝﾄ開催中_イベント名」の形式に整形（全角スペースをアンダースコアに置換）
        display_channel_name = f"ｲﾍﾞﾝﾄ開催中_{event_name.replace(' ', '_')}"
        # Discordのチャンネル名の文字数制限(100文字)に収める
        if len(display_channel_name) > 100:
            display_channel_name = display_channel_name[:97] + "..."
        
        # 新しいテキストチャンネルを作成（カテゴリーなし、サーバーの一番上に配置）
        new_channel = await guild.create_text_channel(
            name=display_channel_name,
            topic=f"イベント: {event_name} | 作成者: {message.author.display_name} | 終了するには!event_end",
            position=0  # 一番上に配置
        )
        
        # アクティブなイベントとして記録
        active_events[new_channel.id] = message.author.id
        
        # 作成者に簡単な通知だけを送信（チャンネルへの自動投稿は行わない）
        await message.channel.send(f"イベントチャンネル {new_channel.mention} を作成しました。\n終了するときはそのチャンネルで `!event_end` と入力してください。")
        
        logger.info(f"イベントチャンネル {display_channel_name} を {message.author} が作成しました")
        
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
        await message.channel.send("このチャンネルはイベントチャンネルではないか、既に終了しています。")
        return
    
    # イベントの作成者か、サーバーの管理者か確認
    creator_id = active_events[channel_id]
    is_creator = message.author.id == creator_id
    is_admin = any(role.permissions.administrator for role in message.author.roles)
    
    if not (is_creator or is_admin):
        await message.channel.send("このイベントを終了できるのは作成者または管理者のみです。")
        return
    
    try:
        # アクティブイベントから削除
        del active_events[channel_id]
        
        # チャンネルを削除する前に通知
        await message.channel.send("このイベントチャンネルを5秒後に削除します...")
        await asyncio.sleep(5)
        
        # チャンネルを削除
        await message.channel.delete()
        
        logger.info(f"イベントチャンネル {message.channel.name} を {message.author} が終了しました")
        
    except discord.Forbidden:
        await message.channel.send("チャンネルを削除する権限がありません。")
        logger.error(f"チャンネル削除権限がないため、{message.channel.name} を削除できませんでした")
    except Exception as e:
        await message.channel.send("チャンネルの削除中にエラーが発生しました。")
        logger.error(f"イベントチャンネル削除中にエラーが発生: {e}")

async def register_event_commands(bot):
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