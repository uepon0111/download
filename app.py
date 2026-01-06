import streamlit as st
import yt_dlp
import os
import shutil
import time
from pathlib import Path
import zipfile

# ── 設定 ──
DOWNLOAD_DIR = "downloads"
COOKIES_FILE = "cookies.txt"

# ページ設定
st.set_page_config(page_title="動画ダウンローダー", layout="centered")
st.title("🎥 動画/音声 ダウンローダー")
st.write("Streamlit Cloud 上で動作します。YouTube の制限によりダウンロードが不安定な場合があります。")
st.info("💡 うまくいかない場合は、ブラウザの Cookie ファイルをアップロードする方法を試してください。最も確実です。")

# ── 関数定義 ──

def cleanup_files():
    """以前のダウンロードファイルを削除"""
    if os.path.exists(DOWNLOAD_DIR):
        shutil.rmtree(DOWNLOAD_DIR)
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    # cookiesは保持する
    # if os.path.exists(COOKIES_FILE):
    #     os.remove(COOKIES_FILE)

def zip_files(directory):
    """ディレクトリ内のファイルをZIPにまとめる"""
    zip_path = "download_files.zip"
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(directory):
            for file in files:
                if file != zip_path:
                    zipf.write(os.path.join(root, file), file)
    return zip_path

# ── UI 構成 ──

with st.form("input_form"):
    url_text = st.text_area("URL入力欄 (改行区切り)", height=100, placeholder="https://www.youtube.com/watch?v=...")
    
    col1, col2 = st.columns(2)
    with col1:
        format_select = st.selectbox("フォーマット", options=['mp3', 'm4a', 'wav', 'mp4 (動画)'], index=0)
    with col2:
        quality_select = st.selectbox("音質/画質", options=['0 (最高)', '5 (標準)', '9 (低)'], index=0)
    
    embed_thumb = st.checkbox("サムネイル埋め込み (音声のみ)", value=True)
    
    uploaded_cookie = st.file_uploader("Cookies.txt (推奨・エラー回避用)", type=['txt'], help="YouTubeの制限を回避するために、ブラウザのcookies.txtをアップロードすることを強く推奨します。")
    
    submitted = st.form_submit_button("変換・ダウンロード開始", type="primary")

# ── 処理実行 ──

if submitted and url_text:
    cleanup_files() # リセット
    
    # Cookieの保存
    cookie_path = None
    if uploaded_cookie is not None:
        with open(COOKIES_FILE, "wb") as f:
            f.write(uploaded_cookie.getbuffer())
        cookie_path = COOKIES_FILE
        st.success("Cookieファイルを適用しました。")

    urls = [line.strip() for line in url_text.splitlines() if line.strip()]
    
    progress_text = st.empty()
    progress_bar = st.progress(0)
    log_area = st.expander("処理ログ (デバッグ情報)", expanded=True)
    
    with log_area:
        for i, url in enumerate(urls):
            progress_text.text(f"処理中 ({i+1}/{len(urls)}): {url}")
            st.write(f"---")
            st.write(f"▶ **開始**: `{url}`")
            
            # オプション設定
            is_video = 'mp4' in format_select
            fmt_clean = format_select.split(' ')[0] # 'mp4 (動画)' -> 'mp4'
            
            # 基本オプション
            ydl_opts = {
                'outtmpl': f'{DOWNLOAD_DIR}/%(title)s.%(ext)s',
                'quiet': False, # ログを出すように変更
                'no_warnings': True,
                'nocheckcertificate': True,
                # 'ignoreerrors': True, # ←★ これが原因の可能性が高いので削除。エラーを隠蔽させない。
                'logtostderr': False,
                'source_address': '0.0.0.0', 
                # User-Agent偽装
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            }

            if cookie_path:
                ydl_opts['cookiefile'] = cookie_path
                st.write("ℹ️ Cookieを使用します。")

            if is_video:
                st.write("ℹ️ 動画モードでダウンロードします。")
                ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
            else:
                st.write(f"ℹ️ 音声モード ({fmt_clean}) で変換します。")
                ydl_opts['format'] = 'bestaudio/best'
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': fmt_clean,
                    'preferredquality': quality_select.split(' ')[0],
                }]
                
                if embed_thumb and fmt_clean != 'wav':
                    ydl_opts['writethumbnail'] = True
                    ydl_opts['postprocessors'].append({'key': 'EmbedThumbnail'})
                    # メタデータ埋め込みはトラブルの元になることがあるので一旦外す
                    # ydl_opts['postprocessors'].append({'key': 'FFmpegMetadata'}) 
                    st.write("ℹ️ サムネイルを埋め込みます。")

            # ダウンロード実行
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    # 詳細な情報を取得
                    info = ydl.extract_info(url, download=True)
                    title = info.get('title', 'video')
                    st.success(f"✔ 処理完了: {title}")
                    
                    # サムネイル表示
                    thumb = info.get('thumbnail')
                    if thumb:
                        st.image(thumb, width=200)
                    
                    # デバッグ：フォルダの中身を確認
                    files_in_dir = os.listdir(DOWNLOAD_DIR)
                    st.write(f"📁 現在の保存フォルダの中身: `{files_in_dir}`")
                        
            except Exception as e:
                st.error(f"✖ エラー発生: {e}")
                st.error("考えられる原因: YouTube側の制限、またはFFmpegによる変換エラー。Cookieの利用を検討してください。")

            progress_bar.progress((i + 1) / len(urls))

    # ── ダウンロードボタンの表示 ──
    files = [f for f in os.listdir(DOWNLOAD_DIR) if not f.endswith('.zip')]
    
    st.write("---")
    if files:
        st.success("✅ すべての処理が完了しました。以下のボタンからダウンロードしてください。")
        
        # ファイルが1つの場合
        if len(files) == 1:
            file_path = os.path.join(DOWNLOAD_DIR, files[0])
            with open(file_path, "rb") as f:
                st.download_button(
                    label=f"⬇ {files[0]} をダウンロード",
                    data=f,
                    file_name=files[0],
                    mime="application/octet-stream"
                )
        # 複数ファイルの場合（ZIPにする）
        else:
            zip_path = zip_files(DOWNLOAD_DIR)
            with open(zip_path, "rb") as f:
                st.download_button(
                    label=f"⬇ まとめてダウンロード (ZIP) - {len(files)}ファイル",
                    data=f,
                    file_name="downloads.zip",
                    mime="application/zip"
                )
    else:
        st.warning("⚠️ ダウンロード可能なファイルが見つかりませんでした。処理ログのエラーを確認してください。")
