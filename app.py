import streamlit as st
import yt_dlp
import os
import tempfile
import time
import zipfile
import io
import re

# --- ページ設定 ---
st.set_page_config(page_title="Video Downloader Pro", layout="centered", page_icon="📥")

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
st.markdown('<div class="main-title"><i class="fa-solid fa-cloud-arrow-down icon-spacing"></i>Video Downloader Pro</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-text">ZIP一括ダウンロード・編集・メタデータ管理</div>', unsafe_allow_html=True)

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
        # 削除後に再描画を強制するためにセッションを少し更新（通常は自動で再実行される）

# ── サイドバー設定 ──
with st.sidebar:
    st.markdown('### <i class="fa-solid fa-sliders icon-spacing"></i> 詳細設定', unsafe_allow_html=True)
    
    # フォーマット選択
    format_type = st.selectbox(
        "保存形式",
        options=['mp4', 'mp3', 'm4a', 'wav'],
        index=0
    )
    
    # 動画用設定
    if format_type == 'mp4':
        st.markdown('---')
        st.markdown('**<i class="fa-solid fa-display icon-spacing"></i> 画質設定**', unsafe_allow_html=True)
        res_options = {
            '最高画質 (Best)': 'best',
            '4K (2160p)': '2160',
            'フルHD (1080p)': '1080',
            'HD (720p)': '720',
            'SD (480p)': '480'
        }
        selected_res = st.selectbox("解像度上限", list(res_options.keys()), index=0)
        res_val = res_options[selected_res]
        
    # 音声用設定
    else:
        st.markdown('---')
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
                    # 初期値としてタイトルとアップローダーを設定
                    info_list.append({
                        'title': info.get('title', 'Unknown'),
                        'uploader': info.get('uploader', 'Unknown'),
                        'thumbnail': info.get('thumbnail'),
                        'duration': info.get('duration'),
                        'url': url,
                        # 編集用のフィールドを初期化
                        'custom_filename': sanitize_filename(info.get('title', 'video')), 
                        'custom_artist': info.get('uploader', 'Unknown')
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
            # ユーザーが編集したファイル名を使用
            final_filename = sanitize_filename(info['custom_filename'])
            # ユーザーが編集したアーティスト名（メタデータ用）
            final_artist = info['custom_artist']

            main_status.markdown(f'<i class="fa-solid fa-list-check icon-spacing"></i> 処理中 ({idx+1}/{total_videos}): **{final_filename}**', unsafe_allow_html=True)
            
            single_status = st.empty()
            single_bar = st.progress(0)
            hooks = ProgressHooks(single_status, single_bar)

            # 出力ファイル名の指定（ユーザー指定名を使用）
            ydl_opts = {
                'outtmpl': f'{tmp_dir}/{final_filename}.%(ext)s',
                'quiet': True,
                'progress_hooks': [hooks.hook],
            }
            if cookie_path: ydl_opts['cookiefile'] = cookie_path

            # フォーマット設定
            if format_type == 'mp4':
                ydl_opts.update({'format': f'bestvideo[height<={res_val}]+bestaudio/best', 'merge_output_format': 'mp4'})
            else:
                postprocessors = [{'key': 'FFmpegExtractAudio','preferredcodec': format_type}]
                if format_type != 'wav' and quality_val != '0':
                    postprocessors[0]['preferredquality'] = quality_val
                
                # アーティストメタデータの強制上書き設定
                if add_metadata:
                    postprocessors.append({
                        'key': 'FFmpegMetadata',
                        'add_metadata': True,
                    })
                
                ydl_opts.update({'format': 'bestaudio/best', 'postprocessors': postprocessors})

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                single_status.markdown('<i class="fa-solid fa-circle-check" style="color:#00ff88"></i> 完了', unsafe_allow_html=True)
            except Exception as e:
                single_status.error(f"エラー: {e}")
                continue
            
            main_progress.progress((idx + 1) / total_videos)

        # ファイル回収
        files = [f for f in os.listdir(tmp_dir) if f.endswith(f".{format_type}")]
        for filename in files:
            with open(os.path.join(tmp_dir, filename), "rb") as f:
                downloaded_data.append({"filename": filename, "data": f.read(), "mime": f"video/mp4" if format_type == 'mp4' else f"audio/{format_type}"})

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

    if st.button("動画情報を解析する", type="primary", use_container_width=True):
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
        st.info("動画リストが空です。URLを入力し直してください。")
        if st.button("戻る"):
            st.session_state.stage = 'input'
            st.rerun()
    
    # 編集用ループ
    # 削除操作が行われるとインデックスがずれるため、コピーに対してループするか、安全に再描画する
    current_infos = st.session_state.video_infos.copy()
    
    for idx, info in enumerate(current_infos):
        # カードコンテナの開始
        with st.container():
            st.markdown('<div class="edit-card">', unsafe_allow_html=True)
            
            col_img, col_edit, col_del = st.columns([1.5, 3, 0.5])
            
            with col_img:
                st.image(info['thumbnail'], use_container_width=True)
                duration_m = info['duration'] // 60 if info['duration'] else 0
                duration_s = info['duration'] % 60 if info['duration'] else 0
                st.caption(f"長さ: {duration_m}:{duration_s:02d}")

            with col_edit:
                # ファイル名編集フォーム（デフォルトは動画タイトル）
                new_filename = st.text_input(
                    "ファイル名 (拡張子なし)", 
                    value=info['custom_filename'], 
                    key=f"fname_{idx}",
                    placeholder="ファイル名を入力"
                )
                
                # アーティスト/アップローダー名編集
                new_artist = st.text_input(
                    "アーティスト / チャンネル名", 
                    value=info['custom_artist'], 
                    key=f"artist_{idx}"
                )
                
                # セッションステートをリアルタイム更新
                st.session_state.video_infos[idx]['custom_filename'] = new_filename
                st.session_state.video_infos[idx]['custom_artist'] = new_artist

            with col_del:
                st.markdown("<br>", unsafe_allow_html=True) # レイアウト調整用の空白
                # 削除ボタン
                if st.button("🗑️", key=f"del_{idx}", help="リストから削除", type="secondary"):
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
        st.download_button(
            label="📦 まとめてZIPで保存",
            data=st.session_state.zip_data,
            file_name="videos_archive.zip",
            mime="application/zip",
            use_container_width=True,
            type="primary"
        )

    st.markdown("#### 個別ファイル")
    for item in st.session_state.download_results:
        # ファイルサイズ計算（概算）
        size_mb = len(item['data']) / (1024 * 1024)
        
        col_dl_1, col_dl_2 = st.columns([3, 1])
        with col_dl_1:
            st.write(f"📄 **{item['filename']}** ({size_mb:.1f} MB)")
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
