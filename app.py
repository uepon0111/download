import streamlit as st
import yt_dlp
import os
import tempfile
import time
import zipfile
import io

# --- ページ設定 ---
st.set_page_config(page_title="Video Downloader Pro", layout="centered", page_icon="📥")

# --- Font Awesome & カスタムCSSの注入 ---
st.markdown("""
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        /* 全体のフォント設定 */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
        html, body, [class*="css"] {
            font-family: 'Inter', sans-serif;
        }

        /* メインタイトル */
        .main-title {
            font-size: 2.5rem;
            font-weight: 800;
            background: linear-gradient(45deg, #0072ff, #00c6ff);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
        }

        /* サブタイトル/キャプション */
        .sub-text {
            color: #888;
            font-size: 1rem;
            margin-bottom: 2rem;
        }

        /* カードデザイン */
        .video-card {
            background: #1e1e1e;
            border-radius: 12px;
            padding: 15px;
            border: 1px solid #333;
            margin-bottom: 15px;
            transition: transform 0.2s ease;
        }
        .video-card:hover {
            border-color: #0072ff;
            transform: translateY(-2px);
        }

        /* サイドバーの装飾 */
        .css-1639199 { 
            background-color: #0e1117;
        }

        /* アイコンのスタイル */
        .icon-spacing {
            margin-right: 10px;
            color: #0072ff;
        }
    </style>
""", unsafe_allow_html=True)

# --- ヘッダー部分 ---
st.markdown('<div class="main-title"><i class="fa-solid fa-cloud-arrow-down icon-spacing"></i>Video Downloader Pro</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-text">ZIP一括ダウンロード・高画質プレビュー・メタデータ自動付与</div>', unsafe_allow_html=True)

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
    st.markdown('### <i class="fa-solid fa-sliders icon-spacing"></i> 詳細設定', unsafe_allow_html=True)
    
    # フォーマット選択
    format_type = st.selectbox(
        "保存形式",
        options=['mp4', 'mp3', 'm4a', 'wav'],
        index=0
    )
    
    # 動画用設定
    if format_type == 'mp4':
        st.markdown('---')
        st.markdown('**<i class="fa-solid fa-display icon-spacing"></i> 画質設定**', unsafe_allow_html=True)
        res_options = {
            '最高画質 (Best)': 'best',
            '4K (2160p)': '2160',
            'フルHD (1080p)': '1080',
            'HD (720p)': '720',
            'SD (480p)': '480'
        }
        selected_res = st.selectbox("解像度上限", list(res_options.keys()), index=0)
        res_val = res_options[selected_res]
        
    # 音声用設定
    else:
        st.markdown('---')
        st.markdown('**<i class="fa-solid fa-headphones icon-spacing"></i> 音質設定**', unsafe_allow_html=True)
        audio_quality_map = {
            '最高 (Best)': '0', 
            '高音質 (192kbps)': '192', 
            '標準 (128kbps)': '128'
        }
        quality_label = st.selectbox("ビットレート", list(audio_quality_map.keys()))
        quality_val = audio_quality_map[quality_label]
    
    st.markdown('---')
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
            speed = d.get('_speed_str', 'N/A')
            self.status_placeholder.markdown(f'<i class="fa-solid fa-spinner fa-spin"></i> ダウンロード中... {d["_percent_str"]} (速度: {speed})', unsafe_allow_html=True)
            
        elif d['status'] == 'finished':
            self.progress_bar.progress(1.0)
            self.status_placeholder.markdown('<i class="fa-solid fa-arrows-rotate fa-spin"></i> 変換処理中...', unsafe_allow_html=True)

# ── 処理ロジック (関数は元のロジックを維持) ──
def get_video_info(urls):
    info_list = []
    with tempfile.TemporaryDirectory() as tmp_dir:
        cookie_path = create_cookie_file(tmp_dir)
        ydl_opts = {'quiet': True, 'extract_flat': False, 'skip_download': True}
        if cookie_path: ydl_opts['cookiefile'] = cookie_path
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
                    })
                except Exception as e:
                    st.error(f"Error: {e}")
    return info_list

