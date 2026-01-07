import streamlit as st
import yt_dlp
import os
import tempfile
import time
import zipfile
import io
import re

# --- ページ設定 ---
st.set_page_config(page_title="Audio Downloader Pro", layout="centered", page_icon="🎵")

# --- Font Awesome & モダンカスタムCSSの注入 ---
st.markdown("""
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        /* --- 全体のフォントと背景 --- */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&family=Noto+Sans+JP:wght@400;700&display=swap');
        
        html, body, [class*="css"] {
            font-family: 'Inter', 'Noto Sans JP', sans-serif;
            color: #e0e0e0;
        }

        /* --- メインタイトル --- */
        .main-header {
            text-align: center;
            padding: 2rem 0;
            margin-bottom: 2rem;
        }
        .main-title {
            font-size: 3rem;
            font-weight: 800;
            background: linear-gradient(135deg, #00C6FF 0%, #0072FF 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            letter-spacing: -1px;
            margin: 0;
        }
        .sub-text {
            color: #888;
            font-size: 1rem;
            margin-top: 0.5rem;
            font-weight: 400;
        }

        /* --- カードデザイン (編集画面) --- */
        .track-card {
            background-color: #1a1a1a;
            border: 1px solid #333;
            border-radius: 16px;
            padding: 20px;
            margin-bottom: 24px;
            transition: all 0.3s ease;
            box-shadow: 0 4px 6px rgba(0,0,0,0.2);
        }
        .track-card:hover {
            border-color: #0072ff;
            box-shadow: 0 8px 15px rgba(0, 114, 255, 0.15);
            transform: translateY(-2px);
        }
        
        /* --- 入力フィールドのカスタマイズ --- */
        .stTextInput input, .stTextArea textarea {
            background-color: #252525 !important;
            color: #fff !important;
            border: 1px solid #444 !important;
            border-radius: 8px !important;
        }
        .stTextInput input:focus, .stTextArea textarea:focus {
            border-color: #0072ff !important;
            box-shadow: 0 0 0 2px rgba(0, 114, 255, 0.2) !important;
        }

        /* --- ボタンのスタイル調整 --- */
        /* プライマリボタン */
        div[data-testid="stButton"] > button[kind="primary"] {
            background: linear-gradient(135deg, #0072ff 0%, #00c6ff 100%);
            border: none;
            color: white;
            font-weight: 600;
            border-radius: 8px;
            padding: 0.5rem 1rem;
            transition: opacity 0.2s;
        }
        div[data-testid="stButton"] > button[kind="primary"]:hover {
            opacity: 0.9;
            box-shadow: 0 4px 12px rgba(0, 114, 255, 0.4);
        }

        /* 削除ボタン（セカンダリ） */
        div[data-testid="stButton"] > button[kind="secondary"] {
            background-color: transparent;
            border: 1px solid #555;
            color: #aaa;
            border-radius: 8px;
        }
        div[data-testid="stButton"] > button[kind="secondary"]:hover {
            border-color: #ff4b4b;
            color: #ff4b4b;
            background-color: rgba(255, 75, 75, 0.1);
        }

        /* --- アイコンの装飾 --- */
        .icon-box {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 32px;
            height: 32px;
            background: rgba(0, 114, 255, 0.1);
            border-radius: 8px;
            color: #0072ff;
            margin-right: 12px;
        }
        .step-header {
            font-size: 1.4rem;
            font-weight: 700;
            margin-bottom: 1rem;
            display: flex;
            align-items: center;
        }

        /* --- プログレスエリア --- */
        .status-box {
            background: #252525;
            padding: 15px;
            border-radius: 10px;
            border-left: 4px solid #0072ff;
            margin-bottom: 10px;
        }
    </style>
""", unsafe_allow_html=True)

# --- ヘッダー部分 ---
st.markdown("""
    <div class="main-header">
        <div class="main-title"><i class="fa-solid fa-waveform"></i> Audio Downloader Pro</div>
        <div class="sub-text">YouTube to MP3 Converter & Metadata Editor</div>
    </div>
""", unsafe_allow_html=True)

