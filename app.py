import streamlit as st
import yt_dlp
import os
import tempfile
import time

# ページ設定
st.set_page_config(page_title="Video Downloader", layout="centered", page_icon="⬇️")

st.title("⬇️ Multi Video Downloader")
st.caption("MP4動画対応・複数ファイル対応版")

# ── 内部関数: Cookieの自動生成 ──
def create_cookie_file(tmp_dir):
    if "general" in st.secrets and "YOUTUBE_COOKIES" in st.secrets["general"]:
        cookie_content = st.secrets["general"]["YOUTUBE_COOKIES"]
        cookie_path = os.path.join(tmp_dir, "cookies.txt")
        with open(cookie_path, "w", encoding="utf-8") as f:
            f.write(cookie_content)
        return cookie_path
    return None

# ── サイドバー設定 ──
with st.sidebar:
    st.header("⚙️ 設定")
    
    # MP4を追加
    format_type = st.selectbox(
        "保存形式",
        options=['mp3', 'm4a', 'wav', 'mp4'], # mp4を追加
        index=0
    )
    
    # 音質/画質設定
    if format_type == 'mp4':
        st.info("MP4選択時は、最高画質(1080p等)と音声を結合してダウンロードします。")
        quality_val = '0' # 動画の場合は使わないが変数確保のため
    else:
        quality_map = {'最高 (0)': '0', '高 (1)': '1', '標準 (5)': '5'}
        quality_label = st.selectbox("音質設定", list(quality_map.keys()))
        quality_val = quality_map[quality_label]
    
    embed_thumb = st.checkbox("カバー画像/サムネイル埋め込み", value=True)

# ── 処理ロジック ──
def process_download(urls):
    """ダウンロード処理を実行し、結果をSession Stateに保存する"""
    
    # 結果保存用のリストを初期化
    downloaded_data = []

    # 一時フォルダ作成
    with tempfile.TemporaryDirectory() as tmp_dir:
        cookie_path = create_cookie_file(tmp_dir)
        
        # 進捗表示
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # 基本オプション
        ydl_opts = {
            'outtmpl': f'{tmp_dir}/%(title)s.%(ext)s',
            'quiet': True,
            'no_warnings': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        }

        # フォーマット別設定
        if format_type == 'mp4':
            # 動画(最高画質)+音声(最高音質) をダウンロードしてマージ
            ydl_opts.update({
                'format': 'bestvideo+bestaudio/best',
                'merge_output_format': 'mp4',
            })
        else:
            # 音声のみ抽出
            ydl_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': format_type,
                    'preferredquality': quality_val,
                }],
            })

        # Cookie設定
        if cookie_path:
            ydl_opts['cookiefile'] = cookie_path

        # サムネイル設定（WAV以外）
        if embed_thumb and format_type != 'wav':
            ydl_opts['writethumbnail'] = True
            # 音声ファイルへの埋め込み
            if format_type != 'mp4':
                if 'postprocessors' not in ydl_opts: ydl_opts['postprocessors'] = []
                ydl_opts['postprocessors'].append({'key': 'EmbedThumbnail'})
                ydl_opts['postprocessors'].append({'key': 'FFmpegMetadata'})
            # MP4への埋め込み
            else:
                 if 'postprocessors' not in ydl_opts: ydl_opts['postprocessors'] = []
                 ydl_opts['postprocessors'].append({'key': 'EmbedThumbnail'})
                 ydl_opts['postprocessors'].append({'key': 'FFmpegMetadata'})


        total_files = len(urls)
        
        for i, url in enumerate(urls):
            status_text.text(f"⏳ 処理中 ({i+1}/{total_files}): {url}")
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                progress_bar.progress((i + 1) / total_files)
            except Exception as e:
                st.error(f"❌ エラー ({url}): {e}")

        # 完了後のファイル収集
        # 指定した拡張子のファイルを探す
        target_ext = format_type
        files = [f for f in os.listdir(tmp_dir) if f.endswith(f".{target_ext}")]

        if not files:
            status_text.error("ファイルが生成されませんでした。")
            return

        # ★重要: ファイルをメモリ(bytes)に読み込んで保存する
        # これをしないと一時フォルダ削除と共にデータが消える
        for filename in files:
            file_path = os.path.join(tmp_dir, filename)
            with open(file_path, "rb") as f:
                file_bytes = f.read()
                downloaded_data.append({
                    "filename": filename,
                    "data": file_bytes,
                    "mime": f"video/mp4" if format_type == 'mp4' else f"audio/{format_type}"
                })

        # Session Stateに結果を保存
        st.session_state['download_results'] = downloaded_data
        status_text.success("処理完了！下のボタンからダウンロードしてください。")

# ── メインエリア ──

url_input = st.text_area(
    "URLを入力 (複数可)",
    height=100,
    placeholder="https://www.youtube.com/watch?v=..."
)

# ダウンロード開始ボタン
if st.button("変換・ダウンロード開始", type="primary", use_container_width=True):
    urls = [u.strip() for u in url_input.splitlines() if u.strip()]
    if urls:
        # 前回の結果をクリア
        if 'download_results' in st.session_state:
            del st.session_state['download_results']
            
        with st.spinner("サーバーで変換処理を行っています..."):
            process_download(urls)
    else:
        st.warning("URLを入力してください。")

# ── 結果表示エリア ──
# Session Stateにデータがあればボタンを表示（リロードされても消えないようにする）
if 'download_results' in st.session_state:
    st.markdown("---")
    st.subheader("📁 ダウンロード準備完了")
    
    results = st.session_state['download_results']
    
    for item in results:
        # ★重要: key引数をファイル名などでユニークにする
        # keyが無いと複数のボタンが正しく動作しません
        st.download_button(
            label=f"⬇️ {item['filename']}",
            data=item['data'],
            file_name=item['filename'],
            mime=item['mime'],
            key=f"btn_{item['filename']}", 
            use_container_width=True
        )
    
    # クリアボタン（画面をリセットしたい場合）
    if st.button("リセット", key="reset_btn"):
        del st.session_state['download_results']
        st.rerun()
