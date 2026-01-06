import streamlit as st
import yt_dlp
import os
import tempfile

# ページ設定
st.set_page_config(page_title="Easy Video Downloader", layout="centered", page_icon="⬇️")

st.title("⬇️ Simple Video Downloader")
st.markdown("URLを入れるだけでダウンロードできます。（ログイン設定済み）")

# ── 内部関数: Cookieの自動生成 ──
def create_cookie_file(tmp_dir):
    """
    Secretsに保存されたCookie情報から一時ファイルを作成する。
    Secretsがない場合はNoneを返す。
    """
    # secrets.toml に 'YOUTUBE_COOKIES' が定義されているか確認
    if "general" in st.secrets and "YOUTUBE_COOKIES" in st.secrets["general"]:
        cookie_content = st.secrets["general"]["YOUTUBE_COOKIES"]
        cookie_path = os.path.join(tmp_dir, "cookies.txt")
        
        # 取得した文字列をファイルに書き出す
        with open(cookie_path, "w", encoding="utf-8") as f:
            f.write(cookie_content)
        return cookie_path
    return None

# ── メインエリア ──

url_input = st.text_area(
    "URLを入力",
    height=100,
    placeholder="https://www.youtube.com/watch?v=..."
)

# 設定（サイドバーに隠す）
with st.sidebar:
    st.header("設定")
    format_type = st.selectbox("保存形式", ['mp3', 'm4a', 'wav'])

# ── ダウンロード処理 ──
def process_download():
    urls = [u.strip() for u in url_input.splitlines() if u.strip()]
    if not urls:
        st.error("URLを入力してください")
        return

    # 一時フォルダ作成
    with tempfile.TemporaryDirectory() as tmp_dir:
        
        # 【重要】ユーザー操作不要でCookieファイルを生成
        cookie_path = create_cookie_file(tmp_dir)
        
        status_text = st.empty()
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'{tmp_dir}/%(title)s.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': format_type,
            }],
            'quiet': True,
            # ブラウザの挙動を模倣（ブロック回避用）
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        }

        # Cookieが生成できていればオプションに追加
        if cookie_path:
            ydl_opts['cookiefile'] = cookie_path
            st.toast("🍪 自動ログイン情報を適用しました")

        try:
            for url in urls:
                status_text.text(f"処理中: {url}")
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
            
            # ファイル一覧取得
            files = [f for f in os.listdir(tmp_dir) if f.endswith(f".{format_type}")]
            
            if not files:
                st.error("エラー: ダウンロードできませんでした。")
                return

            st.success("完了しました")
            for filename in files:
                file_path = os.path.join(tmp_dir, filename)
                with open(file_path, "rb") as f:
                    st.download_button(
                        label=f"⬇️ {filename}",
                        data=f,
                        file_name=filename,
                        mime=f"audio/{format_type}"
                    )

        except Exception as e:
            st.error(f"エラーが発生しました: {e}")

if st.button("ダウンロード開始", type="primary", use_container_width=True):
    with st.spinner("処理中..."):
        process_download()
