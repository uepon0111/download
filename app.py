import streamlit as st
import yt_dlp
import os
import shutil
from zipfile import ZipFile

# ページ設定
st.set_page_config(page_title="YouTube Downloader", layout="centered")

st.title("YouTube/Video Downloader")
st.markdown("URLを入力して、形式を選択してください。")
st.info("⚠ エラーが出る場合は、Chrome拡張機能などで取得した `cookies.txt` をアップロードしてください。")

# ── 保存先ディレクトリの準備 ──
DOWNLOAD_DIR = "downloads"
# 前回の残りを消す（安全のためtry-except）
if os.path.exists(DOWNLOAD_DIR):
    try:
        shutil.rmtree(DOWNLOAD_DIR)
    except:
        pass
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
    
    # Cookieアップロード
    cookie_file = st.file_uploader("Cookies.txt (エラー回避用)", type=["txt"], help="HTTP 403エラーが出る場合、ブラウザからエクスポートしたcookies.txtをここにアップロードしてください")

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

        # オプション設定
        q_val = quality.split()[0]
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'{DOWNLOAD_DIR}/%(title)s.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': format_type,
                'preferredquality': q_val,
            }],
            'quiet': True,
            'no_warnings': True,
            # ⬇⬇⬇ ここが403エラー対策の追加設定 ⬇⬇⬇
            'nocheckcertificate': True,
            'ignoreerrors': True,  # エラーでも止まらない
            'extractor_args': {
                'youtube': {
                    # WebブラウザではなくAndroidアプリのふりをする（回避率向上）
                    'player_client': ['android', 'ios'] 
                }
            }
            # ⬆⬆⬆ ここまで ⬆⬆⬆
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
                        
                        # サムネイル表示
                        thumb = info.get('thumbnail')
                        if thumb:
                            st.image(thumb, width=150)
                        success_count += 1
                    else:
                        st_status.error(f"失敗: 動画情報を取得できませんでした ({url})")
            except Exception as e:
                # エラーメッセージを短く表示
                err_msg = str(e)
                if "403" in err_msg:
                    st_status.error(f"⛔ 403エラー (拒否) されました: {url}\n対策: Cookies.txt をアップロードしてください。")
                else:
                    st_status.error(f"エラー ({url}): {e}")

        st_status.update(label="処理終了", state="complete", expanded=False)

        # ── ZIP圧縮とダウンロードボタン ──
        if success_count > 0:
            shutil.make_archive("download_files", 'zip', DOWNLOAD_DIR)
            
            with open("download_files.zip", "rb") as fp:
                btn = st.download_button(
                    label="📥 ZIPファイルをダウンロード",
                    data=fp,
                    file_name="downloaded_audio.zip",
                    mime="application/zip"
                )
        else:
            st.error("1つもダウンロードできませんでした。Cookieを使用するか、しばらく時間を空けて試してください。")
