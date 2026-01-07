import streamlit as st
import yt_dlp
import os
import tempfile
import time
import zipfile
import io
import re
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TALB, APIC, error

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

# ── 共通関数: ファイル名サニタイズ ──
def sanitize_filename(name):
    """ファイル名に使えない文字を除去"""
    return re.sub(r'[\\/*?:"<>|]', "", name)

# ── 共通関数: メタデータ書き込み (mutagen) ──
def apply_id3_tags(file_path, title, artist, album, cover_data=None):
    try:
        audio = MP3(file_path, ID3=ID3)
        try:
            audio.add_tags()
        except error:
            pass

        if title: audio.tags.add(TIT2(encoding=3, text=title))
        if artist: audio.tags.add(TPE1(encoding=3, text=artist))
        if album: audio.tags.add(TALB(encoding=3, text=album))

        if cover_data:
            audio.tags.add(
                APIC(
                    encoding=3, 
                    mime='image/jpeg', 
                    type=3, 
                    desc='Cover',
                    data=cover_data
                )
            )
        audio.save()
    except Exception as e:
        print(f"Metadata Error: {e}")

# ── サイドバー設定 ──
with st.sidebar:
    st.markdown('### <i class="fa-solid fa-bars icon-spacing"></i> モード選択', unsafe_allow_html=True)
    mode = st.radio("機能を選択", ["YouTubeダウンロード", "MP3タグ編集 (ローカル)"], label_visibility="collapsed")
    
    st.markdown('---')
    st.markdown('### <i class="fa-solid fa-sliders icon-spacing"></i> 詳細設定', unsafe_allow_html=True)
    
    if mode == "YouTubeダウンロード":
        # 形式はMP3固定
        format_type = 'mp3'
        st.markdown('**<i class="fa-solid fa-headphones icon-spacing"></i> 音質設定**', unsafe_allow_html=True)
        audio_quality_map = {
            '最高 (Best)': '0', 
            '高音質 (192kbps)': '192', 
            '標準 (128kbps)': '128'
        }
        quality_label = st.selectbox("ビットレート", list(audio_quality_map.keys()))
        quality_val = audio_quality_map[quality_label]
        
        st.markdown('---')
        embed_thumb = st.checkbox("デフォルトサムネイル埋め込み", value=True)

