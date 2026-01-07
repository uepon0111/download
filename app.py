import streamlit as st
import yt_dlp
import os
import tempfile
import zipfile
import io
import re
import requests
from mutagen.id3 import ID3, TIT2, TPE1, TALB, APIC, TYER
from mutagen.mp3 import MP3

# --- ページ設定 ---
st.set_page_config(page_title="Audio Downloader Pro+", layout="centered")

# --- CSS設定 ---
st.markdown("""
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
        html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
        .main-title {
            font-size: 2.5rem; font-weight: 800;
            background: linear-gradient(45deg, #FF512F, #DD2476);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
        }
        .sub-text { color: #888; font-size: 1rem; margin-bottom: 2rem; }
        .edit-card {
            background-color: #262730; border: 1px solid #444;
            border-radius: 12px; padding: 20px; margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        .icon-spacing { margin-right: 10px; color: #DD2476; }
        .stButton button[kind="secondary"] {
            border-color: #ff4b4b !important; color: #ff4b4b !important;
        }
        .cover-preview { border-radius: 8px; max-width: 100%; margin-top: 10px; }
    </style>
""", unsafe_allow_html=True)

# --- ヘッダー ---
st.markdown('<div class="main-title"><i class="fa-solid fa-music icon-spacing"></i>Audio Downloader Pro+</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-text">高機能メタデータ編集・カスタムサムネイル対応</div>', unsafe_allow_html=True)

# ── 内部関数 ──
def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name)

def remove_video(index):
    if 0 <= index < len(st.session_state.video_infos):
        del st.session_state.video_infos[index]

# ── サイドバー設定 ──
with st.sidebar:
    st.markdown('### <i class="fa-solid fa-sliders icon-spacing"></i> 設定', unsafe_allow_html=True)
    audio_quality_map = {'最高 (Best)': '0', '高音質 (192kbps)': '192', '標準 (128kbps)': '128'}
    quality_label = st.selectbox("ビットレート", list(audio_quality_map.keys()))
    quality_val = audio_quality_map[quality_label]
    st.markdown('---')
    st.caption("※タイトルやアーティスト名などのメタデータはダウンロード後に適用されます。")

# ── 進捗表示クラス ──
class ProgressHooks:
    def __init__(self, status_placeholder, progress_bar):
        self.status_placeholder = status_placeholder
        self.progress_bar = progress_bar
    def hook(self, d):
        if d['status'] == 'downloading':
            p = d.get('_percent_str', '0%').replace('%','')
            try: per = float(p)
            except: per = 0
            self.progress_bar.progress(min(per / 100, 1.0))
            self.status_placeholder.markdown(f'ダウンロード中... {d["_percent_str"]}')
        elif d['status'] == 'finished':
            self.progress_bar.progress(1.0)
            self.status_placeholder.markdown('変換中...')

# ── 情報取得ロジック ──
def get_video_info(urls):
    info_list = []
    ydl_opts = {'quiet': True, 'extract_flat': False, 'skip_download': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        for url in urls:
            try:
                info = ydl.extract_info(url, download=False)
                info_list.append({
                    'url': url,
                    'original_title': info.get('title', ''),
                    'duration': info.get('duration'),
                    'thumbnail_url': info.get('thumbnail'),
                    # 編集用デフォルト値
                    'custom_title': info.get('title', 'Audio'),
                    'custom_artist': info.get('uploader', 'Unknown Artist'),
                    'custom_album': 'YouTube Download',
                    'cover_mode': 'YouTube', # YouTube or Custom
                    'custom_cover_bytes': None # カスタム画像データ
                })
            except Exception as e:
                st.error(f"Error fetching {url}: {e}")
    return info_list

# ── メタデータ適用関数 (Mutagen使用) ──
def apply_metadata(file_path, info):
    try:
        audio = MP3(file_path, ID3=ID3)
        try:
            audio.add_tags()
        except Exception:
            pass # すでにタグがある場合

        # テキストタグ設定
        audio.tags.add(TIT2(encoding=3, text=info['custom_title']))
        audio.tags.add(TPE1(encoding=3, text=info['custom_artist']))
        audio.tags.add(TALB(encoding=3, text=info['custom_album']))
        
        # カバー画像設定
        cover_data = None
        mime_type = 'image/jpeg'

        # 1. カスタム画像がアップロードされている場合
        if info['cover_mode'] == 'Custom' and info['custom_cover_bytes']:
            cover_data = info['custom_cover_bytes']
            # マジックナンバー等で判定もできるが、簡易的にjpegとする(pngでも動作はする)
            if cover_data.startswith(b'\x89PNG'):
                mime_type = 'image/png'
        
        # 2. YouTubeのサムネイルを使う場合
        elif info['cover_mode'] == 'YouTube' and info['thumbnail_url']:
            try:
                resp = requests.get(info['thumbnail_url'], timeout=10)
                if resp.status_code == 200:
                    cover_data = resp.content
                    if info['thumbnail_url'].endswith('.webp'):
                        mime_type = 'image/webp' # 一部のプレイヤーはwebp非対応の可能性あり
            except Exception:
                pass

        if cover_data:
            audio.tags.add(APIC(
                encoding=3,
                mime=mime_type,
                type=3, # 3 is for the cover image
                desc=u'Cover',
                data=cover_data
            ))
        
        audio.save()
        return True
    except Exception as e:
        print(f"Metadata Error: {e}")
        return False

# ── ダウンロード処理 ──
def process_download(info_list):
    downloaded_data = []
    zip_buffer = None
    main_progress = st.progress(0)
    main_status = st.empty()
    total = len(info_list)

    with tempfile.TemporaryDirectory() as tmp_dir:
        for idx, info in enumerate(info_list):
            filename_base = sanitize_filename(info['custom_title'])
            main_status.info(f"処理中 ({idx+1}/{total}): {filename_base}")
            
            s_stat = st.empty()
            s_bar = st.progress(0)
            hooks = ProgressHooks(s_stat, s_bar)

            # yt-dlp設定 (サムネイルは埋め込まず、後でMutagenで制御する)
            ydl_opts = {
                'outtmpl': f'{tmp_dir}/{filename_base}.%(ext)s',
                'quiet': True,
                'progress_hooks': [hooks.hook],
                'format': 'bestaudio/best',
                'writethumbnail': False, # 自前で処理するためFalse
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': quality_val,
                }],
            }

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([info['url']])
                
                # ダウンロードされたファイルのパスを特定
                mp3_path = os.path.join(tmp_dir, f"{filename_base}.mp3")
                
                # メタデータとカバー画像の適用
                if os.path.exists(mp3_path):
                    s_stat.markdown("🏷️ タグ情報を書き込み中...")
                    apply_metadata(mp3_path, info)
                    s_stat.success("完了")
                else:
                    s_stat.error("ファイルが見つかりません")
                    continue

            except Exception as e:
                s_stat.error(f"エラー: {e}")
                continue
            
            main_progress.progress((idx + 1) / total)

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

