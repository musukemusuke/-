import discord
import asyncio
import os
import logging

from utils import set_permissions_with_retry, get_ids_from_env, metrics, setup_logger

logger = setup_logger(__name__)

async def process_member(bot, member, guild, read_only_channel_ids, archive_channel_id, old_display_name=None):
    if member.bot:
        return
    metrics['members_processed'] += 1
    logger.debug(f"process_member: メンバー {member.display_name}, ギルド {guild.name}, read_only_channel_ids: {read_only_channel_ids}, old_display_name: {old_display_name}")

    # ニックネーム変更があった場合、古い個人ロールを削除
    if old_display_name:
        old_role_name = old_display_name[:100]
        old_personal_role = discord.utils.get(guild.roles, name=old_role_name)
        if old_personal_role and old_personal_role in member.roles:
            try:
                await member.remove_roles(old_personal_role, reason=f"ニックネーム変更に伴い古い個人ロール {old_role_name} を削除")
                logger.info(f"メンバー {member.display_name} から古い個人ロール {old_role_name} を削除しました。")
            except discord.Forbidden:
                logger.error(f"権限不足でメンバー {member.display_name} から古い個人ロール {old_role_name} を削除できません。")
            except Exception as e:
                logger.error(f"古い個人ロール {old_role_name} の削除中にエラーが発生しました: {e}")

    role_name = member.display_name[:100]
    target_role = None

    existing_member_role = next((r for r in member.roles if r.name == role_name), None)
    
    if existing_member_role:
        logger.debug(f"メンバー {member.display_name} は既に個人ロール {role_name} を持っています。")
        target_role = existing_member_role
    else:
        existing_guild_role = next((r for r in guild.roles if r.name == role_name), None)
        
        if existing_guild_role:
            logger.info(f"メンバー {member.display_name} に個人ロール {role_name} が付与されていませんが、サーバーに既存のロールがあります。付与します。")
            target_role = existing_guild_role
            try:
                await member.add_roles(target_role, reason=f"メンバー {member.display_name} に既存の個人ロール {role_name} を再付与")
                logger.info(f"メンバー {member.display_name} に既存の個人ロール {role_name} を付与しました。ロールID: {target_role.id}")
            except discord.Forbidden:
                logger.error(f"権限不足でメンバー {member.display_name} に既存の個人ロール {role_name} を付与できません。Botのロールがサーバー内で最上位に配置されているか、ロール管理権限が有効になっているか確認してください。")
                return
            except discord.HTTPException as e:
                logger.error(f"メンバー {member.display_name} に既存の個人ロール {role_name} を付与中にDiscord APIエラーが発生しました。ステータスコード: {e.status}, エラーメッセージ: {e.text}")
                return
            except Exception as e:
                logger.error(f"メンバー {member.display_name} に既存の個人ロール {role_name} を付与中に予期せぬエラーが発生しました: {type(e).__name__}: {str(e)}")
                return
        else:
            placeholder_role_name = "新しいロール"
            placeholder_roles = [r for r in guild.roles if r.name == placeholder_role_name]
            available_placeholder = None
            for role in placeholder_roles:
                is_used_by_other = any(role in m.roles and m != member for m in guild.members)
                if not is_used_by_other:
                    available_placeholder = role
                    break

            if available_placeholder:
                logger.info(f"メンバー {member.display_name} の個人ロール '{role_name}' が見つかりませんでしたが、未使用のプレースホルダーロール '{placeholder_role_name}' を発見しました。これを個人ロールとして変換します。")
                try:
                    await available_placeholder.edit(name=role_name, reason=f"プレースホルダーロール '{placeholder_role_name}' を {member.display_name} の個人ロールに変換")
                    logger.info(f"ロール '{placeholder_role_name}' を '{role_name}' にリネームしました。")

                    role_color = discord.Color.random()
                    member_permissions = discord.Permissions()
                    member_permissions.view_channel = True
                    member_permissions.send_messages = True
                    member_permissions.read_message_history = True
                    member_permissions.add_reactions = True
                    member_permissions.embed_links = True
                    member_permissions.attach_files = True
                    member_permissions.external_emojis = True
                    member_permissions.external_stickers = True
                    member_permissions.send_messages_in_threads = True
                    member_permissions.send_polls = True
                    member_permissions.use_application_commands = True
                    member_permissions.mention_everyone = False
                    member_permissions.connect = True
                    member_permissions.speak = True
                    member_permissions.stream = True
                    member_permissions.use_voice_activation = True
                    member_permissions.set_voice_channel_status = True
                    member_permissions.use_embedded_activities = True
                    member_permissions.create_expressions = True
                    member_permissions.change_nickname = True

                    await available_placeholder.edit(color=role_color, permissions=member_permissions, reason=f"{member.display_name} の個人ロールの権限と色を設定")
                    logger.info(f"個人ロール '{role_name}' の色と権限を設定しました。")

                    await member.add_roles(available_placeholder)
                    logger.info(f"メンバー {member.display_name} に変換された個人ロール '{role_name}' を付与しました。ロールID: {available_placeholder.id}")
                    metrics['roles_created'] += 1
                    target_role = available_placeholder

                except discord.Forbidden:
                    logger.error(f"権限不足でプレースホルダーロール '{placeholder_role_name}' を {member.display_name} の個人ロールに変換できません。Botのロールがサーバー内で最上位に配置されているか、ロール管理権限が有効になっているか確認してください。")
                    return
                except discord.HTTPException as e:
                    logger.error(f"プレースホルダーロール '{placeholder_role_name}' を {member.display_name} の個人ロールに変換中にDiscord APIエラーが発生しました。ステータスコード: {e.status}, エラーメッセージ: {e.text}")
                    return
                except Exception as e:
                    logger.error(f"プレースホルダーロール '{placeholder_role_name}' を {member.display_name} の個人ロールに変換中に予期せぬエラーが発生しました: {type(e).__name__}: {str(e)}")
                    return
            else:
                logger.info(f"メンバー {member.display_name} に個人ロール {role_name} が付与されておらず、サーバーにも存在せず、プレースホルダーロール '{placeholder_role_name}' も見つからないため、新しく作成します。")
                role_color = discord.Color.random()
                member_permissions = discord.Permissions()
                member_permissions.view_channel = True
                member_permissions.send_messages = True
                member_permissions.read_message_history = True
                member_permissions.add_reactions = True
                member_permissions.embed_links = True
                member_permissions.attach_files = True
                member_permissions.external_emojis = True
                member_permissions.external_stickers = True
                member_permissions.send_messages_in_threads = True
                member_permissions.send_polls = True
                member_permissions.use_application_commands = True
                member_permissions.mention_everyone = False
                member_permissions.connect = True
                member_permissions.speak = True
                member_permissions.stream = True
                member_permissions.use_voice_activation = True
                member_permissions.set_voice_channel_status = True
                member_permissions.use_embedded_activities = True
                member_permissions.create_expressions = True
                member_permissions.change_nickname = True

                try:
                    new_role = await guild.create_role(
                        name=role_name,
                        color=role_color,
                        permissions=member_permissions,
                        reason=f"Bot起動時にロールがなかったため {member.display_name} の個人ロールを作成"
                    )
                    await member.add_roles(new_role)
                    logger.info(f"メンバー {member.display_name} に新しい個人ロールを付与しました。ロールID: {new_role.id}")
                    metrics['roles_created'] += 1
                    target_role = new_role
                except discord.Forbidden:
                    logger.error(f"権限不足でメンバー {member.display_name} の個人ロールを作成できません。Botのロールがサーバー内で最上位に配置されているか、ロール管理権限が有効になっているか確認してください。")
                    return
                except discord.HTTPException as e:
                    logger.error(f"メンバー {member.display_name} の個人ロール作成中にDiscord APIエラーが発生しました。ステータスコード: {e.status}, エラーメッセージ: {e.text}")
                    return
                except Exception as e:
                    logger.error(f"メンバー {member.display_name} の個人ロール作成中に予期せぬエラーが発生しました: {type(e).__name__}: {str(e)}")
                    return

    if target_role:
        if archive_channel_id != 0:
            for channel in guild.channels:
                # テキストチャンネルかつ、@everyoneが閲覧できないプライベートチャンネルは自動権限設定の対象外にする
                if isinstance(channel, discord.TextChannel) and not channel.permissions_for(guild.default_role).view_channel:
                    logger.debug(f"チャンネル {channel.name} はプライベートなテキストチャンネルのため、自動権限設定をスキップします。")
                    continue

                if channel.id == archive_channel_id:
                    continue
                if channel.id in read_only_channel_ids:
                    logger.debug(f"process_member: チャンネル {channel.name} ({channel.id}) は読み取り専用チャンネルです。個人ロール {target_role.name} のメッセージ送信権限を無効にします。")
                    await set_permissions_with_retry(channel, target_role, {"view_channel": True, "send_messages": False}, logger=logger)
                else:
                    logger.debug(f"process_member: チャンネル {channel.name} ({channel.id}) は通常チャンネルです。個人ロール {target_role.name} のメッセージ送信権限を有効にします。")
                    await set_permissions_with_retry(channel, target_role, {"view_channel": True, "send_messages": True}, logger=logger)
                logger.debug(f"チャンネル {channel.name} で {target_role.name} の権限を設定しました。")

