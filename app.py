import streamlit as st
import yt_dlp
import os
import tempfile
import time
import zipfile
import io
import re
import subprocess  # FFmpeg直接実行用
import shutil      # ファイル操作用

# --- ページ設定 ---
st.set_page_config(page_title="Audio Downloader Pro", layout="centered")

# --- Font Awesome & カスタムCSS (ホワイトベースのデザイン) ---
st.markdown("""
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        /* 全体のフォント設定と背景 */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
        
        html, body, [class*="css"] {
            font-family: 'Inter', sans-serif;
            color: #333333;
            background-color: #ffffff;
        }

        /* Streamlitのデフォルト背景を白に強制 */
        .stApp {
            background-color: #f8f9fa;
        }

        /* メインタイトル */
        .main-title {
            font-size: 2.2rem;
            font-weight: 800;
            background: linear-gradient(135deg, #2575fc 0%, #6a11cb 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
            display: flex;
            align-items: center;
        }

        /* サブタイトル */
        .sub-text {
            color: #666;
            font-size: 0.95rem;
            margin-bottom: 2.5rem;
            border-bottom: 2px solid #eaeaea;
            padding-bottom: 1rem;
        }

        /* カードデザイン (ホワイトベース) */
        .edit-card {
            background-color: #ffffff;
            border: 1px solid #e0e0e0;
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 20px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.03);
            transition: all 0.2s ease;
        }
        
        .edit-card:hover {
            box-shadow: 0 6px 16px rgba(0,0,0,0.06);
            border-color: #d0d0d0;
        }
        
        /* ラベルのスタイル */
        .card-label {
            font-size: 0.85rem;
            font-weight: 600;
            color: #888;
            margin-bottom: 4px;
        }

        /* 入力フィールドの微調整 */
        input[type="text"] {
            background-color: #fcfcfc;
            border: 1px solid #eee;
        }

        /* サムネイル画像 */
        .thumb-img {
            border-radius: 12px;
            width: 100%;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }

        /* 削除ボタン（ゴミ箱）のスタイル調整 */
        button[kind="secondary"] {
            border: 1px solid #ffecec !important;
            background-color: #fff !important;
            color: #ff4b4b !important;
            transition: 0.3s;
        }
        button[kind="secondary"]:hover {
            background-color: #ff4b4b !important;
            color: white !important;
            border-color: #ff4b4b !important;
        }

        /* アイコンのスタイル */
        .icon-spacing {
            margin-right: 12px;
        }
        
        .icon-primary {
            color: #2575fc;
        }
        
        /* プログレスバーの色調整 */
        .stProgress > div > div > div > div {
            background-image: linear-gradient(to right, #2575fc, #6a11cb);
        }
    </style>
""", unsafe_allow_html=True)

