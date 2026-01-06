import streamlit as st
import yt_dlp
import os
import shutil

# ページ設定
st.set_page_config(page_title="Auto YouTube Downloader", layout="centered")

st.title("YouTube Downloader (自動Cookie適用済)")
st.markdown("URLを入力するだけでダウンロード可能です。")

# ── 保存先ディレクトリ ──
DOWNLOAD_DIR = "downloads"
if os.path.exists(DOWNLOAD_DIR):
    shutil.rmtree(DOWNLOAD_DIR)
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ── UI ──
with st.form("dl_form"):
    urls_text = st.text_area("URL入力欄", height=100, placeholder="https://www.youtube.com/watch?v=...")
    format_type = st.selectbox("フォーマット", ["mp3", "m4a", "wav"])
    submitted = st.form_submit_button("変換開始")

# ── 処理ロジック ──
if submitted and urls_text:
    urls = [u.strip() for u in urls_text.splitlines() if u.strip()]
    
    # --- 自動Cookieの準備 ---
    cookie_path = None
    # GitHub Secrets や Streamlit の Secrets から読み込む設定
    if "YOUTUBE_COOKIES" in st.secrets:
        cookie_path = "temp_cookies.txt"
        with open(cookie_path, "w") as f:
            f.write(st.secrets["YOUTUBE_COOKIES"])
    
    st_status = st.status("ダウンロード中...", expanded=True)
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f'{DOWNLOAD_DIR}/%(title)s.%(ext)s',
        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': format_type, 'preferredquality': '0'}],
        'quiet': True,
        'nocheckcertificate': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    }
    
    # Cookieが存在すれば適用
    if cookie_path:
        ydl_opts['cookiefile'] = cookie_path
        st_status.write("✅ 認証用Cookieを自動適用しました")

    success_count = 0
    for url in urls:
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.extract_info(url, download=True)
                st_status.write(f"✅ 完了: {url}")
                success_count += 1
        except Exception as e:
            st_status.error(f"❌ エラー: {e}")

    # 一時Cookieファイルの削除
    if cookie_path and os.path.exists(cookie_path):
        os.remove(cookie_path)

    if success_count > 0:
        shutil.make_archive("download_files", 'zip', DOWNLOAD_DIR)
        with open("download_files.zip", "rb") as fp:
            st.download_button("📥 ZIPファイルをダウンロード", data=fp, file_name="audio.zip", mime="application/zip")