# ==========================================
# モードA: YouTubeダウンローダー
# ==========================================
if mode == "YouTubeダウンロード":

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
                        info_list.append({
                            'title': info.get('title', 'Unknown'),
                            'uploader': info.get('uploader', 'Unknown'),
                            'thumbnail': info.get('thumbnail'),
                            'duration': info.get('duration'),
                            'url': url,
                            'custom_filename': sanitize_filename(info.get('title', 'audio')), 
                            'custom_title': info.get('title', 'Unknown'),
                            'custom_artist': info.get('uploader', 'Unknown'),
                            'custom_album': '', 
                            'custom_cover_bytes': None
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
                final_title = info.get('custom_title', '')
                final_artist = info.get('custom_artist', '')
                final_album = info.get('custom_album', '')
                custom_cover = info.get('custom_cover_bytes')

                main_status.markdown(f'<i class="fa-solid fa-list-check icon-spacing"></i> 処理中 ({idx+1}/{total_videos}): **{final_filename}**', unsafe_allow_html=True)
                
                single_status = st.empty()
                single_bar = st.progress(0)
                hooks = ProgressHooks(single_status, single_bar)

                ydl_opts = {
                    'outtmpl': f'{tmp_dir}/{final_filename}.%(ext)s',
                    'quiet': True,
                    'progress_hooks': [hooks.hook],
                }
                if cookie_path: ydl_opts['cookiefile'] = cookie_path

                postprocessors = [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3'}]
                if quality_val != '0':
                    postprocessors[0]['preferredquality'] = quality_val
                
                postprocessors.append({'key': 'FFmpegMetadata', 'add_metadata': True})
                
                if embed_thumb and not custom_cover:
                    ydl_opts['writethumbnail'] = True
                    postprocessors.append({'key': 'EmbedThumbnail'})
                
                ydl_opts.update({'format': 'bestaudio/best', 'postprocessors': postprocessors})

                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([url])
                    
                    mp3_path = os.path.join(tmp_dir, f"{final_filename}.mp3")
                    if os.path.exists(mp3_path):
                        apply_id3_tags(mp3_path, title=final_title, artist=final_artist, album=final_album, cover_data=custom_cover)

                    single_status.markdown('<i class="fa-solid fa-circle-check" style="color:#00ff88"></i> 完了', unsafe_allow_html=True)
                except Exception as e:
                    single_status.error(f"エラー: {e}")
                    continue
                
                main_progress.progress((idx + 1) / total_videos)

            files = [f for f in os.listdir(tmp_dir) if f.endswith(".mp3")]
            for filename in files:
                with open(os.path.join(tmp_dir, filename), "rb") as f:
                    downloaded_data.append({"filename": filename, "data": f.read(), "mime": "audio/mpeg"})

            if len(files) > 0:
                zip_io = io.BytesIO()
                with zipfile.ZipFile(zip_io, 'w', zipfile.ZIP_DEFLATED) as zf:
                    for filename in files:
                        zf.write(os.path.join(tmp_dir, filename), arcname=filename)
                zip_buffer = zip_io.getvalue()
                
            main_status.markdown('<i class="fa-solid fa-face-smile icon-spacing"></i> すべての処理が完了しました！', unsafe_allow_html=True)
            return downloaded_data, zip_buffer

    # --- メインUI (Downloader) ---
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
                
                # レイアウト用のカラムを作成（左：画像、中：編集、右：削除）
                col_img, col_edit, col_del = st.columns([1.5, 3, 0.5])
                
                # ★ポイント: 「編集カラム（入力）」を先に処理して、セッションステートを更新する
                with col_edit:
                    new_filename = st.text_input("ファイル名 (拡張子なし)", value=info['custom_filename'], key=f"fname_{idx}")
                    c_title, c_artist = st.columns(2)
                    with c_title:
                        new_title = st.text_input("タイトル", value=info['custom_title'], key=f"title_{idx}")
                    with c_artist:
                        new_artist = st.text_input("アーティスト", value=info['custom_artist'], key=f"artist_{idx}")
                    new_album = st.text_input("アルバム名", value=info['custom_album'], key=f"album_{idx}")
                    
                    # 画像アップローダー
                    uploaded_cover = st.file_uploader("カバー画像を変更 (jpg/png)", type=['jpg', 'jpeg', 'png'], key=f"cover_{idx}")
                    
                    # セッションステート更新
                    st.session_state.video_infos[idx]['custom_filename'] = new_filename
                    st.session_state.video_infos[idx]['custom_title'] = new_title
                    st.session_state.video_infos[idx]['custom_artist'] = new_artist
                    st.session_state.video_infos[idx]['custom_album'] = new_album
                    
                    # ★ここでアップロード有無を判定し、セッションステートを即時更新
                    if uploaded_cover is not None:
                        st.session_state.video_infos[idx]['custom_cover_bytes'] = uploaded_cover.getvalue()

                # ★ポイント: 「画像カラム（表示）」を後に処理することで、更新された画像データを表示できる
                with col_img:
                    # セッションステートから最新の値を取得（アップロード直後のデータも反映される）
                    current_cover = st.session_state.video_infos[idx].get('custom_cover_bytes')
                    default_thumb = info.get('thumbnail')
                    
                    display_thumb = current_cover if current_cover else default_thumb
                    
                    if display_thumb:
                        st.image(display_thumb, use_container_width=True)
                    else:
                        st.markdown('<div style="height:100px; background:#333; display:flex; align-items:center; justify-content:center; color:#666;">No Image</div>', unsafe_allow_html=True)
                    
                    duration_m = info['duration'] // 60 if info['duration'] else 0
                    duration_s = info['duration'] % 60 if info['duration'] else 0
                    st.caption(f"長さ: {duration_m}:{duration_s:02d}")

                with col_del:
                    st.markdown("<br>", unsafe_allow_html=True)
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
            st.download_button("ZIPでまとめて保存", st.session_state.zip_data, "audio_archive.zip", "application/zip", type="primary", use_container_width=True)

        st.markdown("#### 個別ファイル")
        for item in st.session_state.download_results:
            col_dl_1, col_dl_2 = st.columns([3, 1])
            with col_dl_1:
                st.markdown(f'<i class="fa-solid fa-file-audio icon-spacing"></i>**{item["filename"]}**', unsafe_allow_html=True)
            with col_dl_2:
                st.download_button("保存", item['data'], item['filename'], item['mime'], key=f"dl_{item['filename']}", use_container_width=True)
            st.markdown("<hr style='margin: 5px 0; opacity: 0.2;'>", unsafe_allow_html=True)
            
        if st.button("最初に戻る"):
            st.session_state.stage = 'input'
            st.session_state.video_infos = []
            st.session_state.download_results = None
            st.rerun()

# ==========================================
# モードB: MP3タグ編集 (ローカル)
# ==========================================
elif mode == "MP3タグ編集 (ローカル)":
    st.markdown('### <i class="fa-solid fa-file-audio icon-spacing"></i> MP3ファイルをアップロード', unsafe_allow_html=True)
    
    # セッション管理
    if 'editor_files' not in st.session_state:
        st.session_state.editor_files = []
    if 'editor_processed_zip' not in st.session_state:
        st.session_state.editor_processed_zip = None

    uploaded_files = st.file_uploader("MP3ファイルを選択（複数可）", type=['mp3'], accept_multiple_files=True)
    
    # ファイルがアップロードされたら解析してセッションに格納
    if uploaded_files:
        # 既にリストにあるファイルと重複しないかチェックする簡易ロジック（ファイル名ベース）
        current_filenames = [f['original_name'] for f in st.session_state.editor_files]
        
        new_files_added = False
        for up_file in uploaded_files:
            if up_file.name not in current_filenames:
                try:
                    # 一時ファイルに保存してmutagenで解析
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                        tmp.write(up_file.getvalue())
                        tmp_path = tmp.name
                    
                    audio = MP3(tmp_path, ID3=ID3)
                    
                    # 既存タグ読み込み (なければ空文字)
                    title = str(audio.tags.get("TIT2", "")) if "TIT2" in audio.tags else ""
                    artist = str(audio.tags.get("TPE1", "")) if "TPE1" in audio.tags else ""
                    album = str(audio.tags.get("TALB", "")) if "TALB" in audio.tags else ""
                    
                    # 画像データ抽出
                    cover_bytes = None
                    for tag in audio.tags.values():
                        if isinstance(tag, APIC):
                            cover_bytes = tag.data
                            break
                    
                    st.session_state.editor_files.append({
                        'original_name': up_file.name,
                        'file_data': up_file.getvalue(), # オリジナルデータ保持
                        'filename': os.path.splitext(up_file.name)[0],
                        'title': title,
                        'artist': artist,
                        'album': album,
                        'cover_bytes': cover_bytes,
                        'new_cover_bytes': None
                    })
                    new_files_added = True
                    os.unlink(tmp_path) # 後始末
                except Exception as e:
                    st.error(f"ファイル {up_file.name} の解析エラー: {e}")

    # 編集画面
    if st.session_state.editor_files:
        st.markdown(f"### 編集 ({len(st.session_state.editor_files)}件)")
        
        if st.button("すべてクリア", type="secondary"):
            st.session_state.editor_files = []
            st.rerun()

        edit_list = st.session_state.editor_files
        for idx, item in enumerate(edit_list):
            st.markdown('<div class="edit-card">', unsafe_allow_html=True)
            col_img, col_info, col_del = st.columns([1.5, 3, 0.5])
            
            # 【修正点】: 情報・編集カラム（col_info）を先に処理することで、アップロードされた画像の反映を確実にする
            with col_info:
                new_fname = st.text_input("ファイル名", value=item['filename'], key=f"ed_fn_{idx}")
                c1, c2 = st.columns(2)
                with c1:
                    new_title = st.text_input("タイトル", value=item['title'], key=f"ed_ti_{idx}")
                with c2:
                    new_artist = st.text_input("アーティスト", value=item['artist'], key=f"ed_ar_{idx}")
                new_album = st.text_input("アルバム", value=item['album'], key=f"ed_al_{idx}")
                
                up_cover = st.file_uploader("画像変更", type=['jpg','png'], key=f"ed_cv_{idx}")
                if up_cover:
                    st.session_state.editor_files[idx]['new_cover_bytes'] = up_cover.getvalue()

                # ステート更新
                st.session_state.editor_files[idx]['filename'] = new_fname
                st.session_state.editor_files[idx]['title'] = new_title
                st.session_state.editor_files[idx]['artist'] = new_artist
                st.session_state.editor_files[idx]['album'] = new_album

            # 【修正点】: 画像表示カラム（col_img）を後に実行し、更新されたステートを参照する
            with col_img:
                # セッションステートから最新のデータを取得
                current_item = st.session_state.editor_files[idx]
                display_img = current_item['new_cover_bytes'] if current_item['new_cover_bytes'] else current_item['cover_bytes']
                if display_img:
                    st.image(display_img, use_container_width=True)
                else:
                    st.markdown('<div style="height:100px; background:#333; display:flex; align-items:center; justify-content:center; color:#666;">No Cover</div>', unsafe_allow_html=True)
            
            with col_del:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("削除", key=f"ed_del_{idx}", type="secondary"):
                    del st.session_state.editor_files[idx]
                    st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

        if st.button("変更を保存してZIP作成", type="primary", use_container_width=True):
            with st.spinner("処理中..."):
                with tempfile.TemporaryDirectory() as tmp_dir:
                    processed_files = []
                    
                    for item in st.session_state.editor_files:
                        # 安全なファイル名
                        safe_name = sanitize_filename(item['filename']) + ".mp3"
                        file_path = os.path.join(tmp_dir, safe_name)
                        
                        # ファイル書き出し
                        with open(file_path, "wb") as f:
                            f.write(item['file_data'])
                        
                        # タグ適用
                        final_cover = item['new_cover_bytes'] if item['new_cover_bytes'] else item['cover_bytes']
                        apply_id3_tags(
                            file_path,
                            title=item['title'],
                            artist=item['artist'],
                            album=item['album'],
                            cover_data=final_cover
                        )
                        processed_files.append(safe_name)

                    # ZIP作成
                    if processed_files:
                        zip_io = io.BytesIO()
                        with zipfile.ZipFile(zip_io, 'w', zipfile.ZIP_DEFLATED) as zf:
                            for fname in processed_files:
                                zf.write(os.path.join(tmp_dir, fname), arcname=fname)
                        st.session_state.editor_processed_zip = zip_io.getvalue()
                        st.success("作成完了！")
                        st.rerun()

        # ダウンロードボタン
        if st.session_state.editor_processed_zip:
            st.markdown("---")
            st.download_button(
                label="編集済みファイルをダウンロード (ZIP)",
                data=st.session_state.editor_processed_zip,
                file_name="edited_songs.zip",
                mime="application/zip",
                type="primary",
                use_container_width=True
            )
