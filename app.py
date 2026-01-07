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
st.set_page_config(page_title="Audio Studio Pro", layout="centered", initial_sidebar_state="expanded")

# --- Font Awesome & カスタムCSS (New Design) ---
st.markdown("""
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        /* ベースフォント */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap');
        html, body, [class*="css"] {
            font-family: 'Inter', sans-serif;
            color: #e0e0e0;
        }

        /* ヘッダーデザイン */
        .main-header {
            padding: 1rem 0;
            border-bottom: 1px solid #333;
            margin-bottom: 2rem;
        }
        .app-title {
            font-size: 2rem;
            font-weight: 700;
            background: linear-gradient(90deg, #4facfe 0%, #00f2fe 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            display: inline-block;
        }
        .app-subtitle {
            font-size: 0.9rem;
            color: #888;
            margin-top: 0.2rem;
        }

        /* カードコンテナ */
        .info-card {
            background-color: #1a1b1e;
            border: 1px solid #2d2e33;
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 16px;
            transition: all 0.3s ease;
        }
        .info-card:hover {
            border-color: #4facfe;
            box-shadow: 0 4px 12px rgba(0,0,0,0.2);
        }

        /* 入力エリア */
        .stTextArea textarea {
            background-color: #121315;
            border: 1px solid #333;
            border-radius: 8px;
            color: #fff;
        }
        
        /* ボタンカスタマイズ */
        button[kind="primary"] {
            background: linear-gradient(90deg, #2c3e50, #4ca1af);
            border: none;
            transition: 0.3s;
        }
        button[kind="primary"]:hover {
            opacity: 0.9;
        }
        button[kind="secondary"] {
            border-color: #ff5252 !important;
            color: #ff5252 !important;
        }
        button[kind="secondary"]:hover {
            background-color: rgba(255, 82, 82, 0.1) !important;
        }

        /* アイコン */
        .fa-icon {
            width: 20px;
            text-align: center;
            margin-right: 8px;
        }
        .section-header {
            font-size: 1.1rem;
            font-weight: 600;
            margin: 20px 0 10px 0;
            display: flex;
            align-items: center;
        }
        .status-text {
            font-size: 0.9rem;
            color: #aaa;
        }
    </style>
""", unsafe_allow_html=True)

# ── 内部関数: ユーティリティ ──
def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()

def create_cookie_file(tmp_dir):
    if "general" in st.secrets and "YOUTUBE_COOKIES" in st.secrets["general"]:
        cookie_content = st.secrets["general"]["YOUTUBE_COOKIES"]
        path = os.path.join(tmp_dir, "cookies.txt")
        with open(path, "w", encoding="utf-8") as f: f.write(cookie_content)
        return path
    return None

def remove_item(index):
    if 0 <= index < len(st.session_state.video_infos):
        del st.session_state.video_infos[index]

# ── サイドバー & モード選択 ──
with st.sidebar:
    st.markdown('<div class="app-title" style="font-size:1.5rem;">Audio Studio</div>', unsafe_allow_html=True)
    st.markdown("---")
    
    mode = st.radio(
        "モード選択",
        ("YouTube ダウンロード", "MP3 タグ編集"),
        index=0 if st.session_state.get('mode', 'youtube') == 'youtube' else 1,
        format_func=lambda x: f" {x}" 
    )
    
    # モード切り替え時のリセット処理
    current_mode_key = 'youtube' if mode == "YouTube ダウンロード" else 'local'
    if st.session_state.get('app_mode') != current_mode_key:
        st.session_state.app_mode = current_mode_key
        st.session_state.video_infos = []
        st.session_state.stage = 'input'
        st.rerun()

    st.markdown("---")
    st.markdown('<div class="section-header"><i class="fa-solid fa-gear fa-icon"></i> 出力設定</div>', unsafe_allow_html=True)
    
    quality_val = '192'
    if current_mode_key == 'youtube':
        audio_quality_map = {'最高 (Best)': '0', '高音質 (192k)': '192', '標準 (128k)': '128'}
        q_label = st.selectbox("ビットレート", list(audio_quality_map.keys()))
        quality_val = audio_quality_map[q_label]
    else:
        st.caption("※ 元の音質を維持または再エンコードします")

    st.markdown("<br>", unsafe_allow_html=True)
    embed_thumb = st.checkbox("サムネイル埋め込み", value=True)
    add_metadata = st.checkbox("メタデータ書き込み", value=True)

# ── ヘッダー表示 ──
st.markdown('<div class="main-header">', unsafe_allow_html=True)
if st.session_state.app_mode == 'youtube':
    st.markdown('<div class="app-title">YouTube Downloader</div>', unsafe_allow_html=True)
    st.markdown('<div class="app-subtitle">動画から高音質MP3を抽出し、メタデータを編集して保存します</div>', unsafe_allow_html=True)