# ── 内部関数: ファイル名サニタイズ ──
def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name)

# ── 内部関数: Cookieの自動生成 ──
def create_cookie_file(tmp_dir):
    if "general" in st.secrets and "YOUTUBE_COOKIES" in st.secrets["general"]:
        cookie_content = st.secrets["general"]["YOUTUBE_COOKIES"]
        cookie_path = os.path.join(tmp_dir, "cookies.txt")
        with open(cookie_path, "w", encoding="utf-8") as f:
            f.write(cookie_content)
        return cookie_path
    return None

# ── 内部関数: 動画削除コールバック ──
def remove_video(index):
    if 0 <= index < len(st.session_state.video_infos):
        del st.session_state.video_infos[index]

# ── サイドバー設定 ──
with st.sidebar:
    st.markdown("### <i class='fa-solid fa-gear'></i> 設定", unsafe_allow_html=True)
    
    st.markdown("""
        <div style="font-size:0.85rem; color:#aaa; margin-bottom:15px;">
        ダウンロードオプションを設定します。
        </div>
    """, unsafe_allow_html=True)
    
    # 音声用設定のみ表示
    st.markdown('**<i class="fa-solid fa-music"></i> 音質 (ビットレート)**', unsafe_allow_html=True)
    audio_quality_map = {
        '最高 (Best)': '0', 
        '高音質 (192kbps)': '192', 
        '標準 (128kbps)': '128'
    }
    quality_label = st.selectbox("ビットレート選択", list(audio_quality_map.keys()), label_visibility="collapsed")
    quality_val = audio_quality_map[quality_label]
    
    st.markdown('---')
    st.markdown('**<i class="fa-solid fa-tags"></i> メタデータ**', unsafe_allow_html=True)
    embed_thumb = st.checkbox("サムネイルを埋め込む", value=True)
    add_metadata = st.checkbox("曲名・歌手情報を付与", value=True)

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
            self.status_placeholder.markdown(f"""
                <div class="status-box">
                    <i class="fa-solid fa-circle-notch fa-spin"></i> ダウンロード中... <b>{d['_percent_str']}</b> (速度: {speed})
                </div>
            """, unsafe_allow_html=True)
            
        elif d['status'] == 'finished':
            self.progress_bar.progress(1.0)
            self.status_placeholder.markdown("""
                <div class="status-box" style="border-left-color: #00ff88;">
                    <i class="fa-solid fa-wand-magic-sparkles fa-spin"></i> 変換処理を実行中...
                </div>
            """, unsafe_allow_html=True)

# ── 処理ロジック ──
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
                        'uploader': info.get('uploader', 'Unknown'),
                        'thumbnail': info.get('thumbnail'),
                        'duration': info.get('duration'),
                        'url': url,
                        'custom_filename': sanitize_filename(info.get('title', 'audio')), 
                        'custom_artist': info.get('uploader', 'Unknown')
                    })
                except Exception as e:
                    st.error(f"Error: {e}")
    return info_list

