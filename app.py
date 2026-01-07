import streamlit as st
import yt_dlp
import os
import tempfile
import zipfile
import io
import re

# --- ページ設定 ---
st.set_page_config(page_title="Audio Downloader Pro", layout="centered")

# --- Font Awesome & カスタムCSS (モダンデザイン定義) ---
st.markdown("""
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        /* 全体のフォント設定 */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;800&display=swap');
        
        html, body, [class*="css"] {
            font-family: 'Inter', sans-serif;
            color: #e0e0e0;
        }

        /* ヘッダーのグラデーションテキスト */
        .main-header {
            text-align: center;
            padding: 2rem 0 1rem 0;
        }
        .main-title {
            font-size: 3rem;
            font-weight: 800;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin: 0;
            line-height: 1.2;
        }
        .sub-text {
            color: #9ca3af;
            font-size: 1rem;
            margin-top: 0.5rem;
            font-weight: 500;
        }

        /* カードデザイン (動画リスト用) */
        .video-card {
            background-color: #1f2937;
            border: 1px solid #374151;
            border-radius: 16px;
            padding: 20px;
            margin-bottom: 24px;
            transition: all 0.3s ease;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
        }
        .video-card:hover {
            border-color: #764ba2;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
        }

        /* カスタム通知ボックス */
        .custom-alert {
            padding: 1rem;
            border-radius: 8px;
            margin-bottom: 1rem;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .alert-info { background-color: #1e3a8a; border: 1px solid #1d4ed8; color: #dbeafe; }
        .alert-success { background-color: #064e3b; border: 1px solid #059669; color: #d1fae5; }
        .alert-error { background-color: #7f1d1d; border: 1px solid #dc2626; color: #fee2e2; }

        /* ボタンのスタイル調整 */
        button[kind="primary"] {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
            border: none !important;
            font-weight: 600 !important;
            transition: opacity 0.2s;
        }
        button[kind="primary"]:hover {
            opacity: 0.9;
        }
        
        /* 削除ボタン */
        .delete-btn-wrapper button {
            border-color: #ef4444 !important;
            color: #ef4444 !important;
        }
        .delete-btn-wrapper button:hover {
            background-color: #ef4444 !important;
            color: white !important;
        }

        /* アイコンのスタイル */
        .icon-box {
            display: inline-flex;
            justify-content: center;
            align-items: center;
            width: 24px;
        }
    </style>
""", unsafe_allow_html=True)

# --- ユーティリティ関数: カスタム通知 ---
def custom_info(msg):
    st.markdown(f'<div class="custom-alert alert-info"><i class="fa-solid fa-circle-info"></i><span>{msg}</span></div>', unsafe_allow_html=True)

def custom_success(msg):
    st.markdown(f'<div class="custom-alert alert-success"><i class="fa-solid fa-circle-check"></i><span>{msg}</span></div>', unsafe_allow_html=True)

def custom_error(msg):
    st.markdown(f'<div class="custom-alert alert-error"><i class="fa-solid fa-triangle-exclamation"></i><span>{msg}</span></div>', unsafe_allow_html=True)

