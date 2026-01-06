import streamlit as st
import yt_dlp
import os
import tempfile

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
        progress_bar = st.progress(0)
        status_text = st.empty()

        # 一時ディレクトリを作成して処理
        with tempfile.TemporaryDirectory() as tmpdir:
            
            # ── Cookie 自動読み込み処理 ──
            cookie_path = None
            try:
                # Streamlit Secrets から cookie_data を取得
                if "cookie_data" in st.secrets["general"]:
                    cookie_content = st.secrets["general"]["cookie_data"]
                    cookie_path = os.path.join(tmpdir, "cookies.txt")
                    
                    # Cookieファイルを一時作成
                    with open(cookie_path, "w", encoding="utf-8") as f:
                        f.write(cookie_content)
                    
                    # ユーザーには見えないようにコンソールにだけログ出力
                    print("✅ Cookies loaded from Secrets.")
                else:
                    print("⚠️ No cookies found in Secrets.")
            except Exception as e:
                # エラーでも停止せず、Cookieなしで続行を試みる
                print(f"⚠️ Cookie loading skipped: {e}")
            # ──────────────────────────

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
                # ブラウザ偽装（念のため残す）
                'nocheckcertificate': True,
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            }

            # WAV以外かつチェックありならサムネイル埋め込み
            if embed_thumbnail and format_option != 'wav':
                ydl_opts['writethumbnail'] = True
                ydl_opts['postprocessors'].append({'key': 'EmbedThumbnail'})
                ydl_opts['postprocessors'].append({'key': 'FFmpegMetadata'})

            # 自動生成したCookieパスを渡す
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
                        
                        # 生成されたファイルを探す
                        for file_name in os.listdir(tmpdir):
                            if file_name.endswith(f".{format_option}"):
                                full_path = os.path.join(tmpdir, file_name)
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