def process_download(info_list):
    downloaded_data = []
    zip_buffer = None
    
    st.markdown("### <i class='fa-solid fa-bars-progress'></i> 処理状況", unsafe_allow_html=True)
    main_progress = st.progress(0)
    main_status = st.empty()
    total_videos = len(info_list)

    with tempfile.TemporaryDirectory() as tmp_dir:
        cookie_path = create_cookie_file(tmp_dir)
        for idx, info in enumerate(info_list):
            url = info['url']
            final_filename = sanitize_filename(info['custom_filename'])
            
            main_status.markdown(f"""
                <div style="margin-bottom: 5px;">
                    <i class="fa-solid fa-compact-disc"></i> 処理中 ({idx+1}/{total_videos}): <b>{final_filename}</b>
                </div>
            """, unsafe_allow_html=True)
            
            single_status = st.empty()
            single_bar = st.progress(0)
            hooks = ProgressHooks(single_status, single_bar)

            # MP3出力設定
            ydl_opts = {
                'outtmpl': f'{tmp_dir}/{final_filename}.%(ext)s',
                'quiet': True,
                'progress_hooks': [hooks.hook],
            }
            if cookie_path: ydl_opts['cookiefile'] = cookie_path

            postprocessors = [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3'}]
            if quality_val != '0':
                postprocessors[0]['preferredquality'] = quality_val
            
            if add_metadata:
                postprocessors.append({
                    'key': 'FFmpegMetadata',
                    'add_metadata': True,
                })
            
            if embed_thumb:
                ydl_opts['writethumbnail'] = True
                postprocessors.append({'key': 'EmbedThumbnail'})
            
            ydl_opts.update({'format': 'bestaudio/best', 'postprocessors': postprocessors})

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                single_status.markdown(f"""
                    <div style="color:#00ff88; margin-bottom:15px;">
                        <i class="fa-solid fa-check"></i> 完了
                    </div>
                """, unsafe_allow_html=True)
            except Exception as e:
                single_status.error(f"エラー: {e}")
                continue
            
            main_progress.progress((idx + 1) / total_videos)

        # ファイル回収
        files = [f for f in os.listdir(tmp_dir) if f.endswith(".mp3")]
        for filename in files:
            with open(os.path.join(tmp_dir, filename), "rb") as f:
                downloaded_data.append({"filename": filename, "data": f.read(), "mime": "audio/mpeg"})

        # ZIP作成
        if len(files) > 0:
            zip_io = io.BytesIO()
            with zipfile.ZipFile(zip_io, 'w', zipfile.ZIP_DEFLATED) as zf:
                for filename in files:
                    zf.write(os.path.join(tmp_dir, filename), arcname=filename)
            zip_buffer = zip_io.getvalue()
            
        main_status.markdown("""
            <div style="background:#0072ff; color:white; padding:10px; border-radius:8px; text-align:center; margin-top:20px;">
                <i class="fa-solid fa-flag-checkered"></i> すべての処理が完了しました
            </div>
        """, unsafe_allow_html=True)
        return downloaded_data, zip_buffer


# --- メインUI ---
if 'stage' not in st.session_state:
    st.session_state.stage = 'input'
if 'video_infos' not in st.session_state:
    st.session_state.video_infos = []

# ステップ1: URL入力
if st.session_state.stage == 'input':
    st.markdown('<div class="step-header"><div class="icon-box"><i class="fa-solid fa-link"></i></div>URLを入力</div>', unsafe_allow_html=True)
    
    url_input = st.text_area(
        label="URL",
        placeholder="ここにYouTubeのURLを貼り付けてください（複数行可）...",
        height=180,
        label_visibility="collapsed"
    )

    col1, col2 = st.columns([2, 1])
    with col2:
        if st.button("情報を取得する", type="primary", use_container_width=True):
            urls = [u.strip() for u in url_input.splitlines() if u.strip()]
            if urls:
                with st.spinner("メタデータを解析中..."):
                    infos = get_video_info(urls)
                    if infos:
                        st.session_state.video_infos = infos
                        st.session_state.stage = 'preview'
                        st.rerun()
            else:
                st.warning("URLが入力されていません")

# ステップ2: プレビュー & 編集
if st.session_state.stage == 'preview':
    st.markdown(f'<div class="step-header"><div class="icon-box"><i class="fa-solid fa-pen-nib"></i></div>編集と確認 <span style="font-size:0.8em; margin-left:10px; color:#888;">{len(st.session_state.video_infos)}件</span></div>', unsafe_allow_html=True)
    
    if len(st.session_state.video_infos) == 0:
        st.info("リストが空です。URLを入力し直してください。")
        if st.button("戻る"):
            st.session_state.stage = 'input'
            st.rerun()
    
    current_infos = st.session_state.video_infos.copy()
    
    for idx, info in enumerate(current_infos):
        # カードコンテナ開始
        st.markdown('<div class="track-card">', unsafe_allow_html=True)
        
        c_thumb, c_info, c_action = st.columns([1.5, 3.5, 0.5])
        
        with c_thumb:
            if info['thumbnail']:
                st.image(info['thumbnail'], use_container_width=True)
            else:
                st.markdown('<div style="height:80px; background:#333; display:flex; align-items:center; justify-content:center; border-radius:8px;"><i class="fa-solid fa-image" style="color:#555;"></i></div>', unsafe_allow_html=True)
            
            duration_m = info['duration'] // 60 if info['duration'] else 0
            duration_s = info['duration'] % 60 if info['duration'] else 0
            st.markdown(f'<div style="text-align:center; font-size:0.8rem; color:#888; margin-top:5px;"><i class="fa-regular fa-clock"></i> {duration_m}:{duration_s:02d}</div>', unsafe_allow_html=True)

        with c_info:
            new_filename = st.text_input(
                "ファイル名", 
                value=info['custom_filename'], 
                key=f"fname_{idx}",
                label_visibility="collapsed",
                placeholder="ファイル名"
            )
            st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True) # Spacer
            new_artist = st.text_input(
                "アーティスト", 
                value=info['custom_artist'], 
                key=f"artist_{idx}",
                label_visibility="collapsed",
                placeholder="アーティスト名"
            )
            
            st.session_state.video_infos[idx]['custom_filename'] = new_filename
            st.session_state.video_infos[idx]['custom_artist'] = new_artist

        with c_action:
            st.markdown('<br>', unsafe_allow_html=True)
            # アイコン風のテキストボタン
            if st.button("×", key=f"del_{idx}", help="リストから削除", type="secondary"):
                remove_video(idx)
                st.rerun()

        st.markdown('</div>', unsafe_allow_html=True)
        # カードコンテナ終了
    
    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("戻る", use_container_width=True):
            st.session_state.stage = 'input'
            st.rerun()
    with c2:
        # FontAwesomeアイコンをボタンテキストには直接入れられないため、テキストで表現
        if st.button("ダウンロード開始", type="primary", use_container_width=True):
            st.session_state.stage = 'processing'
            st.rerun()