# --- ヘッダー部分 ---
st.markdown('<div class="main-title"><i class="fa-solid fa-music icon-spacing icon-primary"></i>Audio Downloader Pro</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-text">MP3ダウンロード・メタデータ編集・タグ管理ツール</div>', unsafe_allow_html=True)

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
    st.caption("オプション")
    embed_thumb = st.toggle("サムネイル埋め込み", value=True)
    add_metadata = st.toggle("メタデータ情報付与", value=True)

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
            self.status_placeholder.markdown(f'<span style="color:#2575fc"><i class="fa-solid fa-circle-notch fa-spin"></i></span> ダウンロード中... {d["_percent_str"]} (速度: {speed})', unsafe_allow_html=True)
            
        elif d['status'] == 'finished':
            self.progress_bar.progress(1.0)
            self.status_placeholder.markdown('<span style="color:#6a11cb"><i class="fa-solid fa-arrows-rotate fa-spin"></i></span> 変換・編集処理中...', unsafe_allow_html=True)

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
                    
                    # ファイル名として安全なデフォルト値を作成
                    safe_title = sanitize_filename(title)
                    
                    info_list.append({
                        'title': title,
                        'uploader': uploader,
                        'thumbnail': info.get('thumbnail'),
                        'duration': info.get('duration'),
                        'url': url,
                        # 以下編集用フィールド（初期値）
                        'custom_filename': safe_title, 
                        'custom_title': title,           # メタデータ用タイトル
                        'custom_artist': uploader,       # メタデータ用アーティスト
                        'custom_album': title,           # メタデータ用アルバム（初期値はタイトル）
                        'thumb_mode': 'youtube',         # 'youtube' or 'upload'
                        'custom_thumb_bytes': None       # アップロードされた画像のバイナリ
                    })
                except Exception as e:
                    st.error(f"Error extracting info: {e}")
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
            base_filename = f"video_{idx}" # 一時ファイル名（衝突回避のため固定）
            final_filename = sanitize_filename(info['custom_filename'])
            if not final_filename:
                final_filename = f"audio_track_{idx}"
            
            # メタデータ情報の取得
            m_title = info['custom_title']
            m_artist = info['custom_artist']
            m_album = info['custom_album']

            main_status.markdown(f'<i class="fa-solid fa-list-check icon-spacing icon-primary"></i> 処理中 ({idx+1}/{total_videos}): <b>{final_filename}</b>', unsafe_allow_html=True)
            
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
                
                # ダウンロードされたファイルの特定
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

                single_status.markdown('<i class="fa-solid fa-circle-check" style="color:#2ecc71"></i> 完了', unsafe_allow_html=True)

            except Exception as e:
                single_status.markdown(f'<span style="color:#e74c3c"><i class="fa-solid fa-triangle-exclamation"></i> エラー: {e}</span>', unsafe_allow_html=True)
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
            
        main_status.markdown('<i class="fa-solid fa-face-smile icon-spacing icon-primary"></i> すべての処理が完了しました！', unsafe_allow_html=True)
        return downloaded_data, zip_buffer


# --- メインUI ステート管理 ---
if 'stage' not in st.session_state:
    st.session_state.stage = 'input'
if 'video_infos' not in st.session_state:
    st.session_state.video_infos = []

# ステップ1: URL入力
if st.session_state.stage == 'input':
    st.markdown('### <i class="fa-solid fa-link icon-spacing icon-primary"></i> 1. URLを入力', unsafe_allow_html=True)
    st.markdown('<div style="margin-bottom:10px; font-size:0.9rem; color:#666;">YouTube動画のURLを貼り付けてください（複数行可）</div>', unsafe_allow_html=True)
    
    url_input = st.text_area(
        label="URL入力",
        placeholder="https://www.youtube.com/watch?v=...\nhttps://youtu.be/...",
        height=150,
        label_visibility="collapsed"
    )

    if st.button("情報を解析して編集へ", type="primary", use_container_width=True):
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

