import streamlit as st
import yt_dlp
import os
import tempfile
import time
import zipfile
import io
import re
import subprocess
import shutil

# --- ページ設定 ---
st.set_page_config(page_title="Audio Editor & Downloader", layout="centered")

# --- Font Awesome & カスタムCSS (ホワイトベース) ---
st.markdown("""
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        /* 全体のフォント設定 */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
        
        html, body, [class*="css"] {
            font-family: 'Inter', sans-serif;
            color: #333333; /* テキスト色をダークグレーに */
        }

        /* アプリ全体の背景 */
        .stApp {
            background-color: #f8f9fa; /* 明るいグレー背景 */
        }

        /* メインタイトル */
        .main-title {
            font-size: 2.5rem;
            font-weight: 800;
            background: linear-gradient(135deg, #2563eb, #06b6d4); /* 青〜シアン */
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
        }

        /* サブタイトル */
        .sub-text {
            color: #64748b;
            font-size: 1rem;
            margin-bottom: 2rem;
        }

        /* カードデザイン (ホワイトベース) */
        .edit-card {
            background-color: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
        }
        
        /* サムネイル画像 */
        .thumb-img {
            border-radius: 8px;
            width: 100%;
            object-fit: cover;
            border: 1px solid #f1f5f9;
        }

        /* ボタンスタイル調整（視認性向上） */
        button[kind="secondary"] {
            border-color: #ef4444 !important;
            color: #ef4444 !important;
            background-color: transparent !important;
        }
        button[kind="secondary"]:hover {
            background-color: #ef4444 !important;
            color: white !important;
        }

        /* アイコンのスタイル */
        .icon-spacing {
            margin-right: 8px;
            color: #2563eb;
        }
        
        /* ステータス表示エリア */
        .status-box {
            padding: 10px;
            background-color: #e0f2fe;
            border-radius: 8px;
            color: #0369a1;
            margin-bottom: 10px;
        }
    </style>
""", unsafe_allow_html=True)

# --- ヘッダー部分 ---
st.markdown('<div class="main-title"><i class="fa-solid fa-music icon-spacing"></i>Audio Editor & Downloader</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-text">YouTubeダウンロード & MP3メタデータ編集ツール</div>', unsafe_allow_html=True)

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

# ── 内部関数: 動画/ファイル削除コールバック ──
def remove_video(index):
    if 0 <= index < len(st.session_state.video_infos):
        del st.session_state.video_infos[index]

# ── サイドバー設定 ──
with st.sidebar:
    st.markdown('### <i class="fa-solid fa-sliders icon-spacing"></i> 設定', unsafe_allow_html=True)
    
    st.markdown('**<i class="fa-solid fa-headphones icon-spacing"></i> 音質設定**')
    audio_quality_map = {
        '最高 (Best)': '0', 
        '高音質 (192kbps)': '192', 
        '標準 (128kbps)': '128'
    }
    quality_label = st.selectbox("ビットレート", list(audio_quality_map.keys()))
    quality_val = audio_quality_map[quality_label]
    
    st.markdown('---')
    embed_thumb = st.checkbox("カバー画像埋め込み", value=True)
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
            self.status_placeholder.markdown(f'<span style="color:#2563eb"><i class="fa-solid fa-spinner fa-spin"></i> ダウンロード中... {d["_percent_str"]} (速度: {speed})</span>', unsafe_allow_html=True)
            
        elif d['status'] == 'finished':
            self.progress_bar.progress(1.0)
            self.status_placeholder.markdown('<span style="color:#059669"><i class="fa-solid fa-arrows-rotate fa-spin"></i> 変換処理中...</span>', unsafe_allow_html=True)

