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
# 絵文字アイコンは使用せず、タイトルのみ設定
st.set_page_config(page_title="Audio Downloader Pro", layout="centered")

# --- Font Awesome & カスタムCSS (ホワイトベース) ---
st.markdown("""
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        /* --- 全体のフォントとベースカラー --- */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
        
        html, body, [class*="css"] {
            font-family: 'Inter', sans-serif;
            color: #1F2937; /* ダークグレー */
        }
        
        /* Streamlitのデフォルト背景を強制的に白にする */
        .stApp {
            background-color: #FFFFFF;
        }

        /* --- タイトルエリア --- */
        .main-title {
            font-size: 2.2rem;
            font-weight: 800;
            color: #111827;
            margin-bottom: 0.2rem;
            display: flex;
            align-items: center;
            gap: 12px;
        }
        
        .main-title i {
            color: #2563EB; /* プライマリーブルー */
        }

        .sub-text {
            color: #6B7280; /* 薄いグレー */
            font-size: 0.95rem;
            margin-bottom: 2.5rem;
            margin-left: 4px;
        }

        /* --- 編集カード (ホワイトデザイン) --- */
        .edit-card {
            background-color: #FFFFFF;
            border: 1px solid #E5E7EB; /* 薄いボーダー */
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 24px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
            transition: box-shadow 0.2s;
        }
        
        .edit-card:hover {
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.05), 0 4px 6px -2px rgba(0, 0, 0, 0.02);
        }

        /* --- カード内のラベル --- */
        .card-label {
            font-size: 0.8rem;
            font-weight: 600;
            color: #6B7280;
            margin-bottom: 4px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        /* --- ボタン類 --- */
        /* セカンダリボタン（削除など） */
        button[kind="secondary"] {
            border-color: #E5E7EB !important;
            color: #4B5563 !important;
            background-color: #FFFFFF !important;
        }
        button[kind="secondary"]:hover {
            border-color: #EF4444 !important; /* 赤 */
            color: #EF4444 !important;
            background-color: #FEF2F2 !important;
        }

        /* --- アイコン --- */
        .icon-spacing {
            margin-right: 8px;
        }
        
        /* プログレスバーの色調整 */
        .stProgress > div > div > div > div {
            background-color: #2563EB;
        }
    </style>
""", unsafe_allow_html=True)

