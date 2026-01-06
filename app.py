import streamlit as st
import yt_dlp
import os
import tempfile
import shutil
import time

# ページ設定
st.set_page_config(page_title="Video Downloader", layout="centered", page_icon="⬇️")

st.title("⬇️ YouTube/Web Video Downloader")
st.caption("サーバー側で処理を行うため、PCへのインストールは不要です。")
st.markdown("---")

# ── サイドバー設定 ──
with st.sidebar:
    st.header("⚙️ 設定")
    
    # フォーマット選択
    format_type = st.selectbox(
        "保存形式",
        options=['mp3', 'm4a', 'wav'],
        index=0
    )
    
    # 音質選択
    quality_map = {'最高 (0)': '0', '高 (1)': '1', '標準 (5)': '5'}
    quality_label = st.selectbox("音質設定", list(quality_map.keys()))
    quality_val = quality_map[quality_label]
    
    # サムネイル埋め込み
    embed_thumb = st.checkbox("カバー画像埋め込み", value=True)
    if format_type == 'wav' and embed_thumb:
        st.warning("※WAVは画像埋め込み非対応のため無視されます。")

    st.markdown("---")
    st.markdown("### 🍪 上級者向け設定")
    st.info("年齢制限動画やプレミアム動画、またはサーバー規制回避のためにCookieが必要です。")
    uploaded_cookie = st.file_uploader(
        "cookies.txt (Netscape形式)", 
        type=['txt'], 
        key="cookie_uploader"
    )

# ── メインエリア ──

url_input = st.text_area(
    "URLを入力 (複数ある場合は改行)",
    height=150,
    placeholder="https://www.youtube.com/watch?v=..."
)

# 処理状況を表示するエリア
status_container = st.container()

# ── 内部関数 ──

def get_cookie_path(tmp_dir, uploaded_file):
    """アップロードされたCookieを一時ファイルパスに変換"""
    if uploaded_file is None:
        return None
    cookie_path = os.path.join(tmp_dir, "cookies.txt")
    with open(cookie_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return cookie_path

def process_download():
    urls = [u.strip() for u in url_input.splitlines() if u.strip()]
    if not urls:
        st.error("URLが入力されていません。")
        return

    # 一時ディレクトリを作成（処理が終われば自動削除）
    with tempfile.TemporaryDirectory() as tmp_dir:
        
        # Cookieの処理
        cookie_path = get_cookie_path(tmp_dir, uploaded_cookie)

        # プログレスバー
        progress_bar = status_container.progress(0)
        status_text = status_container.empty()
        
        total_files = len(urls)
        success_files = []

        # yt-dlp オプション
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'{tmp_dir}/%(title)s.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': format_type,
                'preferredquality': quality_val,
            }],
            'quiet': True,
            'no_warnings': True,
            # クラウド環境でのエラー回避用設定（User-Agent偽装など）
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        }

        # Cookieがある場合に追加
        if cookie_path:
            ydl_opts['cookiefile'] = cookie_path

        # 画像埋め込み設定
        if embed_thumb and format_type != 'wav':
            ydl_opts['writethumbnail'] = True
            ydl_opts['postprocessors'].append({'key': 'EmbedThumbnail'})
            ydl_opts['postprocessors'].append({'key': 'FFmpegMetadata'})

        # ダウンロード実行ループ
        for i, url in enumerate(urls):
            status_text.text(f"⏳ 処理中 ({i+1}/{total_files}): {url}")
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                # 進捗更新
                progress_bar.progress((i + 1) / total_files)
            except Exception as e:
                st.error(f"❌ エラー ({url}): {e}")

        status_text.text("✅ 処理完了！ファイルを準備しています...")
        
        # 生成されたファイルをリストアップ
        files = [f for f in os.listdir(tmp_dir) if f.endswith(f".{format_type}")]

        if not files:
            st.warning("ファイルが生成されませんでした。URLやCookieを確認してください。")
            return

        st.success(f"完了しました！以下のボタンから保存してください。")

        # ダウンロードボタン生成
        for filename in files:
            file_path = os.path.join(tmp_dir, filename)
            with open(file_path, "rb") as f:
                btn = st.download_button(
                    label=f"⬇️ {filename}",
                    data=f,
                    file_name=filename,
                    mime=f"audio/{format_type}"
                )
                if btn:
                    st.toast("保存しました！")

# ── 実行ボタン ──
if st.button("ダウンロード開始", type="primary", use_container_width=True):
    with st.spinner("サーバーで変換処理を行っています..."):
        process_download()

st.markdown("---")
st.caption("※本ツールは技術検証用です。著作権法および各サイトの利用規約を遵守してご利用ください。")