# ── 処理ロジック: 情報取得 (YouTube & Upload) ──
def get_video_info(urls=None, uploaded_files=None):
    info_list = []
    
    # 1. YouTube URLの処理
    if urls:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cookie_path = create_cookie_file(tmp_dir)
            ydl_opts = {'quiet': True, 'extract_flat': False, 'skip_download': True}
            if cookie_path: ydl_opts['cookiefile'] = cookie_path
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                for url in urls:
                    try:
                        info = ydl.extract_info(url, download=False)
                        title = info.get('title', 'Unknown')
                        uploader = info.get('uploader', 'Unknown')
                        info_list.append({
                            'source_type': 'youtube', # 識別子
                            'title': title,
                            'uploader': uploader,
                            'thumbnail': info.get('thumbnail'),
                            'duration': info.get('duration'),
                            'url': url,
                            # 以下編集用フィールド
                            'custom_filename': sanitize_filename(title), 
                            'custom_title': title,            
                            'custom_artist': uploader,        
                            'custom_album': title,            
                            'thumb_mode': 'youtube',          
                            'custom_thumb_bytes': None        
                        })
                    except Exception as e:
                        st.error(f"Error (URL): {e}")

    # 2. アップロードファイルの処理
    if uploaded_files:
        for u_file in uploaded_files:
            # 拡張子を除いたファイル名をタイトルとする
            base_name = os.path.splitext(u_file.name)[0]
            info_list.append({
                'source_type': 'file', # 識別子
                'title': base_name,
                'uploader': 'User Upload',
                'thumbnail': None,
                'duration': None,
                'url': None,
                'file_bytes': u_file.getvalue(), # ファイルの実体
                # 編集用フィールド
                'custom_filename': sanitize_filename(base_name),
                'custom_title': base_name,
                'custom_artist': '',
                'custom_album': '',
                'thumb_mode': 'upload', # ファイルの場合はデフォルトでアップロードモード
                'custom_thumb_bytes': None
            })
            
    return info_list