else:
    st.markdown('<div class="app-title">MP3 Tag Editor</div>', unsafe_allow_html=True)
    st.markdown('<div class="app-subtitle">手持ちのMP3ファイルのメタデータとカバー画像を編集します</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

# ── ロジック: 情報取得 (YouTube) ──
def get_youtube_info(urls):
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
                        'source_type': 'youtube',
                        'url': url,
                        'original_title': title,
                        'thumbnail_url': info.get('thumbnail'),
                        'duration': info.get('duration'),
                        # 編集用フィールド
                        'custom_filename': sanitize_filename(title),
                        'custom_title': title,
                        'custom_artist': uploader,
                        'custom_album': title,
                        'thumb_mode': 'youtube', # youtube or upload
                        'custom_thumb_bytes': None
                    })
                except Exception as e:
                    st.error(f"取得エラー: {url}")
    return info_list

# ── ロジック: 情報取得 (Local) ──
def get_local_files_info(uploaded_files):
    info_list = []
    for f in uploaded_files:
        fname = os.path.splitext(f.name)[0]
        info_list.append({
            'source_type': 'local',
            'file_bytes': f.getvalue(),
            'original_filename': f.name,
            'thumbnail_url': None, # ローカルの既存アートワーク取得は複雑なため省略（アップロード推奨）
            'duration': None,
            # 編集用フィールド
            'custom_filename': sanitize_filename(fname),
            'custom_title': fname,
            'custom_artist': 'Unknown Artist',
            'custom_album': 'Unknown Album',
            'thumb_mode': 'upload', # localの場合はデフォルトでアップロードモード
            'custom_thumb_bytes': None
        })
    return info_list

# ── ロジック: ダウンロード・変換処理 ──
def process_audio(info_list):
    results = []
    zip_buffer = None
    
    # プログレス表示
    progress_text = st.empty()
    progress_bar = st.progress(0)
    
    total = len(info_list)

    with tempfile.TemporaryDirectory() as tmp_dir:
        cookie_path = create_cookie_file(tmp_dir)
        
        for idx, info in enumerate(info_list):
            base_name = f"temp_{idx}"
            temp_input_path = os.path.join(tmp_dir, f"{base_name}_input.mp3")
            temp_cover_path = os.path.join(tmp_dir, f"{base_name}_cover.jpg")
            final_output_path = os.path.join(tmp_dir, f"{sanitize_filename(info['custom_filename'])}.mp3")

            progress_text.markdown(f"**処理中 ({idx+1}/{total})**: {info['custom_filename']}")

            # 1. ソースの確保 (YouTube DL or Local Write)
            try:
                if info['source_type'] == 'youtube':
                    ydl_opts = {
                        'outtmpl': os.path.join(tmp_dir, f"{base_name}_input.%(ext)s"),
                        'format': 'bestaudio/best',
                        'quiet': True,
                        'writethumbnail': True, # YouTubeのサムネ確保用
                        'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': quality_val}],
                    }
                    if cookie_path: ydl_opts['cookiefile'] = cookie_path
                    
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([info['url']])
                    
                    # yt-dlpはファイル名を変更する可能性があるため探索
                    found = False
                    for f in os.listdir(tmp_dir):
                        if f.startswith(f"{base_name}_input") and f.endswith(".mp3"):
                            os.rename(os.path.join(tmp_dir, f), temp_input_path)
                            found = True
                            break
                    if not found: raise Exception("Download failed")
                    
                else: # local
                    with open(temp_input_path, "wb") as f:
                        f.write(info['file_bytes'])

                # 2. カバー画像の準備
                has_cover = False
                
                # A: ユーザーアップロード画像
                if info.get('custom_thumb_bytes'):
                    with open(temp_cover_path, "wb") as f:
                        f.write(info['custom_thumb_bytes'])
                    has_cover = True
                
                # B: YouTubeサムネイル (YouTubeモードかつアップロードがない場合)
                elif info['source_type'] == 'youtube' and info['thumb_mode'] == 'youtube' and embed_thumb:
                    # yt-dlpがDLした画像を探す
                    for f in os.listdir(tmp_dir):
                        if f.startswith(f"{base_name}_input") and f.lower().endswith(('.jpg', '.webp', '.png')):
                            os.rename(os.path.join(tmp_dir, f), temp_cover_path)
                            has_cover = True
                            break

                # 3. FFmpegで合成 (メタデータ + 画像)
                cmd = ['ffmpeg', '-y', '-i', temp_input_path]
                
                if has_cover and embed_thumb:
                    cmd.extend(['-i', temp_cover_path])
                    cmd.extend(['-map', '0:a', '-map', '1:0'])
                    # ID3v2 規格準拠のカバー画像設定
                    cmd.extend(['-c:v', 'copy', '-id3v2_version', '3', '-metadata:s:v', 'title="Album cover"', '-metadata:s:v', 'comment="Cover (front)"'])
                else:
                    cmd.extend(['-map', '0:a'])
                
                cmd.extend(['-c:a', 'copy']) # 再エンコードなしでコピー（高速化・音質維持）

                if add_metadata:
                    cmd.extend([
                        '-metadata', f"title={info['custom_title']}",
                        '-metadata', f"artist={info['custom_artist']}",
                        '-metadata', f"album={info['custom_album']}",
                        '-metadata', 'genre=', # 既存ジャンルクリア（任意）
                    ])
                
                cmd.append(final_output_path)
                
                # 実行
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

                # 結果格納
                with open(final_output_path, "rb") as f:
                    results.append({
                        "filename": os.path.basename(final_output_path),
                        "data": f.read(),
                        "mime": "audio/mpeg"
                    })
                
                progress_bar.progress((idx + 1) / total)

            except Exception as e:
                st.error(f"Error processing {info['custom_filename']}: {e}")
                continue

    # ZIP作成
    if results:
        zip_io = io.BytesIO()
        with zipfile.ZipFile(zip_io, 'w', zipfile.ZIP_DEFLATED) as zf:
            for item in results:
                zf.writestr(item['filename'], item['data'])
        zip_buffer = zip_io.getvalue()
    
    progress_text.markdown('<i class="fa-solid fa-circle-check" style="color:#00e676"></i> 完了', unsafe_allow_html=True)
    time.sleep(1)
    return results, zip_buffer


