import os
import sys
import shutil
import subprocess

def download_video(urls, output_format, audio_quality):
    output_dir = "downloads"
    os.makedirs(output_dir, exist_ok=True)

    if shutil.which("ffmpeg") is None:
        print("Error: ffmpeg is not installed.")
        sys.exit(1)

    url_list = [u.strip() for u in urls.splitlines() if u.strip()]
    if not url_list: return

    for u in url_list:
        print(f"Downloading: {u}")
        cmd = [
            'yt-dlp', '-x',
            '--audio-format', output_format,
            '--audio-quality', str(audio_quality),
            '-o', f"{output_dir}/%(title)s.%(ext)s",
            '--embed-thumbnail', '--add-metadata',
            u
        ]
        if output_format == 'wav': # WAVは埋め込み不可のため除外
            cmd.remove('--embed-thumbnail')
            cmd.remove('--add-metadata')
            
        subprocess.run(cmd)

if __name__ == "__main__":
    download_video(
        os.environ.get("INPUT_URLS", ""),
        os.environ.get("INPUT_FORMAT", "mp3"),
        os.environ.get("INPUT_QUALITY", "0")
    )