# --- メインロジック ---
if 'stage' not in st.session_state: st.session_state.stage = 'input'
if 'video_infos' not in st.session_state: st.session_state.video_infos = []

# 1. 入力画面
if st.session_state.stage == 'input':
    st.markdown('### 1. URL入力')
    url_input = st.text_area("URL", height=150, placeholder="https://www.youtube.com/watch?v=...")
    if st.button("解析開始", type="primary", use_container_width=True):
        urls = [u.strip() for u in url_input.splitlines() if u.strip()]
        if urls:
            with st.spinner("情報を取得中..."):
                infos = get_video_info(urls)
                if infos:
                    st.session_state.video_infos = infos
                    st.session_state.stage = 'preview'
                    st.rerun()

# 2. 編集画面
if st.session_state.stage == 'preview':
    st.markdown(f'### 2. メタデータ編集 ({len(st.session_state.video_infos)}件)')
    
    for idx, info in enumerate(st.session_state.video_infos):
        with st.container():
            st.markdown('<div class="edit-card">', unsafe_allow_html=True)
            c1, c2 = st.columns([1.5, 3])
            
            # --- 左カラム：画像設定 ---
            with c1:
                st.caption("カバー画像設定")
                img_mode = st.radio("画像ソース", ["YouTube", "Custom"], key=f"mode_{idx}", horizontal=True, label_visibility="collapsed")
                st.session_state.video_infos[idx]['cover_mode'] = img_mode

                if img_mode == "YouTube":
                    if info['thumbnail_url']:
                        st.image(info['thumbnail_url'], use_container_width=True)
                    else:
                        st.markdown("No Image")
                else:
                    uploaded_file = st.file_uploader("画像をアップロード", type=['jpg', 'png'], key=f"up_{idx}")
                    if uploaded_file:
                        # バイナリデータを保存
                        st.session_state.video_infos[idx]['custom_cover_bytes'] = uploaded_file.getvalue()
                        st.image(uploaded_file, caption="設定する画像", use_container_width=True)
                    elif st.session_state.video_infos[idx]['custom_cover_bytes']:
                        # すでにアップロード済みのデータを表示
                        st.image(st.session_state.video_infos[idx]['custom_cover_bytes'], caption="設定済み画像", use_container_width=True)
            
            # --- 右カラム：テキスト情報設定 ---
            with c2:
                # 削除ボタンを右上に
                col_title, col_del = st.columns([4, 1])
                with col_title:
                    st.caption("基本情報")
                with col_del:
                    if st.button("🗑", key=f"del_{idx}", help="リストから削除", type="secondary"):
                        remove_video(idx)
                        st.rerun()

                new_title = st.text_input("タイトル", value=info['custom_title'], key=f"title_{idx}")
                new_artist = st.text_input("アーティスト", value=info['custom_artist'], key=f"artist_{idx}")
                new_album = st.text_input("アルバム名", value=info['custom_album'], key=f"album_{idx}")
                
                # 状態更新
                st.session_state.video_infos[idx]['custom_title'] = new_title
                st.session_state.video_infos[idx]['custom_artist'] = new_artist
                st.session_state.video_infos[idx]['custom_album'] = new_album

            st.markdown('</div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    if c1.button("戻る", use_container_width=True):
        st.session_state.stage = 'input'
        st.rerun()
    if c2.button("ダウンロード開始", type="primary", use_container_width=True):
        st.session_state.stage = 'processing'
        st.rerun()

# 3. 処理 & 完了画面
if st.session_state.stage == 'processing':
    res, zip_d = process_download(st.session_state.video_infos)
    st.session_state.results = res
    st.session_state.zip_data = zip_d
    st.session_state.stage = 'finished'
    st.rerun()

if st.session_state.stage == 'finished':
    st.markdown('### 3. ダウンロード完了')
    
    if st.session_state.zip_data:
        st.download_button("ZIPで一括保存", st.session_state.zip_data, "music_files.zip", "application/zip", type="primary", use_container_width=True)
    
    st.markdown("---")
    for item in st.session_state.results:
        c1, c2 = st.columns([3, 1])
        c1.markdown(f"🎵 **{item['filename']}**")
        c2.download_button("保存", item['data'], item['filename'], item['mime'], key=f"dl_{item['filename']}")
    
    if st.button("最初に戻る"):
        st.session_state.stage = 'input'
        st.session_state.video_infos = []
        st.rerun()