# ── メインステート管理 ──
if 'stage' not in st.session_state: st.session_state.stage = 'input'
if 'video_infos' not in st.session_state: st.session_state.video_infos = []

# ==========================================
# STEP 1: 入力 (URL or File)
# ==========================================
if st.session_state.stage == 'input':
    
    if st.session_state.app_mode == 'youtube':
        st.markdown('<div class="section-header"><i class="fa-brands fa-youtube fa-icon"></i> YouTube URL</div>', unsafe_allow_html=True)
        url_input = st.text_area("URL", placeholder="https://www.youtube.com/watch?v=...", height=150, label_visibility="collapsed")
        
        if st.button("情報を解析する", type="primary", use_container_width=True):
            urls = [u.strip() for u in url_input.splitlines() if u.strip()]
            if urls:
                with st.spinner("URLを解析中..."):
                    infos = get_youtube_info(urls)
                    if infos:
                        st.session_state.video_infos = infos
                        st.session_state.stage = 'preview'
                        st.rerun()
            else:
                st.warning("URLを入力してください")
                
    else: # local mode
        st.markdown('<div class="section-header"><i class="fa-solid fa-file-audio fa-icon"></i> MP3ファイル選択</div>', unsafe_allow_html=True)
        uploaded_files = st.file_uploader("MP3ファイルをアップロード", type=['mp3'], accept_multiple_files=True)
        
        if uploaded_files:
            if st.button("編集へ進む", type="primary", use_container_width=True):
                infos = get_local_files_info(uploaded_files)
                st.session_state.video_infos = infos
                st.session_state.stage = 'preview'
                st.rerun()

