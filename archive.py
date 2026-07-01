import os
import io
import traceback
import discord
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PIL import Image
import pypdfium2 as pdfium

# チャット履歴をPDFに生成して画像にも変換する関数
def create_chat_archive(messages, channel_name):
    # PDFの基本設定（A4サイズ）
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4  # A4のサイズを取得
    
    # 日本語フォントを登録（環境に応じて自動選択）
    try:
        # Windows環境: MSゴシック
        font_path = "msgothic.ttc"
        pdfmetrics.registerFont(TTFont('jp_font', font_path))
        print("create_chat_archive: MSゴシックフォントを使用")
    except Exception as e:
        print(f"create_chat_archive: MSゴシック登録失敗: {e}")
        try:
            # Linux環境: Ubuntu標準のNoto Sans CJK JP
            font_paths = [
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/NotoSansCJK-Regular.ttc",
            ]
            font_path = None
            for path in font_paths:
                if os.path.exists(path):
                    font_path = path
                    break
            if font_path:
                pdfmetrics.registerFont(TTFont('jp_font', font_path))
                print(f"create_chat_archive: Noto Sansフォントを使用 (path={font_path})")
            else:
                raise Exception("フォントがどのパスにも存在しません")
        except Exception as e:
            print(f"create_chat_archive: フォント登録失敗: {e}")
            import glob
            font_files = glob.glob("/usr/share/fonts/**/*.ttc", recursive=True) + glob.glob("/usr/share/fonts/**/*.ttf", recursive=True)
            print(f"利用可能なフォントファイル: {font_files}")
            raise
    
    # 背景色を設定（PDFは黒背景にするために矩形を描画）
    c.setFillColorRGB(54/255, 57/255, 63/255)  # Discordの黒背景色
    c.rect(0, 0, width, height, fill=True, stroke=False)
    
    # テキスト描画設定
    margin = 50  # ページの余白
    line_height = 25  # 1行の高さ
    current_y = height - margin  # 上から描画開始
    page_num = 1  # 現在のページ番号
    
    # タイトルを描画（白色）
    c.setFillColorRGB(1, 1, 1)  # 白
    c.setFont("jp_font", 20)
    c.drawString(margin, current_y, f"アーカイブ: {channel_name}")
    current_y -= line_height * 2  # タイトル分のスペース
    
    # メッセージを1件ずつ描画
    c.setFont("jp_font", 12)
    for idx, message in enumerate(messages):
        author = message.author.display_name
        content = message.content if message.content else "(添付ファイル等)"
        
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
        
        # ユーザー名を青色で描画
        c.setFillColorRGB(114/255, 137/255, 218/255)  # Discordの青色
        c.drawString(margin, current_y, f"{author}:")
        
        # メッセージ内容を白色で描画
        c.setFillColorRGB(1, 1, 1)
        author_text_width = pdfmetrics.stringWidth(f"{author}: ", "jp_font", 12)
        # 長いメッセージは改行して描画
        content_lines = content.split('\n')
        first_line = content_lines[0]
        c.drawString(margin + author_text_width, current_y, first_line)
        # 2行目以降を描画
        for line in content_lines[1:]:
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
    c.drawString(margin, current_y, f"全{len(messages)}件のメッセージ / {page_num}ページ")
    
    # PDFを保存
    c.save()
    buffer.seek(0)
    print(f"create_chat_archive: PDF生成完了、チャンネル名={channel_name}, メッセージ数={len(messages)}, ページ数={page_num}")
    
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
        traceback.print_exc()
        # 一時ファイルが残っていたら削除
        if os.path.exists("temp.pdf"):
            os.remove("temp.pdf")
        # 画像変換に失敗してもPDFは返却する
        buffer.seek(0)
        return buffer, None

# テキストチャンネルのメッセージ履歴をアーカイブチャンネルに送信する関数
async def archive_text_channel_history(bot, channel, ARCHIVE_CHANNEL_ID):
    if ARCHIVE_CHANNEL_ID == 0:
        print("アーカイブチャンネルIDが設定されていないため、履歴を保存できませんでした。")
        return
    archive_channel = bot.get_channel(ARCHIVE_CHANNEL_ID)
    if not archive_channel or not isinstance(archive_channel, discord.TextChannel):
        print("アーカイブチャンネルが見つからないか、テキストチャンネルではありません。")
        return
    messages = []
    async for message in channel.history(limit=None, oldest_first=True):
        if not message.author.bot:  # botのメッセージは除外
            messages.append(message)
    if not messages:
        print(f"{channel.name} のメッセージは0件だったのでアーカイブしませんでした。")
        return
    # チャットPDFを生成
    try:
        print(f"PDF生成開始: {channel.name}, メッセージ数: {len(messages)}")
        pdf_file, img_file = create_chat_archive(messages, channel.name)
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
        await archive_channel.send(f"📦 **アーカイブ: {channel.name}**（元ボイスチャンネル: {channel.name.replace('聞き専用-', '')}）", files=files)
        print(f"{channel.name} のアーカイブが完了しました。全{len(messages)}件のメッセージを保存しました。")
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