import io
import asyncio
import unicodedata
import os
import discord
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PIL import Image
import pypdfium2 as pdfium
from utils import setup_logger, get_ids_from_env

# ロガーの初期化
logger = setup_logger(__name__)

# アーカイブ用チャンネルID（環境変数から読み込み）
ARCHIVE_CHANNEL_IDS = get_ids_from_env('ARCHIVE_CHANNEL_ID')
ARCHIVE_CHANNEL_ID = ARCHIVE_CHANNEL_IDS[0] if ARCHIVE_CHANNEL_IDS else None
if not ARCHIVE_CHANNEL_ID:
    logger.warning("ARCHIVE_CHANNEL_IDが環境変数に設定されていません。アーカイブ機能は無効化されます。")

# チャット履歴をPDFに生成し画像に変換する関数
def create_chat_pdf(messages, channel_name):
    # PDFの基本設定：Discordのチャット欄のアスペクト比に近いサイズに調整（幅800px相当、高さは可変）
    # 単位をポイントに変換（1px ≈ 0.75pt、Discordのチャットは通常幅約800pxで表示されるため、それに合わせる）
    discord_chat_width = 600  # pt単位（800px * 0.75）
    page_height = 841.89  # A4の高さを維持（長いチャットでも複数ページで対応）
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(discord_chat_width, page_height))
    width, height = discord_chat_width, page_height
    
    # 日本語フォントを登録（環境に応じて自動選択）
    try:
        # Windows環境: MSゴシック
        font_path = "msgothic.ttc"
        pdfmetrics.registerFont(TTFont('jp_font', font_path))
        logger.info("create_chat_pdf: MSゴシックフォントを使用")
    except Exception as e:
        logger.warning(f"create_chat_pdf: MSゴシック登録失敗: {e}")
        try:
            # Linux環境: Ubuntuでインストール可能なIPAフォント（ttf形式でReportLabと互換性あり）
            font_paths = [
                "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
                "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",
                "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttf",
            ]
            font_path = None
            for path in font_paths:
                if os.path.exists(path):
                    font_path = path
                    break
            if font_path:
                pdfmetrics.registerFont(TTFont('jp_font', font_path))
                logger.info(f"create_chat_pdf: Linux用IPAゴシックフォントを使用 (path={font_path})")
            else:
                raise Exception("フォントがどのパスにも存在しません")
        except Exception as e:
            logger.error(f"create_chat_pdf: Linuxフォント登録失敗: {e}")
            # フォント一覧を出力
            import glob
            font_files = glob.glob("/usr/share/fonts/**/*.ttf", recursive=True) + glob.glob("/usr/share/fonts/**/*.ttc", recursive=True)
            logger.debug(f"利用可能なフォントファイル: {font_files}")
            raise
    
    # 背景色を設定（PDFは黒背景にするために矩形を描画）
    c.setFillColorRGB(54/255, 57/255, 63/255)  # Discordの黒背景色
    c.rect(0, 0, width, height, fill=True, stroke=False)
    
    # テキスト描画設定：Discordの表示サイズに合わせて調整
    margin = 30  # ページの左右余白を狭くする
    line_height = 22  # 1行の高さをDiscordの行間に近づける
    current_y = height - margin  # 上から描画開始
    page_num = 1  # 現在のページ番号
    
    # タイトルを描画（白色）
    c.setFillColorRGB(1, 1, 1)  # 白
    c.setFont("jp_font", 18)
    c.drawString(margin, current_y, f"アーカイブ: {channel_name}")
    current_y -= line_height * 2  # タイトル分のスペース
    
    # メッセージを1件ずつ描画：Discordのフォントサイズ（14px相当）に合わせる
    c.setFont("jp_font", 11)
    for idx, message in enumerate(messages):
        # 特殊文字を可能な限り通常の文字に変換（おしゃれフォント対策）
        author = message.author.display_name
        # 特殊な太文字・斜体文字をASCIIに変換する簡易的な処理（NFKC正規化）
        author = unicodedata.normalize('NFKC', author)
        content = message.content if message.content else "(添付ファイル等)"
        content = unicodedata.normalize('NFKC', content)
        
        # ページの下まで来たら新しいページを作成
        if current_y < margin + line_height:
            c.showPage()
            page_num += 1
            # 新しいページの背景を描画
            c.setFillColorRGB(54/255, 57/255, 63/255)
            c.rect(0, 0, width, height, fill=True, stroke=False)
            c.setFillColorRGB(1, 1, 1)
            c.setFont("jp_font", 12)
            current_y = height - margin
        
        # ユーザー名をDiscordと同じ青色で描画
        c.setFillColorRGB(114/255, 137/255, 218/255)  # Discordのユーザー名青色
        # メッセージ内容を白色で描画
        c.setFillColorRGB(1, 1, 1)
        # 作者名の後にスペースを入れてDiscordの表示に近づける
        author_text = f"{author}: "
        author_text_width = pdfmetrics.stringWidth(author_text, "jp_font", 11)
        c.drawString(margin, current_y, author_text)
        # 1行に描画可能な最大文字数を計算（横幅に合わせて自動改行、Discordの折り返しに合わせる）
        available_width_first_line = width - margin - author_text_width
        available_width = width - margin * 2
        
        # テキストを自動的に改行する関数
        def wrap_text(text, max_width, font_name, font_size):
            words = list(text)  # 日本語は1文字ずつ処理
            lines = []
            current_line = ""
            for char in words:
                test_line = current_line + char
                if pdfmetrics.stringWidth(test_line, font_name, font_size) <= max_width:
                    current_line = test_line
                else:
                    lines.append(current_line)
                    current_line = char
            if current_line:
                lines.append(current_line)
            return lines
        
        # 元の改行で分割しつつ、長い行は自動改行
        raw_lines = content.split('\n')
        all_content_lines = []
        for line in raw_lines:
            if not line:
                all_content_lines.append("")
                continue
            # 1行目は作者名の後ろから描画するので幅が狭い
            if not all_content_lines:
                wrapped = wrap_text(line, available_width_first_line, "jp_font", 12)
            else:
                wrapped = wrap_text(line, available_width, "jp_font", 12)
            all_content_lines.extend(wrapped)
        
        # 最初の行を作者名の横に描画
        if all_content_lines:
            first_content_line = all_content_lines[0]
            c.drawString(margin + author_text_width, current_y, first_content_line)
            # 残りの行を下に描画
            for line in all_content_lines[1:]:
                current_y -= line_height
                if current_y < margin:
                    # ページをめくる
                    c.showPage()
                    page_num += 1
                    c.setFillColorRGB(54/255, 57/255, 63/255)
                    c.rect(0, 0, width, height, fill=True, stroke=False)
                    c.setFillColorRGB(1, 1, 1)
                    c.setFont("jp_font", 12)
                    current_y = height - margin
                c.drawString(margin, current_y, line)
        
        current_y -= line_height
    
    # 最後にフッターを描画
    if current_y < margin + line_height:
        c.showPage()
        page_num += 1
        c.setFillColorRGB(54/255, 57/255, 63/255)
        c.rect(0, 0, width, height, fill=True, stroke=False)
        current_y = height - margin
    c.setFillColorRGB(185/255, 187/255, 190/255)  # 薄い灰色
    c.setFont("jp_font", 10)
    c.drawString(margin, current_y, f"全{len(messages)}件のメッセージ / {page_num}ページ")
    
    # PDFを保存
    c.save()
    buffer.seek(0)
    print(f"create_chat_pdf: PDF生成完了、チャンネル名={channel_name}, メッセージ数={len(messages)}, ページ数={page_num}")
    
    # PDFを画像に変換
    try:
        print("PDFを画像に変換開始")
        # 一時ファイルにPDFを保存してから開く（pypdfium2の互換性対策）
        with open("temp.pdf", "wb") as f:
            f.write(buffer.getvalue())
        pdf = pdfium.PdfDocument("temp.pdf")
        # 複数ページがある場合は全ページを縦に連結した画像を作成
        page_images = []
        for page in pdf:
            bitmap = page.render(scale=2)  # 高解像度でレンダリング
            pil_image = bitmap.to_pil()
            page_images.append(pil_image)
        
        # 全ページを連結して1枚の画像にする
        total_width = max(img.width for img in page_images)
        total_height = sum(img.height for img in page_images)
        combined_image = Image.new('RGB', (total_width, total_height))
        y_offset = 0
        for img in page_images:
            combined_image.paste(img, (0, y_offset))
            y_offset += img.height
        
        # 連結した画像をBytesIOに保存
        img_buffer = io.BytesIO()
        combined_image.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        # 一時ファイルを削除
        os.remove("temp.pdf")
        print("PDFから画像への変換完了")
        # PDFバッファを巻き戻して返却
        buffer.seek(0)
        return buffer, img_buffer
    except Exception as e:
        print(f"PDFから画像への変換に失敗: {e}")
        import traceback
        traceback.print_exc()
        # 一時ファイルが残っていたら削除
        if os.path.exists("temp.pdf"):
            os.remove("temp.pdf")
        # 画像変換に失敗してもPDFは返却する
        buffer.seek(0)
        return buffer, None