# ==========================================
# STEP 2: プレビュー & 編集
# ==========================================
if st.session_state.stage == 'preview':
    st.markdown(f'<div class="section-header"><i class="fa-solid fa-pen-to-square fa-icon"></i> 編集 ({len(st.session_state.video_infos)}件)</div>', unsafe_allow_html=True)
    
    if not st.session_state.video_infos:
        st.info("対象ファイルがありません")
        if st.button("戻る"):
            st.session_state.stage = 'input'
            st.rerun()

    # 編集カードのループ
    current_infos = st.session_state.video_infos.copy()
    for idx, info in enumerate(current_infos):
        with st.container():
            st.markdown('<div class="info-card">', unsafe_allow_html=True)
            
            c1, c2, c3 = st.columns([1.2, 3, 0.3])
            
            # --- 左カラム: 画像 ---
            with c1:
                st.caption("アートワーク")
                
                # モード選択 (YouTubeモード時のみ選択可, ローカルはUploadのみ)
                if info['source_type'] == 'youtube':
                    t_mode = st.radio("", ["YouTube", "Upload"], key=f"tm_{idx}", horizontal=True, label_visibility="collapsed")
                    st.session_state.video_infos[idx]['thumb_mode'] = 'youtube' if t_mode == 'YouTube' else 'upload'
                else:
                    st.caption("Upload Mode")
                
                # 画像表示・アップロード
                current_mode = st.session_state.video_infos[idx]['thumb_mode']
                
                if current_mode == 'youtube':
                    if info.get('thumbnail_url'):
                        st.image(info['thumbnail_url'], use_container_width=True)
                    else:
                        st.markdown('<div style="background:#333;height:100px;display:flex;align-items:center;justify-content:center;">No Image</div>', unsafe_allow_html=True)
                else:
                    # Upload
                    up_img = st.file_uploader("画像", type=['jpg','png','webp'], key=f"up_{idx}", label_visibility="collapsed")
                    if up_img:
                        st.session_state.video_infos[idx]['custom_thumb_bytes'] = up_img.getvalue()
                        st.image(up_img, use_container_width=True)
                    elif info.get('custom_thumb_bytes'):
                        st.image(info['custom_thumb_bytes'], use_container_width=True)
                    else:
                        st.markdown('<div style="border:1px dashed #555; height:100px; display:flex; align-items:center; justify-content:center; color:#555;"><i class="fa-solid fa-image"></i></div>', unsafe_allow_html=True)

            # --- 中央カラム: メタデータ ---
            with c2:
                # ファイル名
                st.text_input("ファイル名", value=info['custom_filename'], key=f"fn_{idx}", 
                              on_change=lambda i=idx, k=f"fn_{idx}": st.session_state.video_infos[i].update({'custom_filename': st.session_state[k]}))
                
                st.markdown("<div style='margin:10px 0;'></div>", unsafe_allow_html=True)
                
                mc1, mc2 = st.columns(2)
                with mc1:
                    st.text_input("タイトル", value=info['custom_title'], key=f"tt_{idx}",
                                  on_change=lambda i=idx, k=f"tt_{idx}": st.session_state.video_infos[i].update({'custom_title': st.session_state[k]}))
                    st.text_input("アーティスト", value=info['custom_artist'], key=f"ar_{idx}",
                                  on_change=lambda i=idx, k=f"ar_{idx}": st.session_state.video_infos[i].update({'custom_artist': st.session_state[k]}))
                with mc2:
                    st.text_input("アルバム", value=info['custom_album'], key=f"al_{idx}",
                                  on_change=lambda i=idx, k=f"al_{idx}": st.session_state.video_infos[i].update({'custom_album': st.session_state[k]}))

            # --- 右カラム: 削除 ---
            with c3:
                st.write("")
                if st.button("🗑", key=f"del_{idx}", type="secondary"):
                    remove_item(idx)
                    st.rerun()

            st.markdown('</div>', unsafe_allow_html=True)

    # アクションボタン
    st.markdown("---")
    ac1, ac2 = st.columns(2)
    with ac1:
        if st.button("最初に戻る", use_container_width=True):
            st.session_state.stage = 'input'
            st.rerun()
    with ac2:
        btn_label = "ダウンロード処理開始" if st.session_state.app_mode == 'youtube' else "編集を適用して保存"
        if st.button(btn_label, type="primary", use_container_width=True):
            st.session_state.stage = 'processing'
            st.rerun()

# ==========================================
# STEP 3: 処理実行
# ==========================================
if st.session_state.stage == 'processing':
    results, zip_data = process_audio(st.session_state.video_infos)
    
    if results:
        st.session_state.final_results = results
        st.session_state.final_zip = zip_data
        st.session_state.stage = 'finished'
        st.rerun()
    else:
        st.error("処理に失敗しました")
        if st.button("戻る"):
            st.session_state.stage = 'preview'
            st.rerun()

# ==========================================
# STEP 4: 完了 & ダウンロード
# ==========================================
if st.session_state.stage == 'finished':
    st.markdown('<div class="section-header"><i class="fa-solid fa-download fa-icon"></i> 保存</div>', unsafe_allow_html=True)
    
    # ZIPダウンロード
    if st.session_state.final_zip:
        st.download_button(
            label="まとめてZIPでダウンロード",
            data=st.session_state.final_zip,
            file_name="audio_files.zip",
            mime="application/zip",
            use_container_width=True,
            type="primary"
        )
    
    st.markdown("---")
    
    # 個別ダウンロード
    for item in st.session_state.final_results:
        cols = st.columns([3, 1])
        with cols[0]:
            st.markdown(f'<div style="padding:10px;"><i class="fa-solid fa-music fa-icon"></i> {item["filename"]}</div>', unsafe_allow_html=True)
        with cols[1]:
            st.download_button(
                label="保存",
                data=item['data'],
                file_name=item['filename'],
                mime=item['mime'],
                key=f"dl_fin_{item['filename']}",
                use_container_width=True
            )
        st.markdown("<hr style='margin:0; border-color:#333;'>", unsafe_allow_html=True)

    if st.button("新しい作業を開始", use_container_width=True):
        st.session_state.stage = 'input'
        st.session_state.video_infos = []
        st.session_state.final_results = None
        st.rerun()
