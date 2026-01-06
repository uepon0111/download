import streamlit as st
import yt_dlp
import os
import tempfile
import time
import zipfile
import io

# ページ設定 (必ず最初に記述)
st.set_page_config(page_title="Advanced Video Downloader", layout="centered", page_icon="⬇️")

st.title("⬇️ Advanced Video Downloader")
st.caption("ZIP一括DL・プレビュー・解像度指定対応版")

# ── 内部関数: Cookieの自動生成 ──
def create_cookie_file(tmp_dir):
    if "general" in st.secrets and "YOUTUBE_COOKIES" in st.secrets["general"]:
        cookie_content = st.secrets["general"]["YOUTUBE_COOKIES"]
        cookie_path = os.path.join(tmp_dir, "cookies.txt")
        with open(cookie_path, "w", encoding="utf-8") as f:
            f.write(cookie_content)
        return cookie_path
    return None

# ── 内部関数: 単位変換 ──
def format_bytes(size):
    power = 2**10
    n = 0
    power_labels = {0 : '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size > power:
        size /= power
        n += 1
    return f"{size:.2f} {power_labels[n]}B"

# ── サイドバー設定 ──
with st.sidebar:
    st.header("⚙️ 詳細設定")
    
    # フォーマット選択
    format_type = st.selectbox(
        "保存形式",
        options=['mp4', 'mp3', 'm4a', 'wav'],
        index=0
    )
    
    # 動画用設定
    if format_type == 'mp4':
        st.subheader("📺 画質設定")
        res_options = {
            '最高画質 (Best)': 'best',
            '4K (2160p)': '2160',
            'フルHD (1080p)': '1080',
            'HD (720p)': '720',
            'SD (480p)': '480',
            '軽量 (360p)': '360'
        }
        selected_res = st.selectbox("解像度上限", list(res_options.keys()), index=0)
        res_val = res_options[selected_res]
        
    # 音声用設定
    else:
        st.subheader("🎵 音質設定")
        audio_quality_map = {
            '最高 (Best)': '0', 
            '高音質 (192kbps)': '192', 
            '標準 (128kbps)': '128',
            '軽量 (64kbps)': '64'
        }
        quality_label = st.selectbox("ビットレート/品質", list(audio_quality_map.keys()))
        quality_val = audio_quality_map[quality_label]
    
    st.divider()
    embed_thumb = st.checkbox("サムネイル埋め込み", value=True)
    add_metadata = st.checkbox("メタデータ付与", value=True)

# ── 進捗表示用のクラス ──
class ProgressHooks:
    def __init__(self, status_placeholder, progress_bar):
        self.status_placeholder = status_placeholder
        self.progress_bar = progress_bar

    def hook(self, d):
        if d['status'] == 'downloading':
            p = d.get('_percent_str', '0%').replace('%','')
            try:
                per = float(p)
            except:
                per = 0
            
            self.progress_bar.progress(min(per / 100, 1.0))
            
            # 詳細情報の表示
            speed = d.get('_speed_str', 'N/A')
            eta = d.get('_eta_str', 'N/A')
            size = d.get('_total_bytes_str') or d.get('_total_bytes_estimate_str') or 'Unknown'
            
            self.status_placeholder.write(
                f"📥 ダウンロード中... {d['_percent_str']} "
                f"(速度: {speed}, 残り: {eta}, サイズ: {size})"
            )
            
        elif d['status'] == 'finished':
            self.progress_bar.progress(1.0)
            self.status_placeholder.write("🔄 変換/結合処理中...")

# ── 処理ロジック ──

def get_video_info(urls):
    """URLリストから動画情報を取得する（ダウンロードはしない）"""
    info_list = []
    
    # クッキー用の一時ディレクトリ（メタデータ取得時も年齢制限などで必要な場合があるため）
    with tempfile.TemporaryDirectory() as tmp_dir:
        cookie_path = create_cookie_file(tmp_dir)
        
        ydl_opts = {
            'quiet': True,
            'extract_flat': False, # 完全な情報を取るためFalse（少し遅いが確実）
            'skip_download': True, # 重要：ダウンロードしない
        }
        if cookie_path:
            ydl_opts['cookiefile'] = cookie_path

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            for url in urls:
                try:
                    info = ydl.extract_info(url, download=False)
                    info_list.append({
                        'title': info.get('title', 'Unknown'),
                        'thumbnail': info.get('thumbnail'),
                        'duration': info.get('duration'),
                        'uploader': info.get('uploader'),
                        'url': url,
                        'id': info.get('id')
                    })
                except Exception as e:
                    st.error(f"情報取得エラー ({url}): {e}")
    return info_list

def process_download(info_list):
    """メタデータリストを元にダウンロードを実行"""
    
    downloaded_data = []
    zip_buffer = None
    
    # UI要素の準備
    main_progress = st.progress(0)
    main_status = st.empty()
    
    total_videos = len(info_list)

    with tempfile.TemporaryDirectory() as tmp_dir:
        cookie_path = create_cookie_file(tmp_dir)
        
        for idx, info in enumerate(info_list):
            url = info['url']
            title = info['title']
            
            main_status.markdown(f"### ⏳ 処理中 ({idx+1}/{total_videos}): **{title}**")
            
            # 個別動画の進捗表示用エリア
            single_status = st.empty()
            single_bar = st.progress(0)
            hooks = ProgressHooks(single_status, single_bar)

            # オプション構築
            ydl_opts = {
                'outtmpl': f'{tmp_dir}/%(title)s.%(ext)s',
                'quiet': True,
                'no_warnings': True,
                'progress_hooks': [hooks.hook],
            }

            # クッキー
            if cookie_path:
                ydl_opts['cookiefile'] = cookie_path

            # フォーマット・画質設定
            if format_type == 'mp4':
                if res_val == 'best':
                    # 最高画質
                    ydl_opts.update({
                        'format': 'bestvideo+bestaudio/best',
                        'merge_output_format': 'mp4',
                    })
                else:
                    # 指定解像度以下で最高のもの
                    ydl_opts.update({
                        'format': f'bestvideo[height<={res_val}]+bestaudio/best[height<={res_val}]/best',
                        'merge_output_format': 'mp4',
                    })
            else:
                # 音声設定
                postprocessors = [{'key': 'FFmpegExtractAudio','preferredcodec': format_type}]
                if format_type != 'wav': # WAVはビットレート指定なし
                     if quality_val != '0': # 0以外なら指定
                        postprocessors[0]['preferredquality'] = quality_val
                
                ydl_opts.update({
                    'format': 'bestaudio/best',
                    'postprocessors': postprocessors,
                })

            # 共通ポストプロセス（サムネ・メタデータ）
            pps = ydl_opts.get('postprocessors', [])
            if add_metadata:
                pps.append({'key': 'FFmpegMetadata'})
            
            if embed_thumb and format_type != 'wav':
                ydl_opts['writethumbnail'] = True
                pps.append({'key': 'EmbedThumbnail'})
            
            ydl_opts['postprocessors'] = pps

            # ダウンロード実行
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                
                # 完了表示の更新
                single_bar.progress(1.0)
                single_status.success(f"✅ 完了: {title}")
                
            except Exception as e:
                st.error(f"❌ ダウンロードエラー ({title}): {e}")
                continue
            
            main_progress.progress((idx + 1) / total_videos)

        # ── ファイル回収とZIP作成 ──
        target_ext = format_type
        # 対応する拡張子のファイルをすべて取得
        files = [f for f in os.listdir(tmp_dir) if f.endswith(f".{target_ext}")]

        if not files:
            main_status.error("ファイルが生成されませんでした。")
            return None, None

        # 個別ファイルの読み込み
        for filename in files:
            file_path = os.path.join(tmp_dir, filename)
            with open(file_path, "rb") as f:
                file_bytes = f.read()
                downloaded_data.append({
                    "filename": filename,
                    "data": file_bytes,
                    "mime": f"video/mp4" if format_type == 'mp4' else f"audio/{format_type}"
                })

        # ZIPファイルの作成（メモリ上）
        if len(files) > 0:
            zip_io = io.BytesIO()
            with zipfile.ZipFile(zip_io, 'w', zipfile.ZIP_DEFLATED) as zf:
                for filename in files:
                    file_path = os.path.join(tmp_dir, filename)
                    zf.write(file_path, arcname=filename)
            zip_io.seek(0)
            zip_buffer = zip_io.getvalue()
            
        main_status.success("🎉 全ての処理が完了しました！")
        return downloaded_data, zip_buffer


# ── メインUI構築 ──

# セッション状態の管理
if 'stage' not in st.session_state:
    st.session_state.stage = 'input' # input -> preview -> downloaded
if 'video_infos' not in st.session_state:
    st.session_state.video_infos = []

# --- ステップ1: URL入力 ---
st.subheader("1️⃣ URL入力")
url_input = st.text_area(
    "動画URL（改行で複数入力可）", 
    placeholder="https://www.youtube.com/watch?v=...\nhttps://youtu.be/...",
    height=100
)

# 情報を取得ボタン
if st.button("動画情報を確認する", type="primary", use_container_width=True):
    urls = [u.strip() for u in url_input.splitlines() if u.strip()]
    if urls:
        with st.spinner("動画情報を取得中..."):
            infos = get_video_info(urls)
            if infos:
                st.session_state.video_infos = infos
                st.session_state.stage = 'preview'
                st.session_state.download_results = None # 結果リセット
                st.rerun()
    else:
        st.warning("URLを入力してください")

# --- ステップ2: プレビュー & ダウンロード開始 ---
if st.session_state.stage == 'preview' and st.session_state.video_infos:
    st.markdown("---")
    st.subheader(f"2️⃣ プレビュー ({len(st.session_state.video_infos)}件)")
    
    # プレビュー表示
    for info in st.session_state.video_infos:
        with st.container():
            col1, col2 = st.columns([1, 3])
            with col1:
                if info['thumbnail']:
                    st.image(info['thumbnail'], use_container_width=True)
            with col2:
                st.markdown(f"**{info['title']}**")
                duration_min = info['duration'] // 60 if info['duration'] else 0
                duration_sec = info['duration'] % 60 if info['duration'] else 0
                st.caption(f"長さ: {duration_min}分{duration_sec}秒 | 投稿者: {info['uploader']}")
    
    st.markdown("---")
    col_l, col_r = st.columns(2)
    with col_l:
        if st.button("🔙 入力に戻る"):
            st.session_state.stage = 'input'
            st.rerun()
    with col_r:
        if st.button("🚀 ダウンロード開始", type="primary", use_container_width=True):
            st.session_state.stage = 'processing'
            st.rerun()

# --- ステップ3: 処理 & 結果 ---
if st.session_state.stage == 'processing':
    st.markdown("---")
    st.subheader("3️⃣ ダウンロード処理")
    
    results, zip_data = process_download(st.session_state.video_infos)
    
    if results:
        st.session_state.download_results = results
        st.session_state.zip_data = zip_data
        st.session_state.stage = 'finished'
        st.rerun()
    else:
        st.error("処理に失敗しました。")
        if st.button("戻る"):
            st.session_state.stage = 'input'
            st.rerun()

# --- ステップ4: 結果表示 ---
if st.session_state.stage == 'finished':
    st.markdown("---")
    st.subheader("📂 ダウンロード")
    
    results = st.session_state.download_results
    zip_data = st.session_state.zip_data
    
    # ZIP一括ダウンロードボタン
    if zip_data:
        st.download_button(
            label="📦 まとめてZIPでダウンロード",
            data=zip_data,
            file_name="videos_archive.zip",
            mime="application/zip",
            use_container_width=True,
            type="primary"
        )
        st.caption("※ファイル名が文字化けする場合は、解凍ソフトの設定を確認してください。")

    st.markdown("### 個別ダウンロード")
    for item in results:
        st.download_button(
            label=f"⬇️ {item['filename']}",
            data=item['data'],
            file_name=item['filename'],
            mime=item['mime'],
            key=f"btn_{item['filename']}",
            use_container_width=True
        )
        
    if st.button("最初に戻る"):
        st.session_state.stage = 'input'
        st.session_state.video_infos = []
        st.session_state.download_results = None
        st.rerun()