# テキストチャンネルのメッセージ履歴をPDFと画像でアーカイブチャンネルに送信する関数
async def archive_text_channel_history(channel, bot):
    if ARCHIVE_CHANNEL_ID == 0:
        print("アーカイブチャンネルIDが設定されていないため、履歴を保存できませんでした。")
        return
    archive_channel = bot.get_channel(ARCHIVE_CHANNEL_ID)
    if not archive_channel or not isinstance(archive_channel, discord.TextChannel):
        print("アーカイブチャンネルが見つからないか、テキストチャンネルではありません。")
        return
    
    # チャンネルのメッセージを全て取得（古い順に並べ替え）
    messages = []
    # Bot以外の全てのメッセージをアーカイブ（コマンド機能を使用しないため除外不要）
    async for message in channel.history(limit=None, oldest_first=True):
        if not message.author.bot:
            messages.append(message)
    
    if not messages:
        print(f"{channel.name} のメッセージは0件だったのでアーカイブしませんでした。")
        return
    
    # チャットPDFを生成
    try:
        import traceback
        print(f"PDF生成開始: {channel.name}, メッセージ数: {len(messages)}")
        pdf_file, img_file = create_chat_pdf(messages, channel.name)
        print("PDF生成完了、ファイルオブジェクト作成")
        # 添付ファイルを準備
        files = []
        pdf_discord_file = discord.File(pdf_file, filename=f"{channel.name}_archive.pdf")
        files.append(pdf_discord_file)
        # 画像が生成できていれば追加で送信
        if img_file:
            img_discord_file = discord.File(img_file, filename=f"{channel.name}_archive.png")
            files.append(img_discord_file)
        print("discord.File作成完了、送信開始")
        # 全サーバーメンバーがアーカイブを見返せるように権限を設定（会話の履歴を共有）
        # Discordの自動権限同期を完全に無効化し、手動で純粋な権限状態を作る
        await archive_channel.edit(sync_permissions=False)
        # 全ての既存の権限上書きをリセット（実行環境のdiscord.pyバージョンに合わせた方法）
        for target, overwrite in list(archive_channel.overwrites.items()):
            await archive_channel.set_permissions(target, read_messages=False, send_messages=False, read_message_history=False)
        # 必要な権限だけを設定：サーバーオーナーとBotだけが閲覧可能（鯖主専用設定）
        await archive_channel.set_permissions(archive_channel.guild.default_role, read_messages=False, send_messages=False, read_message_history=False)
        await archive_channel.set_permissions(archive_channel.guild.owner, read_messages=True, send_messages=True, read_message_history=True)
        await archive_channel.set_permissions(bot.user, read_messages=True, send_messages=True)
        print("アーカイブの権限設定完了: サーバーオーナーだけがアーカイブを閲覧できるようになりました")
        
        await archive_channel.send(f"📦 **アーカイブ: {channel.name}**（元ボイスチャンネル: {channel.name.replace('聞き専用-', '')}）", files=files)
        # サーバー側の自動同期で発生する余分な権限上書きを完全に消去する最終処理
        await asyncio.sleep(3)
        for target, overwrite in list(archive_channel.overwrites.items()):
            if not isinstance(target, discord.Member) and target != archive_channel.guild.default_role and target != archive_channel.guild.owner and target != bot.user:
                await archive_channel.set_permissions(target, read_messages=False, send_messages=False, read_message_history=False)
        print(f"{channel.name} のアーカイブが完全に完了しました。全{len(messages)}件のメッセージを保存し、全ての余分な権限上書きを削除しました。")
        
        # アーカイブ完了後、元のテキストチャンネルの全メッセージを一括削除（常設ボイスで常に最新の会話だけを残す）
        try:
            deleted = await channel.purge(limit=None)
            print(f"元のテキストチャンネル{channel.name}の{len(deleted)}件のメッセージを削除しました。常設ボイスのチャンネルをクリーンに保ちます。")
        except Exception as purge_e:
            print(f"メッセージ削除中にエラーが発生しました: {purge_e}")
    except Exception as e:
        print(f"PDF生成中にエラーが発生しました: {e}")
        print(traceback.format_exc())
        # PDF生成に失敗した場合はテキストでフォールバック
        await archive_channel.send(f"📦 **アーカイブ: {channel.name}**（元ボイスチャンネル: {channel.name.replace('聞き専用-', '')}）")
        for message in messages:
            content = f"**{message.author.display_name}**: {message.content}" if message.content else f"**{message.author.display_name}**: (添付ファイル等)"
            if len(content) > 1900:
                for i in range(0, len(content), 1900):
                    await archive_channel.send(content[i:i+1900])
            else:
                await archive_channel.send(content)
        await archive_channel.send(f"✅ {channel.name} のテキストアーカイブが完了しました。全{len(messages)}件のメッセージを保存しました。\n---")
        
        # PDF生成失敗時も元のテキストチャンネルのメッセージを削除
        try:
            deleted = await channel.purge(limit=None)
            print(f"テキストアーカイブ完了後、元のテキストチャンネル{channel.name}の{len(deleted)}件のメッセージを削除しました。")
        except Exception as purge_e:
            print(f"メッセージ削除中にエラーが発生しました: {purge_e}")