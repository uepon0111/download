import streamlit as st
import yt_dlp
import os
import tempfile
import time
import zipfile
import io
import re
from PIL import Image

# --- ページ設定 ---
# 絵文字アイコンを削除
st.set_page_config(page_title="Audio Downloader Pro", layout="centered")

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

        /* サブタイトル */
        .sub-text {
            color: #888;
            font-size: 1rem;
            margin-bottom: 2rem;
        }

        /* カードデザイン (コンテナ全体) */
        .edit-card {
            background-color: #1e1e1e;
            border: 1px solid #333;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        
        /* サムネイル画像 */
        .thumb-img {
            border-radius: 8px;
            width: 100%;
            object-fit: cover;
        }

        /* 削除ボタン（ゴミ箱）のスタイル調整 */
        button[kind="secondary"] {
            border-color: #ff4b4b !important;
            color: #ff4b4b !important;
        }
        button[kind="secondary"]:hover {
            background-color: #ff4b4b !important;
            color: white !important;
        }

        /* アイコンのスタイル */
        .icon-spacing {
            margin-right: 10px;
            color: #0072ff;
        }
        
        /* アップローダーの微調整 */
        .stFileUploader label {
            font-size: 0.8rem;
        }
    </style>
""", unsafe_allow_html=True)

# --- ヘッダー部分 ---
st.markdown('<div class="main-title"><i class="fa-solid fa-cloud-arrow-down icon-spacing"></i>Audio Downloader Pro</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-text">MP3一括ダウンロード・編集・メタデータ管理</div>', unsafe_allow_html=True)

# ── 内部関数: ファイル名サニタイズ ──
def sanitize_filename(name):
    """ファイル名に使えない文字を除去"""
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
    st.markdown('### <i class="fa-solid fa-sliders icon-spacing"></i> 詳細設定', unsafe_allow_html=True)
    
    # 形式はMP3固定
    format_type = 'mp3'
    
    # 音声用設定のみ表示
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
                        # 編集用フィールドの初期化
                        'custom_filename': sanitize_filename(title), 
                        'custom_title': title,
                        'custom_artist': uploader,
                        'custom_album': '',
                        'custom_cover_data': None  # アップロード画像のバイナリ
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
            final_filename = sanitize_filename(info['custom_filename'])
            
            # メタデータ情報の準備
            meta_title = info['custom_title']
            meta_artist = info['custom_artist']
            meta_album = info['custom_album']
            custom_cover_data = info.get('custom_cover_data')

            main_status.markdown(f'<i class="fa-solid fa-list-check icon-spacing"></i> 処理中 ({idx+1}/{total_videos}): **{final_filename}**', unsafe_allow_html=True)
            
            single_status = st.empty()
            single_bar = st.progress(0)
            hooks = ProgressHooks(single_status, single_bar)

            # --- カスタムサムネイルの上書きフック ---
            # ダウンロード完了直後(変換前)に、ダウンロードされたサムネイルをアップロード画像で置換する
            def replace_thumbnail_hook(d):
                if d['status'] == 'finished' and custom_cover_data:
                    # ダウンロードされたファイルのベース名 (拡張子なし)
                    base_filename = os.path.splitext(d['filename'])[0]
                    
                    # フォルダ内の関連画像ファイル(webp, jpg等)を探して削除
                    dir_path = os.path.dirname(d['filename'])
                    file_stem = os.path.basename(base_filename)
                    
                    for f in os.listdir(dir_path):
                        if f.startswith(file_stem) and f.lower().endswith(('.jpg', '.jpeg', '.webp', '.png')):
                            try:
                                os.remove(os.path.join(dir_path, f))
                            except:
                                pass

                    # 新しい画像をjpgとして保存 (EmbedThumbnailはjpgを優先的に拾う)
                    image_path = f"{base_filename}.jpg"
                    with open(image_path, "wb") as f:
                        f.write(custom_cover_data)

            # MP3出力設定
            ydl_opts = {
                'outtmpl': f'{tmp_dir}/{final_filename}.%(ext)s',
                'quiet': True,
                'progress_hooks': [hooks.hook, replace_thumbnail_hook],
                # メタデータの上書き設定 (ffmpeg引数を使用)
                'postprocessor_args': {
                    'ffmpeg': [
                        '-metadata', f'title={meta_title}',
                        '-metadata', f'artist={meta_artist}',
                        '-metadata', f'album={meta_album}'
                    ]
                }
            }
            if cookie_path: ydl_opts['cookiefile'] = cookie_path

            # 音声変換設定
            postprocessors = [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3'}]
            if quality_val != '0':
                postprocessors[0]['preferredquality'] = quality_val
            
            if add_metadata:
                postprocessors.append({
                    'key': 'FFmpegMetadata',
                    'add_metadata': True,
                })
            
            # サムネイル埋め込み設定
            if embed_thumb:
                ydl_opts['writethumbnail'] = True
                postprocessors.append({'key': 'EmbedThumbnail'})
            
            ydl_opts.update({'format': 'bestaudio/best', 'postprocessors': postprocessors})

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                single_status.markdown('<i class="fa-solid fa-circle-check" style="color:#00ff88"></i> 完了', unsafe_allow_html=True)
            except Exception as e:
                single_status.error(f"エラー: {e}")
                continue
            
            main_progress.progress((idx + 1) / total_videos)

        # ファイル回収 (MP3のみ)
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
            
        main_status.markdown('<i class="fa-solid fa-face-smile icon-spacing"></i> すべての処理が完了しました！', unsafe_allow_html=True)
        return downloaded_data, zip_buffer


# --- メインUI ---
if 'stage' not in st.session_state:
    st.session_state.stage = 'input'
if 'video_infos' not in st.session_state:
    st.session_state.video_infos = []

# ステップ1: URL入力
if st.session_state.stage == 'input':
    st.markdown('### <i class="fa-solid fa-link icon-spacing"></i> 1. URLを入力', unsafe_allow_html=True)
    url_input = st.text_area(
        label="URL入力",
        placeholder="https://www.youtube.com/watch?v=...\nhttps://youtu.be/...",
        height=150,
        label_visibility="collapsed"
    )

    if st.button("情報を解析する", type="primary", use_container_width=True):
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

# ステップ2: プレビュー & 編集
if st.session_state.stage == 'preview':
    st.markdown(f'### <i class="fa-solid fa-pen-to-square icon-spacing"></i> 2. 編集と確認 ({len(st.session_state.video_infos)}件)', unsafe_allow_html=True)
    
    if len(st.session_state.video_infos) == 0:
        st.info("リストが空です。URLを入力し直してください。")
        if st.button("戻る"):
            st.session_state.stage = 'input'
            st.rerun()
    
    current_infos = st.session_state.video_infos.copy()
    
    for idx, info in enumerate(current_infos):
        with st.container():
            st.markdown('<div class="edit-card">', unsafe_allow_html=True)
            
            col_img, col_edit, col_del = st.columns([1.5, 3, 0.5])
            
            with col_img:
                # カスタム画像があればそれを表示、なければYouTubeサムネ
                display_img = info['thumbnail']
                if info.get('custom_cover_data'):
                    display_img = info['custom_cover_data']
                
                if display_img:
                    st.image(display_img, use_container_width=True)
                else:
                    st.markdown('<div style="height:100px; background:#333; display:flex; align-items:center; justify-content:center; color:#666;">No Image</div>', unsafe_allow_html=True)
                
                # 画像アップローダー
                uploaded_file = st.file_uploader("カバー画像変更", type=['png', 'jpg', 'jpeg'], key=f"up_{idx}", label_visibility="visible")
                if uploaded_file is not None:
                    # 画像データを読み込んでセッションステートに保存
                    st.session_state.video_infos[idx]['custom_cover_data'] = uploaded_file.getvalue()
                    st.rerun()

                duration_m = info['duration'] // 60 if info['duration'] else 0
                duration_s = info['duration'] % 60 if info['duration'] else 0
                st.caption(f"長さ: {duration_m}:{duration_s:02d}")

            with col_edit:
                # --- 編集フィールド ---
                new_filename = st.text_input(
                    "ファイル名 (拡張子なし)", 
                    value=info['custom_filename'], 
                    key=f"fname_{idx}",
                    placeholder="ファイル名"
                )
                
                new_title = st.text_input(
                    "タイトル (曲名)", 
                    value=info['custom_title'], 
                    key=f"title_{idx}",
                    placeholder="タイトル"
                )

                new_artist = st.text_input(
                    "アーティスト", 
                    value=info['custom_artist'], 
                    key=f"artist_{idx}",
                    placeholder="アーティスト"
                )

                new_album = st.text_input(
                    "アルバム名", 
                    value=info['custom_album'], 
                    key=f"album_{idx}",
                    placeholder="アルバム"
                )
                
                # 変更を即時反映
                st.session_state.video_infos[idx]['custom_filename'] = new_filename
                st.session_state.video_infos[idx]['custom_title'] = new_title
                st.session_state.video_infos[idx]['custom_artist'] = new_artist
                st.session_state.video_infos[idx]['custom_album'] = new_album

            with col_del:
                st.markdown("<br>", unsafe_allow_html=True)
                # 絵文字ボタンをテキストに変更
                if st.button("削除", key=f"del_{idx}", help="リストから削除", type="secondary"):
                    remove_video(idx)
                    st.rerun()

            st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("URL入力に戻る", use_container_width=True):
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
        st.error("ダウンロード可能なファイルがありませんでした。")
        if st.button("戻る"):
            st.session_state.stage = 'preview'
            st.rerun()

# ステップ4: 完了画面
if st.session_state.stage == 'finished':
    st.markdown('### <i class="fa-solid fa-download icon-spacing"></i> 3. ダウンロード', unsafe_allow_html=True)
    
    if st.session_state.zip_data:
        # 絵文字ラベルを変更
        st.download_button(
            label="ZIPでまとめて保存",
            data=st.session_state.zip_data,
            file_name="audio_archive.zip",
            mime="application/zip",
            use_container_width=True,
            type="primary"
        )

    st.markdown("#### 個別ファイル")
    for item in st.session_state.download_results:
        size_mb = len(item['data']) / (1024 * 1024)
        
        col_dl_1, col_dl_2 = st.columns([3, 1])
        with col_dl_1:
            # 絵文字をFont Awesomeアイコンに変更
            st.markdown(f'<i class="fa-solid fa-file-audio icon-spacing"></i>**{item["filename"]}** ({size_mb:.1f} MB)', unsafe_allow_html=True)
        with col_dl_2:
            st.download_button(
                label="保存",
                data=item['data'],
                file_name=item['filename'],
                mime=item['mime'],
                key=f"dl_{item['filename']}",
                use_container_width=True
            )
        st.markdown("<hr style='margin: 5px 0; opacity: 0.2;'>", unsafe_allow_html=True)
        
    if st.button("最初に戻る"):
        st.session_state.stage = 'input'
        st.session_state.video_infos = []
        st.session_state.download_results = None
        st.rerun()