# --- ヘッダー部分 ---
st.markdown("""
    <div class="main-header">
        <div class="main-title"><i class="fa-solid fa-wave-square"></i> Audio Downloader Pro</div>
        <div class="sub-text">URLから音声を抽出し、タグを編集してダウンロード</div>
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
    st.markdown('### <i class="fa-solid fa-gear icon-box"></i> 設定', unsafe_allow_html=True)
    
    st.markdown('**<i class="fa-solid fa-sliders icon-box"></i> 音質設定**', unsafe_allow_html=True)
    audio_quality_map = {
        '最高 (Best)': '0', 
        '高音質 (192kbps)': '192', 
        '標準 (128kbps)': '128'
    }
    quality_label = st.selectbox("ビットレート", list(audio_quality_map.keys()), label_visibility="collapsed")
    quality_val = audio_quality_map[quality_label]
    
    st.markdown("---")
    st.markdown('**<i class="fa-solid fa-tags icon-box"></i> メタデータ**', unsafe_allow_html=True)
    embed_thumb = st.toggle("アートワーク埋め込み", value=True)
    add_metadata = st.toggle("タグ情報の付与", value=True)
    
    st.markdown("""
        <div style="margin-top: 2rem; font-size: 0.8rem; color: #666;">
            <i class="fa-regular fa-copyright"></i> Audio Downloader Pro<br>
            v2.0 Modern Edition
        </div>
    """, unsafe_allow_html=True)

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
            self.status_placeholder.markdown(f'<span style="color:#667eea"><i class="fa-solid fa-circle-down fa-bounce"></i></span> ダウンロード中... {d["_percent_str"]} (速度: {speed})', unsafe_allow_html=True)
            
        elif d['status'] == 'finished':
            self.progress_bar.progress(1.0)
            self.status_placeholder.markdown('<span style="color:#764ba2"><i class="fa-solid fa-compact-disc fa-spin"></i></span> 変換処理中...', unsafe_allow_html=True)

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
                    custom_error(f"Error processing URL: {url}<br><small>{e}</small>")
    return info_list

def process_download(info_list):
    downloaded_data = []
    zip_buffer = None
    
    # 修正箇所: ダブルクォーテーション内でのHTML属性の干渉を避けるため、外側をシングルクォーテーションに変更
    st.markdown('### <i class="fa-solid fa-terminal"></i> 処理状況', unsafe_allow_html=True)
    main_progress = st.progress(0)
    main_status = st.empty()
    total_videos = len(info_list)

    with tempfile.TemporaryDirectory() as tmp_dir:
        cookie_path = create_cookie_file(tmp_dir)
        for idx, info in enumerate(info_list):
            url = info['url']
            final_filename = sanitize_filename(info['custom_filename'])
            
            main_status.markdown(f'**[{idx+1}/{total_videos}]** {final_filename} を処理中...')
            
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

            # 音声変換設定
            postprocessors = [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3'}]
            if quality_val != '0':
                postprocessors[0]['preferredquality'] = quality_val
            
            if add_metadata:
                postprocessors.append({'key': 'FFmpegMetadata', 'add_metadata': True})
            
            # サムネイル埋め込み設定
            if embed_thumb:
                ydl_opts['writethumbnail'] = True
                postprocessors.append({'key': 'EmbedThumbnail'})
            
            ydl_opts.update({'format': 'bestaudio/best', 'postprocessors': postprocessors})

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                single_status.markdown('<span style="color:#059669"><i class="fa-solid fa-check"></i> 完了</span>', unsafe_allow_html=True)
            except Exception as e:
                single_status.markdown(f'<span style="color:#dc2626"><i class="fa-solid fa-xmark"></i> 失敗: {e}</span>', unsafe_allow_html=True)
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
            
        main_status.markdown('<span style="color:#667eea; font-weight:bold;"><i class="fa-solid fa-flag-checkered"></i> すべての処理が完了しました</span>', unsafe_allow_html=True)
        return downloaded_data, zip_buffer


# --- メインUI ---
if 'stage' not in st.session_state:
    st.session_state.stage = 'input'
if 'video_infos' not in st.session_state:
    st.session_state.video_infos = []

# ステップ1: URL入力
if st.session_state.stage == 'input':
    st.markdown('#### <i class="fa-solid fa-link icon-box"></i> YouTube URLを入力', unsafe_allow_html=True)
    st.caption("複数のURLを入力する場合は改行してください。")
    
    url_input = st.text_area(
        label="URL",
        placeholder="https://www.youtube.com/watch?v=...\nhttps://youtu.be/...",
        height=150,
        label_visibility="collapsed"
    )

    col1, col2 = st.columns([2, 1])
    with col2:
        if st.button("解析を開始", type="primary", use_container_width=True):
            urls = [u.strip() for u in url_input.splitlines() if u.strip()]
            if urls:
                with st.spinner("メタデータを取得しています..."):
                    infos = get_video_info(urls)
                    if infos:
                        st.session_state.video_infos = infos
                        st.session_state.stage = 'preview'
                        st.rerun()
            else:
                custom_error("URLが入力されていません")

# ステップ2: プレビュー & 編集
if st.session_state.stage == 'preview':
    st.markdown(f'#### <i class="fa-solid fa-pen-to-square icon-box"></i> 編集と確認 <small>({len(st.session_state.video_infos)}件)</small>', unsafe_allow_html=True)
    
    if len(st.session_state.video_infos) == 0:
        custom_info("リストが空です。URLを入力し直してください。")
        if st.button("戻る"):
            st.session_state.stage = 'input'
            st.rerun()
    
    current_infos = st.session_state.video_infos.copy()
    
    for idx, info in enumerate(current_infos):
        # カード形式のコンテナ
        st.markdown('<div class="video-card">', unsafe_allow_html=True)
        
        c_thumb, c_detail, c_action = st.columns([1.5, 3, 0.5])
        
        with c_thumb:
            if info['thumbnail']:
                st.image(info['thumbnail'], use_container_width=True)
            else:
                st.markdown('<div style="height:80px; background:#111; border-radius:8px; display:flex; align-items:center; justify-content:center;"><i class="fa-solid fa-image" style="color:#333;"></i></div>', unsafe_allow_html=True)
            
            duration_m = info['duration'] // 60 if info['duration'] else 0
            duration_s = info['duration'] % 60 if info['duration'] else 0
            st.caption(f'<i class="fa-regular fa-clock"></i> {duration_m}:{duration_s:02d}', unsafe_allow_html=True)

        with c_detail:
            new_filename = st.text_input(
                "ファイル名", 
                value=info['custom_filename'], 
                key=f"fname_{idx}",
                label_visibility="collapsed",
                placeholder="ファイル名"
            )
            st.caption("ファイル名")

            new_artist = st.text_input(
                "アーティスト名", 
                value=info['custom_artist'], 
                key=f"artist_{idx}",
                label_visibility="collapsed",
                placeholder="アーティスト名"
            )
            st.caption("アーティスト / チャンネル名")
            
            st.session_state.video_infos[idx]['custom_filename'] = new_filename
            st.session_state.video_infos[idx]['custom_artist'] = new_artist

        with c_action:
            st.markdown('<div class="delete-btn-wrapper">', unsafe_allow_html=True)
            if st.button("✕", key=f"del_{idx}", help="削除"):
                remove_video(idx)
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)
    
    # アクションバー
    st.markdown("---")
    c1, c2 = st.columns([1, 2])
    with c1:
        if st.button("戻る", use_container_width=True):
            st.session_state.stage = 'input'
            st.rerun()
    with c2:
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
        custom_error("ダウンロード可能なファイルがありませんでした。")
        if st.button("戻る"):
            st.session_state.stage = 'preview'
            st.rerun()

# ステップ4: 完了画面
if st.session_state.stage == 'finished':
    custom_success("ダウンロードが完了しました！")
    
    # 修正箇所: 外側をシングルクォーテーションに変更
    st.markdown('#### <i class="fa-solid fa-box-archive icon-box"></i> 一括ダウンロード', unsafe_allow_html=True)
    if st.session_state.zip_data:
        st.download_button(
            label="ZIPでまとめて保存",
            data=st.session_state.zip_data,
            file_name="audio_archive.zip",
            mime="application/zip",
            use_container_width=True,
            type="primary",
            icon=":material/folder_zip:" # Streamlitの新しいIcon機能も併用
        )

    # 修正箇所: 外側をシングルクォーテーションに変更
    st.markdown('#### <i class="fa-solid fa-music icon-box"></i> 個別ファイル', unsafe_allow_html=True)
    for item in st.session_state.download_results:
        with st.container():
            st.markdown('<div class="video-card" style="padding: 15px; margin-bottom: 10px; display:flex; align-items:center; justify-content:space-between;">', unsafe_allow_html=True)
            
            size_mb = len(item['data']) / (1024 * 1024)
            col_name, col_btn = st.columns([3, 1.5])
            
            with col_name:
                st.markdown(f'**{item["filename"]}**')
                st.caption(f'{size_mb:.1f} MB')
            
            with col_btn:
                st.download_button(
                    label="保存",
                    data=item['data'],
                    file_name=item['filename'],
                    mime=item['mime'],
                    key=f"dl_{item['filename']}",
                    use_container_width=True
                )
            st.markdown('</div>', unsafe_allow_html=True)
        
    if st.button("ホームに戻る"):
        st.session_state.stage = 'input'
        st.session_state.video_infos = []
        st.session_state.download_results = None
        st.rerun()
