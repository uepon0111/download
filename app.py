import streamlit as st
import yt_dlp
import os
import shutil
import time
from zipfile import ZipFile

# ページ設定
st.set_page_config(page_title="YouTube Downloader", layout="centered")

st.title("YouTube/Video Downloader")
st.markdown("スマホ・PCからダウンロード可能です。エラーが出る場合はCookiesを使用してください。")

# ── 保存先ディレクトリの準備 ──
DOWNLOAD_DIR = "downloads"
if os.path.exists(DOWNLOAD_DIR):
    shutil.rmtree(DOWNLOAD_DIR)
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ── UI部分 ──
with st.form("dl_form"):
    urls_text = st.text_area("URL入力欄 (改行区切り)", height=100, placeholder="https://www.youtube.com/watch?v=...")
    
    col1, col2 = st.columns(2)
    with col1:
        format_type = st.selectbox("フォーマット", ["mp3", "m4a", "wav"], index=0)
    with col2:
        quality = st.selectbox("音質", ["0 (最高)", "1 (高)", "5 (標準)"], index=0)
    
    embed_thumb = st.checkbox("サムネイル埋め込み (WAV以外)", value=True)
    
    st.markdown("---")
    st.markdown("##### 🔓 403エラー回避用 (推奨)")
    st.markdown("""
    <small>YouTubeがサーバーからの接続を拒否する場合、ブラウザのCookieが必要です。<br>
    PCでChrome拡張機能「<b>Get cookies.txt LOCALLY</b>」などを使い、YouTubeのCookieをtxt保存してここにアップロードしてください。</small>
    """, unsafe_allow_html=True)
    cookie_file = st.file_uploader("cookies.txt をアップロード", type=["txt"])

    submitted = st.form_submit_button("変換開始")

# ── 処理ロジック ──
if submitted and urls_text:
    urls = [u.strip() for u in urls_text.splitlines() if u.strip()]
    
    if not urls:
        st.warning("URLを入力してください。")
    else:
        st_status = st.status("準備中...", expanded=True)
        
        # Cookieの処理
        cookie_path = None
        if cookie_file is not None:
            cookie_path = "cookies.txt"
            with open(cookie_path, "wb") as f:
                f.write(cookie_file.getvalue())
            st_status.write("🍪 Cookieファイルを読み込みました")

        # オプション設定 (エラー回避設定を追加)
        q_val = quality.split()[0]
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'{DOWNLOAD_DIR}/%(title)s.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': format_type,
                'preferredquality': q_val,
            }],
            # 以下、エラー回避用オプション
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
            'ignoreerrors': True, # エラーでも止まらない
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36', # ブラウザのふりをする
        }

        # WAV以外ならメタデータ・サムネ追加
        if format_type != 'wav' and embed_thumb:
            ydl_opts['writethumbnail'] = True
            ydl_opts['postprocessors'].append({'key': 'EmbedThumbnail'})
            ydl_opts['postprocessors'].append({'key': 'FFmpegMetadata'})

        if cookie_path:
            ydl_opts['cookiefile'] = cookie_path

        # ダウンロード実行
        success_count = 0
        
        for url in urls:
            st_status.write(f"処理開始: {url}")
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    if info:
                        title = info.get('title', 'video')
                        st_status.write(f"✅ 完了: {title}")
                        success_count += 1
                    else:
                        st_status.error(f"❌ 取得失敗: {url} (動画情報が空です)")
            except Exception as e:
                st_status.error(f"❌ エラー ({url}): {e}")

        # Cookieファイルの削除（セキュリティのため）
        if cookie_path and os.path.exists(cookie_path):
            os.remove(cookie_path)

        st_status.update(label="処理終了", state="complete", expanded=False)

        # ── ZIP圧縮とダウンロードボタン ──
        if success_count > 0:
            shutil.make_archive("download_files", 'zip', DOWNLOAD_DIR)
            
            with open("download_files.zip", "rb") as fp:
                st.markdown("### ✨ ダウンロード準備完了")
                btn = st.download_button(
                    label="📥 ZIPファイルをダウンロード",
                    data=fp,
                    file_name="downloaded_audio.zip",
                    mime="application/zip"
                )
        elif success_count == 0:
             st.error("1つもダウンロードできませんでした。Cookieを使用してください。")
