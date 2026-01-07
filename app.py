import streamlit as st
import yt_dlp
import os
import tempfile
import time
import zipfile
import io
import re
import subprocess  # FFmpeg直接実行用に追記
import shutil      # ファイル操作用に追記

# --- ページ設定 ---
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
    st.markdown('### <i class="fa-solid fa-sliders icon-spacing"></i> 設定', unsafe_allow_html=True)
    
    # ★モード選択を追加
    app_mode = st.radio("モード選択", ["YouTubeダウンロード", "ローカルMP3編集"])
    st.markdown('---')

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
                        'is_local': False, # ローカル判定フラグ
                        # 以下編集用フィールド
                        'custom_filename': sanitize_filename(title), 
                        'custom_title': title,            # メタデータ用タイトル
                        'custom_artist': uploader,        # メタデータ用アーティスト
                        'custom_album': title,            # メタデータ用アルバム（初期値はタイトル）
                        'thumb_mode': 'youtube',          # 'youtube' or 'upload'
                        'custom_thumb_bytes': None        # アップロードされた画像のバイナリ
                    })
                except Exception as e:
                    st.error(f"Error: {e}")
    return info_list

# ★ローカルファイルの情報を生成する関数
def get_local_file_info(uploaded_files):
    info_list = []
    for f in uploaded_files:
        # 拡張子を除いたファイル名を取得
        base_name = os.path.splitext(f.name)[0]
        # ファイルのバイナリデータを読み込む
        file_bytes = f.getvalue()
        
        info_list.append({
            'title': base_name,
            'uploader': 'Unknown',
            'thumbnail': None, # ローカルの場合デフォルト画像なし
            'duration': None,
            'url': None, # URLなし
            'is_local': True,
            'file_data': file_bytes, # バイナリデータ保持
            
            # 以下編集用フィールド
            'custom_filename': sanitize_filename(base_name),
            'custom_title': base_name,
            'custom_artist': '',
            'custom_album': '',
            'thumb_mode': 'upload', # 初期値をアップロードモードに
            'custom_thumb_bytes': None
        })
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
            base_filename = f"video_{idx}" # 一時ファイル名（衝突回避のため固定）
            final_filename = sanitize_filename(info['custom_filename'])
            mp3_path = f"{tmp_dir}/{base_filename}.mp3"
            
            # メタデータ情報の取得
            m_title = info['custom_title']
            m_artist = info['custom_artist']
            m_album = info['custom_album']

            main_status.markdown(f'<i class="fa-solid fa-list-check icon-spacing"></i> 処理中 ({idx+1}/{total_videos}): **{final_filename}**', unsafe_allow_html=True)
            
            single_status = st.empty()
            single_bar = st.progress(0)
            hooks = ProgressHooks(single_status, single_bar)

            try:
                # ★ローカルファイルかYouTubeかで処理を分岐
                if info.get('is_local'):
                    # ローカルファイル処理
                    single_status.markdown('<i class="fa-solid fa-file-import"></i> ファイル読み込み中...', unsafe_allow_html=True)
                    with open(mp3_path, "wb") as f:
                        f.write(info['file_data'])
                    single_bar.progress(1.0)
                    time.sleep(0.5) # UI更新用ウェイト
                else:
                    # YouTubeダウンロード処理
                    url = info['url']
                    
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

                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([url])
                
                # ファイル存在確認
                if not os.path.exists(mp3_path):
                    raise Exception("MP3 conversion failed or file not found")

                # サムネイル画像の準備
                cover_image_path = None
                
                # A: カスタム画像がアップロードされている場合
                if info['thumb_mode'] == 'upload' and info['custom_thumb_bytes']:
                    cover_image_path = f"{tmp_dir}/{base_filename}_custom_cover.jpg"
                    with open(cover_image_path, "wb") as f:
                        f.write(info['custom_thumb_bytes'])
                
                # B: YouTubeのサムネイルを使う場合
                elif embed_thumb and info.get('thumb_mode') == 'youtube':
                    # yt_dlpが保存した画像を探す (jpg, webp, pngなど)
                    for f in os.listdir(tmp_dir):
                        if f.startswith(base_filename) and f.lower().endswith(('.jpg', '.jpeg', '.webp', '.png')) and not f.endswith('.mp3'):
                            cover_image_path = os.path.join(tmp_dir, f)
                            break
                
                # 2. FFmpegを使ってメタデータと画像を埋め込み
                output_mp3_path = f"{tmp_dir}/{final_filename}.mp3"
                
                # FFmpegコマンド構築
                ffmpeg_cmd = [
                    'ffmpeg', '-y', 
                    '-i', mp3_path,
                ]

                # カバー画像がある場合の入力追加
                if cover_image_path and embed_thumb:
                    ffmpeg_cmd.extend(['-i', cover_image_path])
                    # マッピング: 音声(0:0)と画像(1:0)
                    ffmpeg_cmd.extend(['-map', '0:0', '-map', '1:0'])
                    # ID3タグ設定 (画像)
                    ffmpeg_cmd.extend(['-c:v', 'copy', '-id3v2_version', '3', '-metadata:s:v', 'title="Album cover"', '-metadata:s:v', 'comment="Cover (front)"'])
                else:
                    ffmpeg_cmd.extend(['-map', '0:0'])
                
                # 音声コーデックはコピー
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
                single_status.markdown('<i class="fa-solid fa-tags"></i> メタデータ書込中...', unsafe_allow_html=True)
                subprocess.run(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                
                # 中間ファイルのクリーンアップ
                if os.path.exists(mp3_path): os.remove(mp3_path)
                if cover_image_path and os.path.exists(cover_image_path) and info['thumb_mode'] == 'upload': 
                     # アップロードした一時画像のみ消す
                     pass

                single_status.markdown('<i class="fa-solid fa-circle-check" style="color:#00ff88"></i> 完了', unsafe_allow_html=True)

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
            
        main_status.markdown('<i class="fa-solid fa-face-smile icon-spacing"></i> すべての処理が完了しました！', unsafe_allow_html=True)
        return downloaded_data, zip_buffer


# --- メインUI ---
if 'stage' not in st.session_state:
    st.session_state.stage = 'input'
if 'video_infos' not in st.session_state:
    st.session_state.video_infos = []

# ステップ1: URL入力 または ファイル選択
if st.session_state.stage == 'input':
    # ★モードによって表示を切り替え
    if app_mode == "YouTubeダウンロード":
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
    
    else: # ローカルMP3編集モード
        st.markdown('### <i class="fa-solid fa-file-audio icon-spacing"></i> 1. MP3ファイルを選択', unsafe_allow_html=True)
        uploaded_files = st.file_uploader(
            "MP3ファイルをアップロード", 
            type=['mp3'], 
            accept_multiple_files=True,
            label_visibility="collapsed"
        )
        if st.button("編集へ進む", type="primary", use_container_width=True):
            if uploaded_files:
                with st.spinner("ファイルを読み込んでいます..."):
                    infos = get_local_file_info(uploaded_files)
                    st.session_state.video_infos = infos
                    st.session_state.stage = 'preview'
                    st.rerun()
            else:
                st.warning("ファイルを選択してください")

# ステップ2: プレビュー & 編集
if st.session_state.stage == 'preview':
    st.markdown(f'### <i class="fa-solid fa-pen-to-square icon-spacing"></i> 2. 編集と確認 ({len(st.session_state.video_infos)}件)', unsafe_allow_html=True)
    
    if len(st.session_state.video_infos) == 0:
        st.info("リストが空です。入力をやり直してください。")
        if st.button("戻る"):
            st.session_state.stage = 'input'
            st.rerun()
    
    current_infos = st.session_state.video_infos.copy()
    
    for idx, info in enumerate(current_infos):
        with st.container():
            st.markdown('<div class="edit-card">', unsafe_allow_html=True)
            
            # レイアウト調整: 画像設定(左) / メタデータ設定(中) / 削除(右)
            col_img, col_edit, col_del = st.columns([1.5, 3, 0.5])
            
            with col_img:
                st.caption("カバー画像")
                
                # ★ローカルモードの場合は「YouTube」選択肢を隠すか、無効化する
                options = ["YouTube", "アップロード"]
                if info.get('is_local'):
                    # ローカルならYouTube画像はないのでアップロードのみをデフォルトにするなどの処理
                    # ここではシンプルにラジオボタンの選択肢を制御
                    options = ["アップロード"]
                
                # UIのキーが一意になるように
                thumb_mode = st.radio(
                    "画像ソース", 
                    options, 
                    key=f"thumb_mode_{idx}",
                    label_visibility="collapsed",
                    horizontal=True
                )
                
                # セッションステートへの反映
                st.session_state.video_infos[idx]['thumb_mode'] = 'youtube' if thumb_mode == "YouTube" else 'upload'

                if thumb_mode == "YouTube" and not info.get('is_local'):
                    if info['thumbnail']:
                        st.image(info['thumbnail'], use_container_width=True)
                    else:
                        st.text("No Image")
                else:
                    uploaded_file = st.file_uploader("画像を選択", type=['jpg', 'png', 'webp'], key=f"uploader_{idx}")
                    if uploaded_file:
                        # 画像データをバイトとして保持
                        st.session_state.video_infos[idx]['custom_thumb_bytes'] = uploaded_file.getvalue()
                        st.image(uploaded_file, caption="アップロード画像", use_container_width=True)
                    elif info.get('custom_thumb_bytes'):
                        st.image(info['custom_thumb_bytes'], caption="アップロード済み", use_container_width=True)
                    else:
                        st.markdown('<div style="background:#333; height:100px; display:flex; align-items:center; justify-content:center; color:#666;">No Image</div>', unsafe_allow_html=True)

            with col_edit:
                # ファイル名
                new_filename = st.text_input(
                    "ファイル名 (拡張子なし)", 
                    value=info['custom_filename'], 
                    key=f"fname_{idx}"
                )
                
                st.markdown("---")
                
                # メタデータ入力カラム
                mc1, mc2 = st.columns(2)
                with mc1:
                    new_title = st.text_input("タイトル (曲名)", value=info['custom_title'], key=f"title_{idx}")
                    new_artist = st.text_input("アーティスト", value=info['custom_artist'], key=f"artist_{idx}")
                with mc2:
                    new_album = st.text_input("アルバム名", value=info['custom_album'], key=f"album_{idx}")
                
                # セッションステートの更新
                st.session_state.video_infos[idx]['custom_filename'] = new_filename
                st.session_state.video_infos[idx]['custom_title'] = new_title
                st.session_state.video_infos[idx]['custom_artist'] = new_artist
                st.session_state.video_infos[idx]['custom_album'] = new_album

            with col_del:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("削除", key=f"del_{idx}", help="リストから削除", type="secondary"):
                    remove_video(idx)
                    st.rerun()

            st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("入力画面に戻る", use_container_width=True):
            st.session_state.stage = 'input'
            st.rerun()
    with c2:
        btn_label = "編集・書き出し実行" if app_mode == "ローカルMP3編集" else "ダウンロード開始"
        if st.button(btn_label, type="primary", use_container_width=True):
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
    st.markdown('### <i class="fa-solid fa-download icon-spacing"></i> 3. 保存', unsafe_allow_html=True)
    
    if st.session_state.zip_data:
        st.download_button(
            label="ZIPでまとめて保存",
            data=st.session_state.zip_data,
            file_name="edited_audio_files.zip",
            mime="application/zip",
            use_container_width=True,
            type="primary"
        )

    st.markdown("#### 個別ファイル")
    for item in st.session_state.download_results:
        size_mb = len(item['data']) / (1024 * 1024)
        
        col_dl_1, col_dl_2 = st.columns([3, 1])
        with col_dl_1:
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
