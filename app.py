import streamlit as st
import yt_dlp
import os
import tempfile
import shutil

# ページ設定
st.set_page_config(page_title="動画ダウンローダー", layout="centered")
st.title("🎥 動画/音声 ダウンローダー")
st.write("YouTube や ニコニコ動画の URL を入力してダウンロードできます。")

# ── サイドバー設定 ──
st.sidebar.header("設定")

# フォーマット選択
format_option = st.sidebar.selectbox(
    "フォーマット",
    options=['mp3', 'm4a', 'wav'],
    index=0
)

# 音質選択
quality_option = st.sidebar.selectbox(
    "音質 (0が最高)",
    options=['0', '1', '5'],
    index=0
)

# サムネイル埋め込み
embed_thumbnail = st.sidebar.checkbox(
    "サムネイルを埋め込む",
    value=True,
    help="WAV形式では機能しない場合があります"
)

# Cookies アップロード
st.sidebar.markdown("---")
uploaded_cookie = st.sidebar.file_uploader(
    "Cookies.txt (ニコニコ等用)", 
    type=['txt'],
    help="ログインが必要な動画の場合に使用します"
)

# ── メインエリア ──
url_input = st.text_area(
    "URL入力欄 (改行区切りで複数可)",
    height=150,
    placeholder="https://www.youtube.com/watch?v=..."
)

# 処理実行ボタン
if st.button("変換・ダウンロード準備を開始", type="primary"):
    urls = [u.strip() for u in url_input.splitlines() if u.strip()]

    if not urls:
        st.error("URL が入力されていません。")
    else:
        # 進行状況バー
        progress_bar = st.progress(0)
        status_text = st.empty()

        # 一時ディレクトリを作成して処理
        with tempfile.TemporaryDirectory() as tmpdir:
            
            # Cookieファイルの一時保存処理
            cookie_path = None
            if uploaded_cookie is not None:
                cookie_path = os.path.join(tmpdir, "cookies.txt")
                with open(cookie_path, "wb") as f:
                    f.write(uploaded_cookie.getvalue())

            # yt-dlp オプション設定
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': f'{tmpdir}/%(title)s.%(ext)s',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': format_option,
                    'preferredquality': quality_option,
                }],
                'quiet': True,
                'no_warnings': True,
            }

            # WAV以外かつチェックありならサムネイル埋め込み
            if embed_thumbnail and format_option != 'wav':
                ydl_opts['writethumbnail'] = True
                ydl_opts['postprocessors'].append({'key': 'EmbedThumbnail'})
                ydl_opts['postprocessors'].append({'key': 'FFmpegMetadata'})

            if cookie_path:
                ydl_opts['cookiefile'] = cookie_path

            # ダウンロード処理ループ
            processed_files = []
            
            for i, url in enumerate(urls):
                status_text.text(f"処理中 ({i+1}/{len(urls)}): {url}")
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=True)
                        title = info.get('title', 'video')
                        # 生成されたファイルを探す（拡張子が確定しない場合があるため検索）
                        for file_name in os.listdir(tmpdir):
                            if file_name.endswith(f".{format_option}"):
                                full_path = os.path.join(tmpdir, file_name)
                                # リストに追加済みのファイルでなければ追加
                                if full_path not in [x['path'] for x in processed_files]:
                                    processed_files.append({
                                        'title': title,
                                        'path': full_path,
                                        'name': file_name
                                    })
                except Exception as e:
                    st.error(f"エラーが発生しました ({url}): {e}")
                
                progress_bar.progress((i + 1) / len(urls))

            status_text.text("処理完了！以下のボタンからダウンロードしてください。")
            progress_bar.progress(100)

            # ダウンロードボタンの表示
            st.success(f"{len(processed_files)} 個のファイルを生成しました。")
            
            for p_file in processed_files:
                try:
                    with open(p_file['path'], "rb") as f:
                        file_data = f.read()
                    
                    st.download_button(
                        label=f"ダウンロード: {p_file['name']}",
                        data=file_data,
                        file_name=p_file['name'],
                        mime=f"audio/{format_option}"
                    )
                except Exception as e:
                    st.error(f"ファイル読み込みエラー: {e}")

# ── 注意書き ──
st.markdown("---")
st.caption("※ 生成されたファイルは一時保存され、再読み込みすると消去されます。")
st.caption("※ 著作権法および各サイトの利用規約を遵守してご利用ください。")
