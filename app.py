import streamlit as st
import yt_dlp
import os
import shutil
import time

# ページ設定
st.set_page_config(page_title="動画ダウンローダー", page_icon="🎵")

st.title("🎵 動画・音声ダウンローダー")
st.write("YouTubeやニコニコ動画のURLを入力して、形式を選んでダウンロードできます。")

# ── サイドバー設定 ──
st.sidebar.header("設定")
fmt = st.sidebar.selectbox("フォーマット", ["mp3", "m4a", "wav"], index=0)
quality_map = {"最高 (0)": "0", "高 (1)": "1", "標準 (5)": "5"}
quality_key = st.sidebar.selectbox("音質", list(quality_map.keys()), index=0)
quality = quality_map[quality_key]

embed_thumb = st.sidebar.checkbox("サムネイル埋め込み", value=True)
if fmt == "wav" and embed_thumb:
    st.sidebar.warning("※ WAV形式はサムネイル埋め込みに対応していない場合があります。")

# Cookieファイルのアップロード
st.sidebar.markdown("---")
st.sidebar.write("ログインが必要な動画用 (任意)")
cookie_file = st.sidebar.file_uploader("cookies.txt", type=["txt"])

# ── メインエリア ──
url_input = st.text_area("URLを入力（改行区切りで複数可）", height=100, placeholder="ここにURLを貼り付け...")

# 一時保存フォルダ
TEMP_DIR = "temp_downloads"
os.makedirs(TEMP_DIR, exist_ok=True)

def cleanup_files():
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)
        os.makedirs(TEMP_DIR, exist_ok=True)

if st.button("変換・ダウンロード開始", type="primary"):
    if not url_input.strip():
        st.error("URLを入力してください。")
    else:
        urls = [u.strip() for u in url_input.splitlines() if u.strip()]
        
        # プログレスバー
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        cleanup_files() # 前回のゴミを削除

        # Cookieの処理
        cookie_path = None
        if cookie_file is not None:
            cookie_path = os.path.join(TEMP_DIR, "cookies.txt")
            with open(cookie_path, "wb") as f:
                f.write(cookie_file.getbuffer())

        # ダウンロード設定
        ydl_opts = {
            'outtmpl': f'{TEMP_DIR}/%(title)s.%(ext)s',
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': fmt,
                'preferredquality': quality,
            }],
            'quiet': True,
        }

        if embed_thumb and fmt != 'wav':
            ydl_opts['writethumbnail'] = True
            ydl_opts['postprocessors'].append({'key': 'EmbedThumbnail'})
            ydl_opts['postprocessors'].append({'key': 'FFmpegMetadata'})
        
        if cookie_path:
            ydl_opts['cookiefile'] = cookie_path

        # 処理実行
        downloaded_files = []
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                for i, url in enumerate(urls):
                    status_text.text(f"処理中 ({i+1}/{len(urls)}): {url}")
                    info = ydl.extract_info(url, download=True)
                    title = info.get('title', 'audio')
                    filename = f"{title}.{fmt}"
                    # ファイル名に使えない文字対策などのため、ディレクトリ内を検索して特定する
                    for f in os.listdir(TEMP_DIR):
                        if f.endswith(f".{fmt}"):
                            full_path = os.path.join(TEMP_DIR, f)
                            if full_path not in downloaded_files:
                                downloaded_files.append(full_path)
                    
                    progress_bar.progress((i + 1) / len(urls))

            status_text.success("処理完了！以下のボタンからダウンロードしてください。")
            
            # ダウンロードボタンの表示
            for file_path in downloaded_files:
                file_name = os.path.basename(file_path)
                with open(file_path, "rb") as f:
                    st.download_button(
                        label=f"📥 {file_name} を保存",
                        data=f,
                        file_name=file_name,
                        mime=f"audio/{fmt}"
                    )

        except Exception as e:
            st.error(f"エラーが発生しました: {e}")
