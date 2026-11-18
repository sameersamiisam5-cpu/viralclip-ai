import re
import subprocess
import shutil
from pathlib import Path
from typing import List, Tuple

class MusicDetector:
    def __init__(self, ffmpeg_bin: str = "ffmpeg"):
        self.ffmpeg_bin = shutil.which(ffmpeg_bin) or "ffmpeg"

    def detect_music_intervals(
        self,
        media_path: Path,
        min_duration_sec: float = 2.5,
        flatness_threshold: float = 0.115
    ) -> List[Tuple[float, float]]:
        """
        Scans an audio or video file using FFmpeg spectral stats to detect
        sustained background music / copyrighted tracks.
        Returns a list of (start_seconds, end_seconds) tuples where music was detected.
        """
        media_file = Path(media_path).resolve()
        if not media_file.exists():
            return []

        cmd = [
            self.ffmpeg_bin, "-y",
            "-i", str(media_file),
            "-vn",
            "-af", "aspectralstats=win_size=4096:measure=flatness,ametadata=mode=print",
            "-f", "null", "-"
        ]

        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False
            )
            raw_output = proc.stderr
        except Exception as e:
            print(f"[MusicDetector] Analysis error: {e}")
            return []

        time_re = re.compile(r"pts_time:([0-9\.]+)")
        flatness_re = re.compile(r"lavfi\.aspectralstats\.1\.flatness=([0-9\.]+)")

        current_time = 0.0
        frames = []

        for line in raw_output.splitlines():
            tm = time_re.search(line)
            if tm:
                try:
                    current_time = float(tm.group(1))
                except ValueError:
                    pass
            fm = flatness_re.search(line)
            if fm:
                try:
                    flatness = float(fm.group(1))
                    is_music = flatness > flatness_threshold
                    frames.append((current_time, is_music))
                except ValueError:
                    pass

        if not frames:
            return []

        # Find continuous music spans
        intervals = []
        in_music = False
        start_t = 0.0

        for t, is_m in frames:
            if is_m and not in_music:
                in_music = True
                start_t = t
            elif not is_m and in_music:
                in_music = False
                if (t - start_t) >= min_duration_sec:
                    intervals.append((round(start_t, 2), round(t, 2)))

        if in_music and (frames[-1][0] - start_t) >= min_duration_sec:
            intervals.append((round(start_t, 2), round(frames[-1][0], 2)))

        # Merge closely spaced music segments (gap <= 1.2s)
        merged = []
        for iv in intervals:
            if not merged:
                merged.append(iv)
            else:
                prev_s, prev_e = merged[-1]
                if iv[0] - prev_e <= 1.2:
                    merged[-1] = (prev_s, iv[1])
                else:
                    merged.append(iv)

        if merged:
            print(f"[MusicDetector] ⚠️ Detected {len(merged)} copyrighted music interval(s): {merged}")
        else:
            print("[MusicDetector] ✔ Clean speech detected: No background music found.")

        return merged

    def build_mute_filter(self, music_intervals: List[Tuple[float, float]]) -> str:
        """
        Builds an FFmpeg volume mute filter with smooth zeroing for all detected music intervals.
        """
        if not music_intervals:
            return ""

        conditions = []
        for start_t, end_t in music_intervals:
            # Pad by 0.15s to guarantee full acoustic fingerprint is obscured
            pad_s = max(0.0, start_t - 0.15)
            pad_e = end_t + 0.15
            conditions.append(f"between(t,{pad_s:.2f},{pad_e:.2f})")

        combined_condition = "+".join(conditions)
        return f"volume=enable='{combined_condition}':volume=0:eval=frame"