# ステップ3: ダウンロード処理
if st.session_state.stage == 'processing':
    results, zip_data = process_download(st.session_state.video_infos)
    if results:
        st.session_state.download_results = results
        st.session_state.zip_data = zip_data
        st.session_state.stage = 'finished'
        st.rerun()
    else:
        st.error("ダウンロード可能なファイルがありませんでした。")
        if st.button("戻る"):
            st.session_state.stage = 'preview'
            st.rerun()

# ステップ4: 完了画面
if st.session_state.stage == 'finished':
    st.markdown('<div class="step-header"><div class="icon-box"><i class="fa-solid fa-download"></i></div>ダウンロード</div>', unsafe_allow_html=True)
    
    if st.session_state.zip_data:
        st.download_button(
            label="ZIPでまとめてダウンロード",
            data=st.session_state.zip_data,
            file_name="audio_archive.zip",
            mime="application/zip",
            use_container_width=True,
            type="primary"
        )

    st.markdown('<h4 style="margin-top:20px; color:#aaa; font-size:1rem;">個別ファイル</h4>', unsafe_allow_html=True)
    
    for item in st.session_state.download_results:
        size_mb = len(item['data']) / (1024 * 1024)
        
        # リスト風デザイン
        c_icon, c_name, c_btn = st.columns([0.5, 3, 1.2])
        
        with c_icon:
            st.markdown('<div style="text-align:center; padding-top:10px; color:#0072ff;"><i class="fa-solid fa-file-audio fa-lg"></i></div>', unsafe_allow_html=True)
        
        with c_name:
            st.markdown(f'<div style="padding-top:8px;"><b>{item["filename"]}</b> <span style="color:#666; font-size:0.8rem;">({size_mb:.1f} MB)</span></div>', unsafe_allow_html=True)
            
        with c_btn:
            st.download_button(
                label="保存",
                data=item['data'],
                file_name=item['filename'],
                mime=item['mime'],
                key=f"dl_{item['filename']}",
                use_container_width=True
            )
        st.markdown("<hr style='margin: 5px 0; border-color: #333;'>", unsafe_allow_html=True)
        
    if st.button("最初に戻る", use_container_width=True):
        st.session_state.stage = 'input'
        st.session_state.video_infos = []
        st.session_state.download_results = None
        st.rerun()
