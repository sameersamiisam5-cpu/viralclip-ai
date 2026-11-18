import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List
import yt_dlp
from src.config import DOWNLOADS_DIR

BROWSER_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

class YouTubeDownloader:
    def __init__(self, ffmpeg_bin: str = "ffmpeg"):
        self.ffmpeg_bin = shutil.which(ffmpeg_bin) or "ffmpeg"
        self.node_path = shutil.which("node") or r"C:\Program Files\nodejs\node.exe"
        self.js_runtimes = {'node': {'path': self.node_path}} if Path(self.node_path).exists() else {}

        self.ydl_opts_info = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'skip_download': True,
            'js_runtimes': self.js_runtimes,
            'remote_components': ['ejs:github'],
        }

    def get_video_info(self, url: str) -> Dict[str, Any]:
        """
        Extract video metadata, thumbnail, duration, title,
        and YouTube Replay Heatmap without downloading the video.
        """
        with yt_dlp.YoutubeDL(self.ydl_opts_info) as ydl:
            info = ydl.extract_info(url, download=False)
            
        heatmap = info.get('heatmap') or []
        
        return {
            'id': info.get('id'),
            'title': info.get('title'),
            'duration': info.get('duration', 0),
            'uploader': info.get('uploader'),
            'thumbnail': info.get('thumbnail'),
            'view_count': info.get('view_count'),
            'heatmap': heatmap,
            'webpage_url': info.get('webpage_url', url),
        }

    def download_clip_section(self, url: str, start_sec: float, end_sec: float, output_filename: Optional[str] = None) -> Path:
        """
        Ultra-fast & resilient stream-slice using FFmpeg input seeking over direct streams.
        Equipped with browser user-agent spoofing, auto-reconnect, and multi-format fallbacks.
        """
        if not output_filename:
            output_filename = f"clip_{int(start_sec)}_{int(end_sec)}.mp4"
            
        output_path = DOWNLOADS_DIR / output_filename
        if output_path.exists():
            output_path.unlink()

        # Step 1: Extract fresh format URLs
        with yt_dlp.YoutubeDL(self.ydl_opts_info) as ydl:
            info = ydl.extract_info(url, download=False)

        formats = info.get('formats', [])
        duration_sec = max(1.0, end_sec - start_sec)
        start_str = f"{round(start_sec, 2)}"
        dur_str = f"{round(duration_sec, 2)}"

        # Build prioritized format candidates to guarantee true HD (1080p/720p) quality first
        candidates: List[Dict[str, Any]] = []

        # Step 1: Find best available standalone audio track (prefer format 140 AAC 128k, then Opus)
        best_audio_url = None
        for f in formats:
            if not f.get('url'):
                continue
            fid = f.get('format_id', '')
            if fid.startswith('sb') or fid in ('233', '234') or f.get('ext') == 'mhtml':
                continue
            if f.get('acodec') and f.get('acodec') != 'none' and f.get('vcodec') == 'none':
                if fid == '140':
                    best_audio_url = f['url']
                    break
                elif not best_audio_url:
                    best_audio_url = f['url']

        # Step 2: Prioritize 1080p 60fps & 720p 60fps HLS streams + HLS AAC Audio
        hls_1080 = None
        hls_720 = None
        hls_audio = None
        for f in formats:
            if not f.get('url'):
                continue
            fid = f.get('format_id', '')
            proto = f.get('protocol', '')
            vcodec = f.get('vcodec', 'none')
            height = f.get('height') or 0
            if fid.startswith('sb') or f.get('ext') == 'mhtml':
                continue
            if 'm3u8' in proto:
                if vcodec != 'none':
                    if height >= 1080 and not hls_1080:
                        hls_1080 = f['url']
                    elif height >= 720 and not hls_720:
                        hls_720 = f['url']
                elif fid in ('234', '233') or f.get('resolution') == 'audio only':
                    if not hls_audio or fid == '234':
                        hls_audio = f['url']

        chosen_hls = hls_1080 or hls_720
        if chosen_hls:
            res_label = "1080p 60fps" if chosen_hls == hls_1080 else "720p 60fps"
            candidates.append({
                'video_url': chosen_hls,
                'audio_url': hls_audio or best_audio_url,
                'desc': f"HLS HD Stream ({res_label})"
            })

        # Step 3: HTTPS DASH HD stream pairs (1080p or 720p)
        dash_1080 = None
        dash_720 = None
        for f in formats:
            if not f.get('url'):
                continue
            fid = f.get('format_id', '')
            vcodec = f.get('vcodec', 'none')
            height = f.get('height') or 0
            if fid.startswith('sb') or f.get('ext') == 'mhtml' or fid in ('233', '234'):
                continue
            if vcodec != 'none' and f.get('acodec') == 'none':
                if height >= 1080 and not dash_1080:
                    dash_1080 = f['url']
                elif height >= 720 and not dash_720:
                    dash_720 = f['url']

        chosen_dash = dash_1080 or dash_720
        if chosen_dash:
            res_label = "1080p" if chosen_dash == dash_1080 else "720p"
            candidates.append({
                'video_url': chosen_dash,
                'audio_url': best_audio_url,
                'desc': f"HTTPS DASH HD Stream ({res_label})"
            })

        # Step 4: Progressive HD formats ONLY (height >= 720, e.g. Format 22)
        for f in formats:
            if f.get('vcodec') != 'none' and f.get('acodec') != 'none' and f.get('url'):
                h = f.get('height') or 0
                if h >= 720:
                    candidates.append({
                        'video_url': f['url'],
                        'audio_url': None,
                        'desc': f"Progressive HD {f.get('format_id')} ({h}p)"
                    })
                    break

        # Step 5: Emergency Fallback ONLY (Standard Def 360p e.g. Format 18)
        for f in formats:
            if f.get('vcodec') != 'none' and f.get('acodec') != 'none' and f.get('url'):
                candidates.append({
                    'video_url': f['url'],
                    'audio_url': None,
                    'desc': f"Progressive SD Fallback {f.get('format_id')} ({f.get('height', 'unknown')}p)"
                })
                break

        # Ultimate fallback candidate
        if info.get('url') and not candidates:
            candidates.append({
                'video_url': info['url'],
                'audio_url': None,
                'desc': "Default info URL"
            })

        if not candidates:
            raise RuntimeError("Could not find any playable stream formats for this video.")

        # Step 2: Attempt streaming slice with auto-reconnect & browser user-agent
        last_error = ""
        for cand in candidates:
            v_url = cand['video_url']
            a_url = cand['audio_url']
            desc = cand['desc']
            print(f"[YouTubeDownloader] Attempting stream slice via {desc}...")

            cmd = [
                self.ffmpeg_bin, "-y",
                "-user_agent", BROWSER_USER_AGENT,
                "-reconnect", "1",
                "-reconnect_at_eof", "1",
                "-reconnect_streamed", "1",
                "-reconnect_delay_max", "5",
                "-ss", start_str,
                "-t", dur_str,
                "-i", v_url
            ]

            if a_url:
                cmd.extend([
                    "-user_agent", BROWSER_USER_AGENT,
                    "-reconnect", "1",
                    "-reconnect_at_eof", "1",
                    "-reconnect_streamed", "1",
                    "-reconnect_delay_max", "5",
                    "-ss", start_str,
                    "-t", dur_str,
                    "-i", a_url,
                    "-map", "0:v:0",
                    "-map", "1:a:0?",
                    "-c:v", "libx264",
                    "-preset", "ultrafast",
                    "-crf", "18",
                    "-threads", "0",
                    "-c:a", "aac",
                    "-b:a", "256k",
                    "-max_muxing_queue_size", "2048",
                    str(output_path)
                ])
            else:
                cmd.extend([
                    "-c:v", "libx264",
                    "-preset", "ultrafast",
                    "-crf", "18",
                    "-threads", "0",
                    "-c:a", "aac",
                    "-b:a", "256k",
                    str(output_path)
                ])

            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 10000:
                print(f"[YouTubeDownloader] ✔ Successfully sliced via {desc} ({output_path.stat().st_size} bytes)")
                return output_path
            else:
                last_error = result.stderr[-300:] if result.stderr else "Unknown error"
                print(f"[YouTubeDownloader] Candidate {desc} failed: {last_error[:120]}... Trying next format.")
                if output_path.exists():
                    output_path.unlink()

        raise RuntimeError(f"FFmpeg stream slice failed across all formats:\n{last_error}")

    @staticmethod
    def _format_timestamp(seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:05.2f}"
