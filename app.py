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
st.write("YouTube や ニコニコ動画の URL から動画・音声を変換してダウンロードします。")

# ── 関数定義 ──

def cleanup_files():
    """以前のダウンロードファイルを削除"""
    if os.path.exists(DOWNLOAD_DIR):
        shutil.rmtree(DOWNLOAD_DIR)
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    if os.path.exists(COOKIES_FILE):
        os.remove(COOKIES_FILE)

def zip_files(directory):
    """ディレクトリ内のファイルをZIPにまとめる"""
    zip_path = "download_files.zip"
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(directory):
            for file in files:
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
    
    uploaded_cookie = st.file_uploader("Cookies.txt (任意・ニコニコ等用)", type=['txt'])
    
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

    urls = [line.strip() for line in url_text.splitlines() if line.strip()]
    
    progress_text = st.empty()
    progress_bar = st.progress(0)
    log_area = st.expander("処理ログ", expanded=True)
    
    downloaded_files = []

    with log_area:
        for i, url in enumerate(urls):
            progress_text.text(f"処理中 ({i+1}/{len(urls)}): {url}")
            st.write(f"▶ {url} の処理を開始...")
            
            # オプション設定
            is_video = 'mp4' in format_select
            fmt_clean = format_select.split(' ')[0] # 'mp4 (動画)' -> 'mp4'
            
            ydl_opts = {
                'outtmpl': f'{DOWNLOAD_DIR}/%(title)s.%(ext)s',
                'quiet': True,
                'no_warnings': True,
            }

            if cookie_path:
                ydl_opts['cookiefile'] = cookie_path

            if is_video:
                # 動画モード
                ydl_opts['format'] = 'bestvideo+bestaudio/best'
                ydl_opts['merge_output_format'] = 'mp4'
            else:
                # 音声モード
                ydl_opts['format'] = 'bestaudio/best'
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': fmt_clean,
                    'preferredquality': quality_select.split(' ')[0],
                }]
                
                # WAV以外ならサムネイル埋め込み
                if embed_thumb and fmt_clean != 'wav':
                    ydl_opts['writethumbnail'] = True
                    ydl_opts['postprocessors'].append({'key': 'EmbedThumbnail'})
                    ydl_opts['postprocessors'].append({'key': 'FFmpegMetadata'})

            # ダウンロード実行
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    title = info.get('title', 'video')
                    st.success(f"✔ 完了: {title}")
                    
                    # サムネイル表示（任意）
                    thumb = info.get('thumbnail')
                    if thumb:
                        st.image(thumb, width=150)
                        
            except Exception as e:
                st.error(f"✖ エラー: {e}")

            progress_bar.progress((i + 1) / len(urls))

    # ── ダウンロードボタンの表示 ──
    files = os.listdir(DOWNLOAD_DIR)
    if files:
        st.success("すべての処理が完了しました！")
        
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
                    label="⬇ まとめてダウンロード (ZIP)",
                    data=f,
                    file_name="downloads.zip",
                    mime="application/zip"
                )
    else:
        st.warning("ダウンロードされたファイルが見つかりませんでした。")
