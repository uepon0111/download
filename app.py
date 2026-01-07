import streamlit as st
import yt_dlp
import os
import tempfile
import zipfile
import io
import re

# --- ページ設定 ---
st.set_page_config(
    page_title="Audio Downloader Pro",
    layout="centered",
    initial_sidebar_state="expanded"
)

# --- カスタムCSSの注入 (モダンデザイン・アイコン化) ---
st.markdown("""
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        /* 全体のフォントと背景 */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;800&display=swap');
        
        /* Streamlitのデフォルトスタイルを上書き */
        .stApp {
            background-color: #0f1116;
            font-family: 'Inter', sans-serif;
        }
        
        /* ヘッダーの非表示（スッキリさせるため） */
        header {visibility: hidden;}

        /* グラデーションタイトル */
        .main-header {
            text-align: center;
            padding: 40px 0 20px 0;
        }
        .main-title {
            font-size: 3rem;
            font-weight: 800;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            letter-spacing: -1px;
            margin: 0;
        }
        .sub-title {
            color: #a0aaec;
            font-size: 1rem;
            font-weight: 400;
            margin-top: 10px;
        }

        /* カードデザイン (グラスモーフィズム) */
        .modern-card {
            background: rgba(30, 32, 40, 0.7);
            border: 1px solid rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 24px;
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3);
            transition: transform 0.2s ease;
        }
        
        /* リストアイテムのデザイン */
        .list-item-container {
            background: #1a1c24;
            border-radius: 12px;
            border: 1px solid #2d3748;
            padding: 16px;
            margin-bottom: 16px;
        }

        /* ボタンのスタイル調整（Streamlit標準ボタンをCSSで微調整は限界があるためコンテナで魅せる） */
        .stButton > button {
            border-radius: 8px;
            font-weight: 600;
            border: none;
            transition: all 0.3s;
        }
        .stButton > button:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.2);
        }

        /* アイコンの色設定 */
        .icon-primary { color: #667eea; }
        .icon-success { color: #00b894; }
        .icon-danger { color: #ff7675; }
        .icon-warning { color: #fdcb6e; }
        .icon-spacing { margin-right: 8px; }

        /* 画像の角丸 */
        img { border-radius: 8px; }
        
        /* プログレスバーの色変更 */
        .stProgress > div > div > div > div {
            background-image: linear-gradient(to right, #667eea, #764ba2);
        }
    </style>
""", unsafe_allow_html=True)

# ── 内部関数 ──
def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name)

def create_cookie_file(tmp_dir):
    if "general" in st.secrets and "YOUTUBE_COOKIES" in st.secrets["general"]:
        cookie_content = st.secrets["general"]["YOUTUBE_COOKIES"]
        cookie_path = os.path.join(tmp_dir, "cookies.txt")
        with open(cookie_path, "w", encoding="utf-8") as f:
            f.write(cookie_content)
        return cookie_path
    return None

def remove_video(index):
    if 0 <= index < len(st.session_state.video_infos):
        del st.session_state.video_infos[index]

# ── サイドバー（設定） ──
with st.sidebar:
    st.markdown("### <i class='fa-solid fa-gear icon-spacing'></i> 設定", unsafe_allow_html=True)
    
    st.markdown("<div style='font-size:0.9rem; color:#888; margin-bottom:10px;'>出力オプション</div>", unsafe_allow_html=True)
    
    # 音質設定
    audio_quality_map = {
        '最高 (Best)': '0', 
        '高音質 (192kbps)': '192', 
        '標準 (128kbps)': '128'
    }
    quality_label = st.selectbox("ビットレート", list(audio_quality_map.keys()))
    quality_val = audio_quality_map[quality_label]
    
    st.markdown("---")
    
    # チェックボックス
    embed_thumb = st.checkbox("サムネイル埋め込み", value=True)
    add_metadata = st.checkbox("メタデータ(ID3)付与", value=True)
    
    st.markdown("---")
    st.markdown("<div style='text-align:center; color:#555; font-size:0.8rem;'>Audio Downloader v2.0</div>", unsafe_allow_html=True)

# ── ヘッダー ──
st.markdown("""
    <div class="main-header">
        <div class="main-title"><i class="fa-brands fa-youtube icon-spacing"></i>Audio Pro</div>
        <div class="sub-title">YouTube to MP3 Converter & Metadata Editor</div>
    </div>
""", unsafe_allow_html=True)

# ── 進捗フッククラス ──
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
            self.status_placeholder.markdown(f'<span style="color:#a0aaec"><i class="fa-solid fa-spinner fa-spin icon-spacing"></i>ダウンロード中... {d["_percent_str"]} (速度: {speed})</span>', unsafe_allow_html=True)
            
        elif d['status'] == 'finished':
            self.progress_bar.progress(1.0)
            self.status_placeholder.markdown('<span style="color:#00b894"><i class="fa-solid fa-wand-magic-sparkles icon-spacing"></i>変換処理中...</span>', unsafe_allow_html=True)