# --- ヘッダー部分 ---
st.markdown("""
    <div class="main-title">
        <i class="fa-solid fa-music"></i>
        <span>Audio Downloader Pro</span>
    </div>
    <div class="sub-text">MP3ダウンロード & メタデータ編集ツール</div>
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
    st.markdown('### <i class="fa-solid fa-sliders icon-spacing"></i>設定', unsafe_allow_html=True)
    
    st.markdown('**<i class="fa-solid fa-file-audio icon-spacing"></i>音質設定 (MP3)**', unsafe_allow_html=True)
    audio_quality_map = {
        '最高 (Best)': '0', 
        '高音質 (192kbps)': '192', 
        '標準 (128kbps)': '128'
    }
    quality_label = st.selectbox("ビットレート", list(audio_quality_map.keys()))
    quality_val = audio_quality_map[quality_label]
    
    st.markdown('---')
    st.caption("オプション")
    embed_thumb = st.checkbox("アートワーク埋め込み", value=True)
    add_metadata = st.checkbox("メタデータ(タグ)付与", value=True)

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
            self.status_placeholder.markdown(f'<i class="fa-solid fa-spinner fa-spin icon-spacing"></i>ダウンロード中... {d["_percent_str"]} (速度: {speed})', unsafe_allow_html=True)
            
        elif d['status'] == 'finished':
            self.progress_bar.progress(1.0)
            self.status_placeholder.markdown('<i class="fa-solid fa-compact-disc fa-spin icon-spacing"></i>変換とタグ付け処理中...', unsafe_allow_html=True)

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
                    title = info.get('title', 'Unknown')
                    uploader = info.get('uploader', 'Unknown')
                    info_list.append({
                        'title': title,
                        'uploader': uploader,
                        'thumbnail': info.get('thumbnail'),
                        'duration': info.get('duration'),
                        'url': url,
                        # 以下編集用フィールド
                        'custom_filename': sanitize_filename(title), 
                        'custom_title': title,           # メタデータ用タイトル
                        'custom_artist': uploader,       # メタデータ用アーティスト
                        'custom_album': title,           # メタデータ用アルバム（初期値はタイトル）
                        'thumb_mode': 'youtube',         # 'youtube' or 'upload'
                        'custom_thumb_bytes': None       # アップロードされた画像のバイナリ
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
            base_filename = f"video_{idx}" # 一時ファイル名
            final_filename = sanitize_filename(info['custom_filename'])
            
            # メタデータ情報の取得
            m_title = info['custom_title']
            m_artist = info['custom_artist']
            m_album = info['custom_album']

            main_status.markdown(f'<i class="fa-solid fa-gear fa-spin icon-spacing"></i>処理中 ({idx+1}/{total_videos}): **{final_filename}**', unsafe_allow_html=True)
            
            single_status = st.empty()
            single_bar = st.progress(0)
            hooks = ProgressHooks(single_status, single_bar)

            # --- yt_dlp設定 ---
            ydl_opts = {
                'outtmpl': f'{tmp_dir}/{base_filename}.%(ext)s',
                'quiet': True,
                'progress_hooks': [hooks.hook],
                'writethumbnail': True, 
                'skip_download': False,
            }
            if cookie_path: ydl_opts['cookiefile'] = cookie_path

            # 音声変換設定
            postprocessors = [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3'}]
            if quality_val != '0':
                postprocessors[0]['preferredquality'] = quality_val
            
            ydl_opts.update({'format': 'bestaudio/best', 'postprocessors': postprocessors})

            try:
                # 1. 音声とYoutubeサムネイルのダウンロード
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                
                mp3_path = f"{tmp_dir}/{base_filename}.mp3"
                if not os.path.exists(mp3_path):
                    raise Exception("MP3 conversion failed")

                # サムネイル画像の準備
                cover_image_path = None
                
                # A: カスタム画像がアップロードされている場合
                if info['thumb_mode'] == 'upload' and info['custom_thumb_bytes']:
                    cover_image_path = f"{tmp_dir}/{base_filename}_custom_cover.jpg"
                    with open(cover_image_path, "wb") as f:
                        f.write(info['custom_thumb_bytes'])
                
                # B: YouTubeのサムネイルを使う場合
                elif embed_thumb:
                    for f in os.listdir(tmp_dir):
                        if f.startswith(base_filename) and f.lower().endswith(('.jpg', '.jpeg', '.webp', '.png')) and not f.endswith('.mp3'):
                            cover_image_path = os.path.join(tmp_dir, f)
                            break
                
                # 2. FFmpegを使ってメタデータと画像を埋め込み
                output_mp3_path = f"{tmp_dir}/{final_filename}.mp3"
                
                ffmpeg_cmd = [
                    'ffmpeg', '-y', 
                    '-i', mp3_path,
                ]

                # カバー画像埋め込み
                if cover_image_path and embed_thumb:
                    ffmpeg_cmd.extend(['-i', cover_image_path])
                    ffmpeg_cmd.extend(['-map', '0:0', '-map', '1:0'])
                    ffmpeg_cmd.extend(['-c:v', 'copy', '-id3v2_version', '3', '-metadata:s:v', 'title="Album cover"', '-metadata:s:v', 'comment="Cover (front)"'])
                else:
                    ffmpeg_cmd.extend(['-map', '0:0'])
                
                ffmpeg_cmd.extend(['-c:a', 'copy'])

                # メタデータ付与
                if add_metadata:
                    ffmpeg_cmd.extend([
                        '-metadata', f'title={m_title}',
                        '-metadata', f'artist={m_artist}',
                        '-metadata', f'album={m_album}'
                    ])
                
                ffmpeg_cmd.append(output_mp3_path)
                
                # FFmpeg実行
                subprocess.run(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                
                # 中間ファイルのクリーンアップ
                if os.path.exists(mp3_path): os.remove(mp3_path)
                
                single_status.markdown('<i class="fa-solid fa-check icon-spacing" style="color:#10B981"></i>完了', unsafe_allow_html=True)

            except Exception as e:
                single_status.error(f"エラー: {e}")
                print(e)
                continue
            
            main_progress.progress((idx + 1) / total_videos)

        # ファイル回収
        files = [f for f in os.listdir(tmp_dir) if f.endswith(".mp3") and not f.startswith("video_")]
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
            
        main_status.markdown('<div style="padding:10px; background-color:#ECFDF5; border-radius:8px; color:#065F46; border:1px solid #10B981;"><i class="fa-solid fa-check-circle icon-spacing"></i>すべての処理が完了しました</div>', unsafe_allow_html=True)
        return downloaded_data, zip_buffer


# --- メインUI ---
if 'stage' not in st.session_state:
    st.session_state.stage = 'input'
if 'video_infos' not in st.session_state:
    st.session_state.video_infos = []

# ステップ1: URL入力
if st.session_state.stage == 'input':
    st.markdown('### <i class="fa-solid fa-link icon-spacing"></i>1. URLを入力', unsafe_allow_html=True)
    url_input = st.text_area(
        label="URL",
        placeholder="https://www.youtube.com/watch?v=...\nhttps://youtu.be/...",
        height=150,
        label_visibility="collapsed"
    )

    if st.button("情報を取得する", type="primary", use_container_width=True):
        urls = [u.strip() for u in url_input.splitlines() if u.strip()]
        if urls:
            with st.spinner("解析中..."):
                infos = get_video_info(urls)
                if infos:
                    st.session_state.video_infos = infos
                    st.session_state.stage = 'preview'
                    st.rerun()
        else:
            st.warning("URLを入力してください")

# ステップ2: プレビュー & 編集
if st.session_state.stage == 'preview':
    st.markdown(f'### <i class="fa-solid fa-pen-to-square icon-spacing"></i>2. 編集 ({len(st.session_state.video_infos)}件)', unsafe_allow_html=True)
    
    if len(st.session_state.video_infos) == 0:
        st.info("リストが空です。URLを入力し直してください。")
        if st.button("戻る"):
            st.session_state.stage = 'input'
            st.rerun()
    
    current_infos = st.session_state.video_infos.copy()
    
    for idx, info in enumerate(current_infos):
        # 編集カード
        st.markdown('<div class="edit-card">', unsafe_allow_html=True)
        
        # レイアウト: 画像(左) | 情報入力(右) | 削除(端)
        col_img, col_edit = st.columns([1.2, 3])
        
        with col_img:
            st.markdown('<div class="card-label">Cover Art</div>', unsafe_allow_html=True)
            
            # 画像モード切替
            thumb_mode = st.radio(
                "画像ソース", 
                ["YouTube", "Upload"], 
                key=f"thumb_mode_{idx}",
                label_visibility="collapsed",
                horizontal=True
            )
            st.session_state.video_infos[idx]['thumb_mode'] = 'youtube' if thumb_mode == "YouTube" else 'upload'

            if thumb_mode == "YouTube":
                if info['thumbnail']:
                    st.image(info['thumbnail'], use_container_width=True)
                else:
                    st.markdown('<div style="background:#f3f4f6; height:150px; display:flex; align-items:center; justify-content:center; border-radius:8px; color:#9ca3af;"><i class="fa-solid fa-image"></i></div>', unsafe_allow_html=True)
            else:
                uploaded_file = st.file_uploader("画像選択", type=['jpg', 'png', 'webp'], key=f"uploader_{idx}", label_visibility="collapsed")
                if uploaded_file:
                    st.session_state.video_infos[idx]['custom_thumb_bytes'] = uploaded_file.getvalue()
                    st.image(uploaded_file, caption="New Cover", use_container_width=True)
                elif info.get('custom_thumb_bytes'):
                    st.image(info['custom_thumb_bytes'], caption="Uploaded", use_container_width=True)
                else:
                    st.markdown('<div style="background:#f3f4f6; height:150px; display:flex; align-items:center; justify-content:center; border-radius:8px; color:#9ca3af; font-size:0.8rem;">ドラッグ&ドロップ</div>', unsafe_allow_html=True)

        with col_edit:
            # 1行目: ファイル名 と 削除ボタン
            r1c1, r1c2 = st.columns([5, 1])
            with r1c1:
                st.markdown('<div class="card-label">Filename (MP3)</div>', unsafe_allow_html=True)
                new_filename = st.text_input(
                    "Filename", 
                    value=info['custom_filename'], 
                    key=f"fname_{idx}",
                    label_visibility="collapsed"
                )
                st.session_state.video_infos[idx]['custom_filename'] = new_filename
            with r1c2:
                st.markdown('<div class="card-label">&nbsp;</div>', unsafe_allow_html=True)
                if st.button("×", key=f"del_{idx}", help="リストから削除", type="secondary"):
                    remove_video(idx)
                    st.rerun()

            st.markdown("<div style='margin-bottom:12px'></div>", unsafe_allow_html=True)

            # 2行目: メタデータ（タイトル・アーティスト・アルバム）
            st.markdown('<div class="card-label"><i class="fa-solid fa-tags icon-spacing"></i>ID3 Tags</div>', unsafe_allow_html=True)
            
            mc1, mc2 = st.columns(2)
            with mc1:
                new_title = st.text_input("タイトル", value=info['custom_title'], key=f"title_{idx}", placeholder="Title")
                new_artist = st.text_input("アーティスト", value=info['custom_artist'], key=f"artist_{idx}", placeholder="Artist")
            with mc2:
                new_album = st.text_input("アルバム", value=info['custom_album'], key=f"album_{idx}", placeholder="Album")
            
            # データ更新
            st.session_state.video_infos[idx]['custom_title'] = new_title
            st.session_state.video_infos[idx]['custom_artist'] = new_artist
            st.session_state.video_infos[idx]['custom_album'] = new_album

        st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown("---")
    c1, c2 = st.columns([1, 2])
    with c1:
        if st.button("← URL入力に戻る", use_container_width=True):
            st.session_state.stage = 'input'
            st.rerun()
    with c2:
        if st.button("変換・ダウンロード開始", type="primary", use_container_width=True):
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
        st.error("処理可能なファイルがありませんでした。")
        if st.button("戻る"):
            st.session_state.stage = 'preview'
            st.rerun()

# ステップ4: 完了画面
if st.session_state.stage == 'finished':
    st.markdown('### <i class="fa-solid fa-download icon-spacing"></i>3. 保存', unsafe_allow_html=True)
    
    if st.session_state.zip_data:
        st.markdown("""
        <div style="background-color:#F3F4F6; padding:15px; border-radius:8px; margin-bottom:20px; border:1px solid #E5E7EB;">
            <div style="font-weight:600; margin-bottom:5px;">一括ダウンロード</div>
            <div style="font-size:0.9rem; color:#6B7280;">すべてのファイルをZIP形式で保存します。</div>
        </div>
        """, unsafe_allow_html=True)
        st.download_button(
            label="ZIPをダウンロード",
            data=st.session_state.zip_data,
            file_name="audio_files.zip",
            mime="application/zip",
            use_container_width=True,
            type="primary"
        )

    st.markdown("#### <i class="fa-solid fa-list icon-spacing"></i>個別ファイル", unsafe_allow_html=True)
    for item in st.session_state.download_results:
        size_mb = len(item['data']) / (1024 * 1024)
        
        with st.container():
            col_dl_1, col_dl_2 = st.columns([3, 1])
            with col_dl_1:
                st.markdown(f"""
                <div style="display:flex; align-items:center; height:100%;">
                    <i class="fa-solid fa-music" style="color:#9CA3AF; margin-right:10px;"></i>
                    <span style="font-weight:600;">{item["filename"]}</span>
                    <span style="color:#9CA3AF; font-size:0.8rem; margin-left:10px;">{size_mb:.1f} MB</span>
                </div>
                """, unsafe_allow_html=True)
            with col_dl_2:
                st.download_button(
                    label="保存",
                    data=item['data'],
                    file_name=item['filename'],
                    mime=item['mime'],
                    key=f"dl_{item['filename']}",
                    use_container_width=True
                )
            st.markdown("<hr style='margin: 8px 0; border-top:1px solid #F3F4F6;'>", unsafe_allow_html=True)
        
    if st.button("ホームに戻る"):
        st.session_state.stage = 'input'
        st.session_state.video_infos = []
        st.session_state.download_results = None
        st.rerun()
