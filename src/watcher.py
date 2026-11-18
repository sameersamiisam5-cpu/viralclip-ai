import time
import shutil
import threading
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
import yt_dlp

from src.config import DOWNLOADS_DIR, OUTPUT_DIR
from src.downloader import YouTubeDownloader
from src.analyzer import ViralAnalyzer
from src.reframer import VideoReframer
from src.subtitles import SubtitleEngine

class LiveStreamWatcher:
    def __init__(self):
        self.is_running = False
        self.stream_url: Optional[str] = None
        self.stream_title: Optional[str] = None
        self.uploader: Optional[str] = None
        self.status: str = "Idle"
        self.sensitivity: float = 75.0  # Virality trigger threshold
        self.auto_render: bool = True
        self.streamer_credit: Optional[str] = None
        self.captured_moments: List[Dict[str, Any]] = []
        self.thread: Optional[threading.Thread] = None
        self.ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
        self.downloader = YouTubeDownloader()
        self.analyzer = ViralAnalyzer(target_duration=45)
        self.reframer = VideoReframer()
        self.subtitle_engine = SubtitleEngine()
        self.stats = {
            "started_at": None,
            "chunks_scanned": 0,
            "clips_produced": 0,
            "last_check": None
        }

    def start(self, url: str, sensitivity: float = 75.0, auto_render: bool = True, streamer_credit: Optional[str] = None):
        if self.is_running:
            return {"status": "error", "message": "Watcher is already running"}

        self.stream_url = url
        self.sensitivity = sensitivity
        self.auto_render = auto_render
        self.streamer_credit = streamer_credit
        self.is_running = True
        self.status = "Initializing Stream Watcher..."
        self.stats["started_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.stats["chunks_scanned"] = 0
        self.stats["clips_produced"] = 0

        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        return {"status": "started", "url": url}

    def stop(self):
        self.is_running = False
        self.status = "Stopped"
        return {"status": "stopped"}

    def get_status(self) -> Dict[str, Any]:
        return {
            "is_running": self.is_running,
            "status": self.status,
            "stream_title": self.stream_title,
            "uploader": self.uploader,
            "stream_url": self.stream_url,
            "stats": self.stats,
            "recent_captures": self.captured_moments[-10:]
        }

    def _run_loop(self):
        print(f"\n[LiveWatcher] Starting Live Stream Watcher on: {self.stream_url}")
        self.status = "Resolving live stream source..."

        try:
            info = self.downloader.get_video_info(self.stream_url)
            self.stream_title = info.get("title", "Live Stream")
            self.uploader = info.get("uploader", "Streamer")
            if not self.streamer_credit:
                self.streamer_credit = f"@{self.uploader.replace(' ', '')}"
        except Exception as e:
            self.status = f"Failed to resolve stream info: {e}"
            self.is_running = False
            return

        window_duration = 50.0  # Scan in 50-second rolling sliding windows
        last_clip_timestamp = 0.0

        while self.is_running:
            try:
                self.status = f"🔴 Watching Live Stream: {self.uploader} ({self.stream_title[:30]}...)"
                self.stats["last_check"] = datetime.now().strftime("%H:%M:%S")
                self.stats["chunks_scanned"] += 1

                # Re-fetch latest duration / progress
                try:
                    current_info = self.downloader.get_video_info(self.stream_url)
                    live_duration = current_info.get("duration", 0)
                except Exception:
                    live_duration = 0

                if live_duration < window_duration:
                    time.sleep(15)
                    continue

                # Target the latest 50-second chunk
                start_sec = max(0.0, live_duration - window_duration)
                end_sec = live_duration

                if start_sec <= last_clip_timestamp:
                    time.sleep(15)
                    continue

                temp_chunk_name = f"watcher_chunk_{int(time.time())}.mp4"
                temp_chunk_path = DOWNLOADS_DIR / temp_chunk_name

                # Stream-slice the latest rolling chunk
                raw_path = self.downloader.download_clip_section(
                    url=self.stream_url,
                    start_sec=start_sec,
                    end_sec=end_sec,
                    output_filename=temp_chunk_name
                )

                # Scan chunk audio energy for excitement surge (screams, laughter, hype)
                energy_points = self.analyzer.scan_audio_energy(str(raw_path), duration=window_duration)
                spikes = self.analyzer.detect_audio_spikes(energy_points)

                if spikes:
                    top_spike = spikes[0]
                    score = top_spike["score"]
                    surge = top_spike["surge"]

                    print(f"[LiveWatcher] Scanned latest window: Peak Virality Score = {score}% (+{surge}dB surge)")

                    if score >= self.sensitivity:
                        self.status = f"🚨 VIRAL SURGE DETECTED ({score}%)! Auto-rendering 9:16 Reel..."
                        last_clip_timestamp = end_sec
                        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                        output_filename = f"live_clip_{self.uploader.replace(' ', '_')}_{timestamp_str}.mp4"

                        # Snap to natural speech pauses
                        snap_start, snap_end = self.analyzer.snap_boundaries_to_silence(
                            start_sec, end_sec, energy_points
                        )

                        # Generate animated subtitles via audio transcription
                        clip_dur = end_sec - start_sec
                        words = self.subtitle_engine.transcribe_audio_fallback(raw_path, clip_duration=clip_dur)
                        ass_path = None
                        if words or self.streamer_credit:
                            phrases = self.subtitle_engine.group_into_phrases(words, max_words_per_phrase=3) if words else []
                            ass_path = DOWNLOADS_DIR / f"watcher_{timestamp_str}.ass"
                            self.subtitle_engine.generate_ass_file(
                                phrases=phrases,
                                output_ass_path=ass_path,
                                style="hormozi_yellow",
                                streamer_credit=self.streamer_credit,
                                hook_headline="🔥 LIVE STREAM MOMENT!"
                            )

                        # Render 9:16 vertical Reel
                        reel_path = self.reframer.convert_to_9_16(
                            input_video_path=raw_path,
                            mode="blur_padding",
                            output_filename=output_filename,
                            subtitles_ass_path=ass_path,
                            anti_copyright=True
                        )

                        self.stats["clips_produced"] += 1
                        capture_event = {
                            "filename": output_filename,
                            "url": f"/output/{output_filename}",
                            "timestamp": datetime.now().strftime("%H:%M:%S"),
                            "score": score,
                            "surge": surge,
                            "stream_time": f"{int(start_sec)}s - {int(end_sec)}s"
                        }
                        self.captured_moments.append(capture_event)
                        print(f"[LiveWatcher] 🎬 Viral Reel Created: {output_filename} ({reel_path.stat().st_size} bytes)")

                # Clean up temp raw chunk
                if raw_path.exists():
                    try:
                        raw_path.unlink()
                    except Exception:
                        pass

                # Sleep before next rolling window check
                time.sleep(20)

            except Exception as e:
                print(f"[LiveWatcher] Error in watcher loop: {e}")
                time.sleep(15)

        self.status = "Stopped"