async def process_guild(bot, guild, read_only_channel_ids, archive_channel_id):
    logger.info(f"サーバー {guild.name} のメンバーをチェックしています...")
    tasks = [process_member(bot, member, guild, read_only_channel_ids, archive_channel_id) for member in guild.members]
    await asyncio.gather(*tasks)
    logger.info(f"サーバー {guild.name} のメンバーチェックが完了しました。")

async def ensure_personal_roles_exist(bot, read_only_channel_ids, archive_channel_id):
    while True:
        logger.info("定期タスク: 個人ロールの存在確認を開始します。")
        for guild in bot.guilds:
            logger.info(f"ギルド {guild.name} のメンバーの個人ロールを確認中...")
            tasks = [process_member(bot, member, guild, read_only_channel_ids, archive_channel_id) for member in guild.members]
            await asyncio.gather(*tasks)
            logger.info(f"ギルド {guild.name} の個人ロール確認が完了しました。")
        await asyncio.sleep(24 * 60 * 60)

async def cleanup_orphaned_roles(bot):
    await bot.wait_until_ready()
    while not bot.is_closed():
        for guild in bot.guilds:
            logger.info(f"ギルド {guild.name} の孤立した個人ロールのクリーンアップを開始します。")
            all_member_role_ids = set()
            for member in guild.members:
                if not member.bot:
                    for role in member.roles:
                        all_member_role_ids.add(role.id)
            
            for role in guild.roles:
                if role.name == "bot":
                    continue
                if role.id not in all_member_role_ids and role < guild.me.top_role and role != guild.default_role:
                    try:
                        await role.delete(reason="誰も保持していない孤立した個人ロールのため削除")
                        logger.info(f"孤立した個人ロール {role.name} を削除しました。")
                    except Exception as e:
                        logger.error(f"孤立ロール {role.name} の削除に失敗しました: {e}")
        await asyncio.sleep(86400)

def setup(bot, read_only_channel_ids, archive_channel_id):
    bot.loop.create_task(ensure_personal_roles_exist(bot, read_only_channel_ids, archive_channel_id))
    bot.loop.create_task(cleanup_orphaned_roles(bot))
    logger.info("Role manager tasks scheduled.")