# ── 処理ロジック: ダウンロードと変換 ──
def process_download(info_list):
    downloaded_data = []
    zip_buffer = None
    main_progress = st.progress(0)
    main_status = st.empty()
    total_videos = len(info_list)

    with tempfile.TemporaryDirectory() as tmp_dir:
        cookie_path = create_cookie_file(tmp_dir)
        
        for idx, info in enumerate(info_list):
            base_filename = f"track_{idx}" # 一時ファイル名
            final_filename = sanitize_filename(info['custom_filename'])
            
            # メタデータ情報の取得
            m_title = info['custom_title']
            m_artist = info['custom_artist']
            m_album = info['custom_album']

            main_status.markdown(f'<div class="status-box"><i class="fa-solid fa-list-check icon-spacing"></i> 処理中 ({idx+1}/{total_videos}): <b>{final_filename}</b></div>', unsafe_allow_html=True)
            
            single_status = st.empty()
            single_bar = st.progress(0)
            hooks = ProgressHooks(single_status, single_bar)

            try:
                mp3_path = f"{tmp_dir}/{base_filename}.mp3"
                cover_image_path = None

                # --- ソース別処理 ---
                if info['source_type'] == 'youtube':
                    # YouTubeダウンロード
                    ydl_opts = {
                        'outtmpl': f'{tmp_dir}/{base_filename}.%(ext)s',
                        'quiet': True,
                        'progress_hooks': [hooks.hook],
                        'writethumbnail': True, 
                        'skip_download': False,
                    }
                    if cookie_path: ydl_opts['cookiefile'] = cookie_path
                    postprocessors = [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3'}]
                    if quality_val != '0':
                        postprocessors[0]['preferredquality'] = quality_val
                    ydl_opts.update({'format': 'bestaudio/best', 'postprocessors': postprocessors})

                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([info['url']])
                    
                    if not os.path.exists(mp3_path):
                        raise Exception("MP3 conversion failed")
                    
                    # サムネイル検索 (YouTube由来)
                    if embed_thumb and info['thumb_mode'] == 'youtube':
                         for f in os.listdir(tmp_dir):
                            if f.startswith(base_filename) and f.lower().endswith(('.jpg', '.jpeg', '.webp', '.png')) and not f.endswith('.mp3'):
                                cover_image_path = os.path.join(tmp_dir, f)
                                break
                                
                elif info['source_type'] == 'file':
                    # アップロードファイル保存
                    single_status.markdown('<i class="fa-solid fa-file-export icon-spacing"></i> ファイル展開中...', unsafe_allow_html=True)
                    with open(mp3_path, "wb") as f:
                        f.write(info['file_bytes'])
                    single_bar.progress(0.5)

                # --- 画像処理 (カスタムアップロードがある場合) ---
                if info['thumb_mode'] == 'upload' and info['custom_thumb_bytes']:
                    cover_image_path = f"{tmp_dir}/{base_filename}_custom_cover.jpg"
                    with open(cover_image_path, "wb") as f:
                        f.write(info['custom_thumb_bytes'])

                # --- FFmpeg実行 ---
                output_mp3_path = f"{tmp_dir}/{final_filename}.mp3"
                ffmpeg_cmd = ['ffmpeg', '-y', '-i', mp3_path]

                if cover_image_path and embed_thumb:
                    ffmpeg_cmd.extend(['-i', cover_image_path])
                    ffmpeg_cmd.extend(['-map', '0:0', '-map', '1:0'])
                    ffmpeg_cmd.extend(['-c:v', 'copy', '-id3v2_version', '3', '-metadata:s:v', 'title="Album cover"', '-metadata:s:v', 'comment="Cover (front)"'])
                else:
                    ffmpeg_cmd.extend(['-map', '0:0'])
                
                # 再エンコードせずコピー (メタデータだけ書き換え)
                ffmpeg_cmd.extend(['-c:a', 'copy'])

                if add_metadata:
                    ffmpeg_cmd.extend([
                        '-metadata', f'title={m_title}',
                        '-metadata', f'artist={m_artist}',
                        '-metadata', f'album={m_album}'
                    ])
                
                ffmpeg_cmd.append(output_mp3_path)
                
                single_status.markdown('<i class="fa-solid fa-gears icon-spacing"></i> メタデータ書き込み中...', unsafe_allow_html=True)
                subprocess.run(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                
                # 完了
                single_bar.progress(1.0)
                single_status.markdown('<span style="color:#059669"><i class="fa-solid fa-circle-check"></i> 完了</span>', unsafe_allow_html=True)

            except Exception as e:
                single_status.error(f"エラー: {e}")
                print(e)
                continue
            
            main_progress.progress((idx + 1) / total_videos)

        # ファイル回収
        files = [f for f in os.listdir(tmp_dir) if f.endswith(".mp3") and not f.startswith("track_")]
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
            
        main_status.markdown('<div class="status-box" style="background-color:#dcfce7; color:#166534;"><i class="fa-solid fa-check icon-spacing"></i> すべての処理が完了しました！</div>', unsafe_allow_html=True)
        return downloaded_data, zip_buffer


# --- メインUI ---
if 'stage' not in st.session_state:
    st.session_state.stage = 'input'
if 'video_infos' not in st.session_state:
    st.session_state.video_infos = []

# ステップ1: 入力 (URL または ファイル)
if st.session_state.stage == 'input':
    st.markdown('### <i class="fa-solid fa-folder-open icon-spacing"></i> 1. ファイルの選択', unsafe_allow_html=True)
    
    tab1, tab2 = st.tabs(["<i class='fa-brands fa-youtube'></i> YouTube URL", "<i class='fa-solid fa-file-audio'></i> MP3アップロード"])
    
    with tab1:
        st.markdown("<br>", unsafe_allow_html=True)
        url_input = st.text_area(
            label="URL入力",
            placeholder="https://www.youtube.com/watch?v=...\nhttps://youtu.be/...",
            height=150,
            label_visibility="collapsed"
        )
    
    with tab2:
        st.markdown("<br>", unsafe_allow_html=True)
        uploaded_files = st.file_uploader(
            "MP3ファイルを選択 (複数可)", 
            type=['mp3'], 
            accept_multiple_files=True
        )

    st.markdown("---")
    
    if st.button("情報を読み込む", type="primary", use_container_width=True):
        urls = [u.strip() for u in url_input.splitlines() if u.strip()] if url_input else []
        
        if not urls and not uploaded_files:
            st.warning("URLを入力するか、ファイルをアップロードしてください")
        else:
            with st.spinner("情報を解析しています..."):
                infos = get_video_info(urls, uploaded_files)
                if infos:
                    st.session_state.video_infos = infos
                    st.session_state.stage = 'preview'
                    st.rerun()

# ステップ2: プレビュー & 編集
if st.session_state.stage == 'preview':
    st.markdown(f'### <i class="fa-solid fa-pen-to-square icon-spacing"></i> 2. 編集と確認 ({len(st.session_state.video_infos)}件)', unsafe_allow_html=True)
    
    if len(st.session_state.video_infos) == 0:
        st.info("リストが空です。")
        if st.button("戻る"):
            st.session_state.stage = 'input'
            st.rerun()
    
    current_infos = st.session_state.video_infos.copy()
    
    for idx, info in enumerate(current_infos):
        with st.container():
            st.markdown('<div class="edit-card">', unsafe_allow_html=True)
            
            col_img, col_edit, col_del = st.columns([1.5, 3, 0.5])
            
            with col_img:
                st.caption("カバー画像")
                
                # 画像ソース選択肢の制御
                options = ["アップロード"]
                if info.get('source_type') == 'youtube':
                    options.insert(0, "YouTube")
                
                # 現在のモードが選択肢にない場合のフォールバック
                current_mode_index = 0
                if info['thumb_mode'] == 'upload':
                    current_mode_index = len(options) - 1
                
                thumb_mode = st.radio(
                    "画像ソース", 
                    options, 
                    index=current_mode_index,
                    key=f"thumb_mode_{idx}",
                    label_visibility="collapsed",
                    horizontal=True
                )
                
                st.session_state.video_infos[idx]['thumb_mode'] = 'youtube' if thumb_mode == "YouTube" else 'upload'

                if thumb_mode == "YouTube":
                    if info['thumbnail']:
                        st.image(info['thumbnail'], use_container_width=True)
                    else:
                        st.text("No Image")
                else:
                    uploaded_img = st.file_uploader("画像", type=['jpg', 'png', 'webp'], key=f"uploader_{idx}", label_visibility="collapsed")
                    if uploaded_img:
                        st.session_state.video_infos[idx]['custom_thumb_bytes'] = uploaded_img.getvalue()
                        st.image(uploaded_img, caption="New Cover", use_container_width=True)
                    elif info.get('custom_thumb_bytes'):
                        st.image(info['custom_thumb_bytes'], caption="New Cover", use_container_width=True)
                    else:
                         st.markdown('<div style="background:#f1f5f9; height:100px; display:flex; align-items:center; justify-content:center; color:#94a3b8; border-radius:8px;"><i class="fa-regular fa-image"></i></div>', unsafe_allow_html=True)

            with col_edit:
                # ファイル名
                new_filename = st.text_input(
                    "ファイル名 (拡張子なし)", 
                    value=info['custom_filename'], 
                    key=f"fname_{idx}"
                )
                
                st.markdown("---")
                
                # メタデータ
                mc1, mc2 = st.columns(2)
                with mc1:
                    new_title = st.text_input("タイトル (Title)", value=info['custom_title'], key=f"title_{idx}")
                    new_artist = st.text_input("アーティスト (Artist)", value=info['custom_artist'], key=f"artist_{idx}")
                with mc2:
                    new_album = st.text_input("アルバム (Album)", value=info['custom_album'], key=f"album_{idx}")
                
                st.session_state.video_infos[idx]['custom_filename'] = new_filename
                st.session_state.video_infos[idx]['custom_title'] = new_title
                st.session_state.video_infos[idx]['custom_artist'] = new_artist
                st.session_state.video_infos[idx]['custom_album'] = new_album

            with col_del:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("✕", key=f"del_{idx}", help="リストから削除", type="secondary"):
                    remove_video(idx)
                    st.rerun()

            st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("入力をやり直す", use_container_width=True):
            st.session_state.stage = 'input'
            st.rerun()
    with c2:
        if st.button("処理開始", type="primary", use_container_width=True):
            st.session_state.stage = 'processing'
            st.rerun()

# ステップ3: 実行中
if st.session_state.stage == 'processing':
    results, zip_data = process_download(st.session_state.video_infos)
    if results:
        st.session_state.download_results = results
        st.session_state.zip_data = zip_data
        st.session_state.stage = 'finished'
        st.rerun()
    else:
        st.error("処理可能なファイルがありませんでした。")
        if st.button("戻る"):
            st.session_state.stage = 'preview'
            st.rerun()

# ステップ4: 完了
if st.session_state.stage == 'finished':
    st.markdown('### <i class="fa-solid fa-download icon-spacing"></i> 3. ダウンロード', unsafe_allow_html=True)
    
    if st.session_state.zip_data:
        st.download_button(
            label="まとめてZIPダウンロード",
            data=st.session_state.zip_data,
            file_name="audio_files.zip",
            mime="application/zip",
            use_container_width=True,
            type="primary"
        )

    st.markdown("#### 個別ファイル")
    for item in st.session_state.download_results:
        size_mb = len(item['data']) / (1024 * 1024)
        
        col_dl_1, col_dl_2 = st.columns([3, 1])
        with col_dl_1:
            st.markdown(f'<div style="padding:10px;"><i class="fa-solid fa-file-audio icon-spacing"></i><b>{item["filename"]}</b> <span style="color:#94a3b8">({size_mb:.1f} MB)</span></div>', unsafe_allow_html=True)
        with col_dl_2:
            st.download_button(
                label="保存",
                data=item['data'],
                file_name=item['filename'],
                mime=item['mime'],
                key=f"dl_{item['filename']}",
                use_container_width=True
            )
        st.markdown("<hr style='margin: 0; opacity: 0.1;'>", unsafe_allow_html=True)
        
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("最初に戻る", use_container_width=True):
        st.session_state.stage = 'input'
        st.session_state.video_infos = []
        st.session_state.download_results = None
        st.rerun()