def process_download(info_list):
    downloaded_data = []
    zip_buffer = None
    main_progress = st.progress(0)
    main_status = st.empty()
    total_videos = len(info_list)

    with tempfile.TemporaryDirectory() as tmp_dir:
        cookie_path = create_cookie_file(tmp_dir)
        for idx, info in enumerate(info_list):
            url = info['url']
            title = info['title']
            main_status.markdown(f'<i class="fa-solid fa-list-check icon-spacing"></i> 処理中 ({idx+1}/{total_videos}): **{title}**', unsafe_allow_html=True)
            
            single_status = st.empty()
            single_bar = st.progress(0)
            hooks = ProgressHooks(single_status, single_bar)

            ydl_opts = {
                'outtmpl': f'{tmp_dir}/%(title)s.%(ext)s',
                'quiet': True,
                'progress_hooks': [hooks.hook],
            }
            if cookie_path: ydl_opts['cookiefile'] = cookie_path

            if format_type == 'mp4':
                ydl_opts.update({'format': f'bestvideo[height<={res_val}]+bestaudio/best', 'merge_output_format': 'mp4'})
            else:
                postprocessors = [{'key': 'FFmpegExtractAudio','preferredcodec': format_type}]
                if format_type != 'wav' and quality_val != '0':
                    postprocessors[0]['preferredquality'] = quality_val
                ydl_opts.update({'format': 'bestaudio/best', 'postprocessors': postprocessors})

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                single_status.markdown('<i class="fa-solid fa-circle-check" style="color:#00ff88"></i> 完了', unsafe_allow_html=True)
            except Exception:
                continue
            main_progress.progress((idx + 1) / total_videos)

        files = [f for f in os.listdir(tmp_dir) if f.endswith(f".{format_type}")]
        for filename in files:
            with open(os.path.join(tmp_dir, filename), "rb") as f:
                downloaded_data.append({"filename": filename, "data": f.read(), "mime": f"video/mp4" if format_type == 'mp4' else f"audio/{format_type}"})

        if len(files) > 0:
            zip_io = io.BytesIO()
            with zipfile.ZipFile(zip_io, 'w', zipfile.ZIP_DEFLATED) as zf:
                for filename in files:
                    zf.write(os.path.join(tmp_dir, filename), arcname=filename)
            zip_buffer = zip_io.getvalue()
            
        main_status.markdown('<i class="fa-solid fa-face-smile icon-spacing"></i> すべての処理が完了しました！', unsafe_allow_html=True)
        return downloaded_data, zip_buffer

# --- メインUI ---
if 'stage' not in st.session_state:
    st.session_state.stage = 'input'

# ステップ1: URL入力
if st.session_state.stage == 'input':
    st.markdown('### <i class="fa-solid fa-link icon-spacing"></i> 1. URLを入力', unsafe_allow_html=True)
    url_input = st.text_area(
        label="YouTube動画のURL（1行に1つずつ入力してください）",
        placeholder="https://www.youtube.com/watch?v=...\nhttps://youtu.be/...",
        height=150,
        label_visibility="collapsed"
    )

    if st.button("動画情報を解析する", type="primary", use_container_width=True):
        urls = [u.strip() for u in url_input.splitlines() if u.strip()]
        if urls:
            with st.spinner("情報を取得しています..."):
                infos = get_video_info(urls)
                if infos:
                    st.session_state.video_infos = infos
                    st.session_state.stage = 'preview'
                    st.rerun()
        else:
            st.warning("URLを入力してください")

# ステップ2: プレビュー
if st.session_state.stage == 'preview':
    st.markdown('### <i class="fa-solid fa-magnifying-glass icon-spacing"></i> 2. 内容を確認', unsafe_allow_html=True)
    
    for info in st.session_state.video_infos:
        # カードデザインの適用
        st.markdown(f"""
            <div class="video-card">
                <div style="display: flex; gap: 20px; align-items: center;">
                    <img src="{info['thumbnail']}" style="width: 160px; border-radius: 8px;">
                    <div>
                        <div style="font-weight: 600; font-size: 1.1rem; margin-bottom: 5px;">{info['title']}</div>
                        <div style="color: #aaa; font-size: 0.9rem;">
                            <i class="fa-solid fa-user"></i> {info['uploader']}
                        </div>
                    </div>
                </div>
            </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("修正する", use_container_width=True):
            st.session_state.stage = 'input'
            st.rerun()
    with c2:
        if st.button("ダウンロード開始", type="primary", use_container_width=True):
            st.session_state.stage = 'processing'
            st.rerun()

# ステップ3: ダウンロード
if st.session_state.stage == 'processing':
    results, zip_data = process_download(st.session_state.video_infos)
    if results:
        st.session_state.download_results = results
        st.session_state.zip_data = zip_data
        st.session_state.stage = 'finished'
        st.rerun()

if st.session_state.stage == 'finished':
    st.markdown('### <i class="fa-solid fa-download icon-spacing"></i> 3. ダウンロード', unsafe_allow_html=True)
    
    if st.session_state.zip_data:
        st.download_button(
            label="まとめてZIPで保存",
            data=st.session_state.zip_data,
            file_name="archive.zip",
            mime="application/zip",
            use_container_width=True,
            type="primary"
        )

    st.markdown("個別ファイル:")
    for item in st.session_state.download_results:
        st.download_button(
            label=f"保存: {item['filename']}",
            data=item['data'],
            file_name=item['filename'],
            mime=item['mime'],
            key=f"dl_{item['filename']}",
            use_container_width=True
        )
        
    if st.button("トップに戻る"):
        st.session_state.stage = 'input'
        st.rerun()