# ── ロジック: 動画情報取得 ──
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

# ── ロジック: ダウンロード処理 ──
def process_download(info_list):
    downloaded_data = []
    zip_buffer = None
    
    # 全体進捗用
    st.markdown("### <i class='fa-solid fa-microchip icon-spacing'></i>処理ステータス", unsafe_allow_html=True)
    main_progress = st.progress(0)
    current_status_text = st.empty()
    
    total_videos = len(info_list)

    with tempfile.TemporaryDirectory() as tmp_dir:
        cookie_path = create_cookie_file(tmp_dir)
        
        for idx, info in enumerate(info_list):
            url = info['url']
            final_filename = sanitize_filename(info['custom_filename'])
            
            # カード形式で進捗を表示
            with st.container():
                st.markdown(f"""
                <div class="list-item-container" style="border-left: 4px solid #667eea;">
                    <div style="font-weight:bold; margin-bottom:8px;">
                        <i class="fa-solid fa-circle-play icon-spacing icon-primary"></i>{final_filename}
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                col_stat, col_bar = st.columns([1, 2])
                with col_stat:
                    single_status = st.empty()
                with col_bar:
                    single_bar = st.progress(0)
                
                hooks = ProgressHooks(single_status, single_bar)

                # yt-dlp設定
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
                    postprocessors.append({'key': 'FFmpegMetadata', 'add_metadata': True})
                
                if embed_thumb:
                    ydl_opts['writethumbnail'] = True
                    postprocessors.append({'key': 'EmbedThumbnail'})
                
                ydl_opts.update({'format': 'bestaudio/best', 'postprocessors': postprocessors})

                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([url])
                    single_status.markdown('<span style="color:#00b894; font-weight:bold;"><i class="fa-solid fa-check icon-spacing"></i>完了</span>', unsafe_allow_html=True)
                except Exception as e:
                    single_status.markdown(f'<span style="color:#ff7675; font-weight:bold;"><i class="fa-solid fa-circle-exclamation icon-spacing"></i>失敗</span>', unsafe_allow_html=True)
                    st.error(f"Details: {e}")
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
        
    return downloaded_data, zip_buffer


# --- ステート管理 ---
if 'stage' not in st.session_state:
    st.session_state.stage = 'input'
if 'video_infos' not in st.session_state:
    st.session_state.video_infos = []

# ==========================================
# STEP 1: URL入力画面
# ==========================================
if st.session_state.stage == 'input':
    st.markdown('<div class="modern-card">', unsafe_allow_html=True)
    st.markdown('#### <i class="fa-solid fa-link icon-spacing icon-primary"></i> リンクを貼り付け', unsafe_allow_html=True)
    st.markdown('<p style="font-size:0.9rem; color:#ccc;">YouTubeのURLを1行に1つずつ入力してください。</p>', unsafe_allow_html=True)
    
    url_input = st.text_area(
        label="URL",
        placeholder="https://www.youtube.com/watch?v=...\nhttps://youtu.be/...",
        height=180,
        label_visibility="collapsed"
    )
    
    col_act_1, col_act_2, col_act_3 = st.columns([1, 2, 1])
    with col_act_2:
        if st.button("情報を解析する", type="primary", use_container_width=True):
            urls = [u.strip() for u in url_input.splitlines() if u.strip()]
            if urls:
                with st.spinner("メタデータを取得中..."):
                    infos = get_video_info(urls)
                    if infos:
                        st.session_state.video_infos = infos
                        st.session_state.stage = 'preview'
                        st.rerun()
            else:
                st.warning("URLが入力されていません")
    st.markdown('</div>', unsafe_allow_html=True)

# ==========================================
# STEP 2: プレビュー & 編集画面
# ==========================================
elif st.session_state.stage == 'preview':
    st.markdown(f"""
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;">
        <h3 style="margin:0;"><i class="fa-solid fa-list icon-spacing"></i>ダウンロードリスト ({len(st.session_state.video_infos)})</h3>
    </div>
    """, unsafe_allow_html=True)
    
    if len(st.session_state.video_infos) == 0:
        st.info("リストが空です。")
        if st.button("戻る"):
            st.session_state.stage = 'input'
            st.rerun()
    
    current_infos = st.session_state.video_infos.copy()
    
    # 編集カードのループ
    for idx, info in enumerate(current_infos):
        with st.container():
            # カード開始
            st.markdown('<div class="list-item-container">', unsafe_allow_html=True)
            
            c_thumb, c_info, c_action = st.columns([2, 4, 1])
            
            with c_thumb:
                if info['thumbnail']:
                    st.image(info['thumbnail'], use_container_width=True)
                    duration_m = info['duration'] // 60 if info['duration'] else 0
                    duration_s = info['duration'] % 60 if info['duration'] else 0
                    st.caption(f'<i class="fa-regular fa-clock icon-spacing"></i>{duration_m}:{duration_s:02d}', unsafe_allow_html=True)
                else:
                    st.markdown('<div style="height:100px; background:#222; border-radius:8px;"></div>', unsafe_allow_html=True)

            with c_info:
                st.markdown(f"**元タイトル**: {info['title']}")
                
                new_filename = st.text_input(
                    "ファイル名", 
                    value=info['custom_filename'], 
                    key=f"fname_{idx}",
                    placeholder="ファイル名",
                    label_visibility="collapsed"
                )
                st.caption("ファイル名 (拡張子不要)")

                new_artist = st.text_input(
                    "アーティスト", 
                    value=info['custom_artist'], 
                    key=f"artist_{idx}",
                    placeholder="アーティスト名",
                    label_visibility="collapsed"
                )
                st.caption("アーティスト / チャンネル名")
                
                st.session_state.video_infos[idx]['custom_filename'] = new_filename
                st.session_state.video_infos[idx]['custom_artist'] = new_artist

            with c_action:
                st.markdown("<br>", unsafe_allow_html=True)
                # 削除ボタン
                if st.button("削除", key=f"del_{idx}", type="secondary"):
                    remove_video(idx)
                    st.rerun()

            st.markdown('</div>', unsafe_allow_html=True)
    
    # アクションボタンエリア
    st.markdown("---")
    col_back, col_go = st.columns([1, 2])
    with col_back:
        if st.button("戻る", use_container_width=True):
            st.session_state.stage = 'input'
            st.rerun()
    with col_go:
        if st.button("ダウンロード開始", type="primary", use_container_width=True):
            st.session_state.stage = 'processing'
            st.rerun()

# ==========================================
# STEP 3: 処理実行画面
# ==========================================
elif st.session_state.stage == 'processing':
    results, zip_data = process_download(st.session_state.video_infos)
    if results:
        st.session_state.download_results = results
        st.session_state.zip_data = zip_data
        st.session_state.stage = 'finished'
        st.rerun()
    else:
        st.error("ダウンロード可能なファイルが見つかりませんでした。")
        if st.button("戻る"):
            st.session_state.stage = 'preview'
            st.rerun()

# ==========================================
# STEP 4: 完了 & ダウンロード画面
# ==========================================
elif st.session_state.stage == 'finished':
    st.markdown('<div class="modern-card" style="text-align:center;">', unsafe_allow_html=True)
    st.markdown('<div style="font-size:4rem; color:#00b894; margin-bottom:10px;"><i class="fa-regular fa-circle-check"></i></div>', unsafe_allow_html=True)
    st.markdown('<h3>All Tasks Completed!</h3>', unsafe_allow_html=True)
    
    if st.session_state.zip_data:
        st.markdown("<br>", unsafe_allow_html=True)
        col_z1, col_z2, col_z3 = st.columns([1,2,1])
        with col_z2:
            st.download_button(
                label="ZIPでまとめて保存",
                data=st.session_state.zip_data,
                file_name="audio_archive.zip",
                mime="application/zip",
                use_container_width=True,
                type="primary"
            )
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('#### <i class="fa-solid fa-file-audio icon-spacing"></i> 個別ファイル', unsafe_allow_html=True)
    
    for item in st.session_state.download_results:
        size_mb = len(item['data']) / (1024 * 1024)
        
        with st.container():
            st.markdown('<div class="list-item-container" style="padding:12px;">', unsafe_allow_html=True)
            c_icon, c_name, c_btn = st.columns([0.5, 3, 1])
            
            with c_icon:
                st.markdown('<i class="fa-solid fa-music fa-lg icon-primary" style="margin-top:10px;"></i>', unsafe_allow_html=True)
            with c_name:
                st.markdown(f"**{item['filename']}**")
                st.caption(f"{size_mb:.1f} MB")
            with c_btn:
                st.download_button(
                    label="保存",
                    data=item['data'],
                    file_name=item['filename'],
                    mime=item['mime'],
                    key=f"dl_{item['filename']}",
                    use_container_width=True
                )
            st.markdown('</div>', unsafe_allow_html=True)
            
    if st.button("新しいファイルを変換する"):
        st.session_state.stage = 'input'
        st.session_state.video_infos = []
        st.session_state.download_results = None
        st.rerun()