# ステップ2: プレビュー & 編集（ここが編集機能のメインUI）
if st.session_state.stage == 'preview':
    st.markdown(f'### <i class="fa-solid fa-pen-to-square icon-spacing icon-primary"></i> 2. MP3情報の編集と確認', unsafe_allow_html=True)
    st.markdown(f'<div style="margin-bottom:20px; color:#666;">{len(st.session_state.video_infos)}件のファイルが見つかりました。ダウンロード前にタグ情報を編集できます。</div>', unsafe_allow_html=True)
    
    if len(st.session_state.video_infos) == 0:
        st.info("リストが空です。URLを入力し直してください。")
        if st.button("戻る"):
            st.session_state.stage = 'input'
            st.rerun()
    
    current_infos = st.session_state.video_infos.copy()
    
    for idx, info in enumerate(current_infos):
        # カードコンテナ開始
        with st.container():
            st.markdown('<div class="edit-card">', unsafe_allow_html=True)
            
            # レイアウト: 画像設定(左) / メタデータ設定(中) / 削除(右)
            col_img, col_edit, col_del = st.columns([1.5, 3, 0.4])
            
            with col_img:
                st.markdown('<div class="card-label">カバー画像</div>', unsafe_allow_html=True)
                thumb_mode = st.radio(
                    "画像ソース", 
                    ["YouTube", "カスタム"], 
                    key=f"thumb_mode_{idx}",
                    label_visibility="collapsed",
                    horizontal=True
                )
                
                # セッションステートへの反映
                st.session_state.video_infos[idx]['thumb_mode'] = 'youtube' if thumb_mode == "YouTube" else 'upload'

                if thumb_mode == "YouTube":
                    if info['thumbnail']:
                        st.image(info['thumbnail'], use_container_width=True)
                    else:
                        st.markdown('<div style="background:#eee; height:150px; display:flex; align-items:center; justify-content:center; border-radius:8px;">No Image</div>', unsafe_allow_html=True)
                else:
                    uploaded_file = st.file_uploader("画像を選択", type=['jpg', 'png', 'webp'], key=f"uploader_{idx}", label_visibility="collapsed")
                    if uploaded_file:
                        st.session_state.video_infos[idx]['custom_thumb_bytes'] = uploaded_file.getvalue()
                        st.image(uploaded_file, caption="New Cover", use_container_width=True)
                    elif info.get('custom_thumb_bytes'):
                        st.image(info['custom_thumb_bytes'], caption="New Cover", use_container_width=True)
                    else:
                        st.markdown('<div style="font-size:0.8rem; color:#999; text-align:center; padding:20px; border:2px dashed #ddd; border-radius:8px;">画像をドラッグ<br>または選択</div>', unsafe_allow_html=True)

            with col_edit:
                st.markdown('<div class="card-label">ファイル設定</div>', unsafe_allow_html=True)
                # ファイル名
                new_filename = st.text_input(
                    "ファイル名 (拡張子なし)", 
                    value=info['custom_filename'], 
                    key=f"fname_{idx}",
                    placeholder="ファイル名を入力"
                )
                
                st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
                st.markdown('<div class="card-label">メタデータ (ID3タグ)</div>', unsafe_allow_html=True)
                
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
                if st.button("✕", key=f"del_{idx}", help="リストから削除", type="secondary"):
                    remove_video(idx)
                    st.rerun()

            st.markdown('</div>', unsafe_allow_html=True)
    
    c1, c2 = st.columns(2)
    with c1:
        if st.button("URL入力に戻る", use_container_width=True):
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
        st.error("ダウンロード可能なファイルがありませんでした。")
        if st.button("戻る"):
            st.session_state.stage = 'preview'
            st.rerun()

# ステップ4: 完了画面
if st.session_state.stage == 'finished':
    st.markdown('### <i class="fa-solid fa-download icon-spacing icon-primary"></i> 3. ダウンロード完了', unsafe_allow_html=True)
    
    # 成功メッセージ
    st.markdown("""
    <div style="background-color:#e8fdf5; border:1px solid #c3fae8; padding:15px; border-radius:10px; color:#1d8c62; margin-bottom:20px;">
        <i class="fa-solid fa-check-circle icon-spacing"></i> 変換とタグ付けが正常に完了しました
    </div>
    """, unsafe_allow_html=True)
    
    if st.session_state.zip_data:
        st.download_button(
            label="ZIPでまとめて保存",
            data=st.session_state.zip_data,
            file_name="audio_archive.zip",
            mime="application/zip",
            use_container_width=True,
            type="primary"
        )

    st.markdown("#### <i class='fa-regular fa-file-audio icon-spacing'></i> 個別ファイル", unsafe_allow_html=True)
    
    for item in st.session_state.download_results:
        size_mb = len(item['data']) / (1024 * 1024)
        
        # リストスタイル
        st.markdown(f"""
        <div style="background:#fff; border:1px solid #eee; padding:10px 15px; border-radius:8px; margin-bottom:8px; display:flex; align-items:center; justify-content:space-between;">
            <div style="display:flex; align-items:center;">
                <i class="fa-solid fa-music" style="color:#2575fc; margin-right:15px; font-size:1.2rem;"></i>
                <div>
                    <div style="font-weight:600; color:#333;">{item["filename"]}</div>
                    <div style="font-size:0.8rem; color:#999;">{size_mb:.1f} MB</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        st.download_button(
            label=f"保存: {item['filename']}",
            data=item['data'],
            file_name=item['filename'],
            mime=item['mime'],
            key=f"dl_{item['filename']}",
            use_container_width=True
        )
        st.markdown("<div style='margin-bottom:15px'></div>", unsafe_allow_html=True)
        
    if st.button("新しいファイルを処理する"):
        st.session_state.stage = 'input'
        st.session_state.video_infos = []
        st.session_state.download_results = None
        st.rerun()
