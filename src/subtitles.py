import json
import shutil
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional
import yt_dlp
import speech_recognition as sr
from src.config import DOWNLOADS_DIR, BASE_DIR

HIGHLIGHT_COLORS = {
    "hormozi_yellow": "&H0000FFFF&",  # Bright Yellow (RGB: 255, 255, 0)
    "neon_green": "&H0000FF00&",      # Electric Green (RGB: 0, 255, 0)
    "cyber_cyan": "&H00FFFF00&",      # Vibrant Cyan (RGB: 0, 255, 255)
    "fire_orange": "&H000080FF&",     # Blaze Orange (RGB: 255, 128, 0)
}

class SubtitleEngine:
    def __init__(self, ffmpeg_bin: str = "ffmpeg"):
        self.ffmpeg_bin = shutil.which(ffmpeg_bin) or "ffmpeg"
        self.node_path = shutil.which("node") or r"C:\Program Files\nodejs\node.exe"
        self.js_runtimes = {'node': {'path': self.node_path}} if Path(self.node_path).exists() else {}

    def fetch_subtitles(self, url: str, video_id: str) -> Optional[Path]:
        output_template = str(DOWNLOADS_DIR / f"sub_{video_id}")
        ydl_opts = {
            'skip_download': True,
            'writeautomaticsub': True,
            'writesubtitles': True,
            'subtitleslangs': ['en.*', 'en', 'hi.*', 'hi'],
            'subtitlesformat': 'json3',
            'outtmpl': output_template,
            'quiet': True,
            'no_warnings': True,
            'js_runtimes': self.js_runtimes,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            candidates = list(DOWNLOADS_DIR.glob(f"sub_{video_id}*.json3"))
            if candidates:
                # Prioritize English subtitles (en-orig, en, en-US)
                en_candidates = [c for c in candidates if "en" in c.name.lower()]
                if en_candidates:
                    en_orig = [c for c in en_candidates if "orig" in c.name.lower()]
                    return en_orig[0] if en_orig else en_candidates[0]
                return candidates[0]
        except Exception:
            pass

        return None

    def transcribe_audio_fallback(self, video_clip_path: Path, clip_duration: float) -> List[Dict[str, Any]]:
        """
        Windowed Speech Alignment:
        Scans audio in 4.5s chunks to align words with creator voice bursts.
        """
        wav_path = DOWNLOADS_DIR / f"temp_{Path(video_clip_path).stem}.wav"
        try:
            cmd = [
                self.ffmpeg_bin, "-y",
                "-i", str(video_clip_path),
                "-vn",
                "-ar", "16000",
                "-ac", "1",
                str(wav_path)
            ]
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

            r = sr.Recognizer()
            window_size = 4.5
            offset = 0.0
            all_words = []

            with sr.AudioFile(str(wav_path)) as source:
                while offset < clip_duration:
                    chunk_dur = min(window_size, clip_duration - offset)
                    audio_chunk = r.record(source, duration=chunk_dur)

                    chunk_text = ""
                    for lang in ["hi-IN", "en-IN", "en-US"]:
                        try:
                            chunk_text = r.recognize_google(audio_chunk, language=lang)
                            if chunk_text:
                                break
                        except Exception:
                            continue

                    if chunk_text:
                        raw_words = chunk_text.split()
                        w_dur = max(0.3, (chunk_dur - 0.4) / len(raw_words))
                        for i, w in enumerate(raw_words):
                            w_st = round(offset + 0.2 + (i * w_dur), 2)
                            w_et = round(w_st + w_dur, 2)
                            all_words.append({
                                "text": w.upper(),
                                "start": w_st,
                                "end": w_et
                            })

                    offset += chunk_dur

            return all_words

        except Exception as e:
            print(f"[SubtitleEngine] Transcriber note: {e}")
            return []
        finally:
            if wav_path.exists():
                try:
                    wav_path.unlink()
                except Exception:
                    pass

    def parse_word_timestamps(
        self,
        json3_path: Path,
        clip_start_sec: float,
        clip_end_sec: float
    ) -> List[Dict[str, Any]]:
        if not json3_path or not json3_path.exists():
            return []

        try:
            with open(json3_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return []

        events = data.get("events", [])
        words = []

        for ev in events:
            t_start_ms = ev.get("tStartMs", 0)
            segs = ev.get("segs", [])

            for s in segs:
                utf8 = s.get("utf8", "")
                text = utf8.strip()
                if not text or text == "\n":
                    continue

                # Strip speaker markers and audio tags like [laughter], [music]
                clean_text = text.replace(">>", "").strip()
                if clean_text.startswith("[") and clean_text.endswith("]"):
                    continue
                if not clean_text:
                    continue

                t_offset_ms = s.get("tOffsetMs", 0)
                word_abs_sec = (t_start_ms + t_offset_ms) / 1000.0

                if clip_start_sec <= word_abs_sec <= clip_end_sec:
                    rel_start = max(0.0, word_abs_sec - clip_start_sec)
                    words.append({
                        "text": clean_text.upper(),
                        "start": rel_start,
                        "abs_time": word_abs_sec
                    })

        for i in range(len(words)):
            if i < len(words) - 1:
                gap = words[i + 1]["start"] - words[i]["start"]
                words[i]["end"] = words[i]["start"] + min(0.6, max(0.25, gap))
            else:
                words[i]["end"] = words[i]["start"] + 0.45

        return words

    def group_into_phrases(
        self,
        words: List[Dict[str, Any]],
        max_words_per_phrase: int = 3,
        max_pause_sec: float = 0.5
    ) -> List[Dict[str, Any]]:
        if not words:
            return []

        phrases = []
        current_phrase = []

        for w in words:
            if not current_phrase:
                current_phrase.append(w)
                continue

            last_w = current_phrase[-1]
            pause = w["start"] - last_w["end"]

            if len(current_phrase) >= max_words_per_phrase or pause > max_pause_sec:
                phrases.append({
                    "start": current_phrase[0]["start"],
                    "end": current_phrase[-1]["end"],
                    "words": current_phrase
                })
                current_phrase = [w]
            else:
                current_phrase.append(w)

        if current_phrase:
            phrases.append({
                "start": current_phrase[0]["start"],
                "end": current_phrase[-1]["end"],
                "words": current_phrase
            })

        return phrases

    def generate_ass_file(
        self,
        phrases: List[Dict[str, Any]],
        output_ass_path: Path,
        style: str = "hormozi_yellow",
        streamer_credit: Optional[str] = None,
        hook_headline: Optional[str] = None,
        is_landscape: bool = False
    ) -> Path:
        highlight_color = HIGHLIGHT_COLORS.get(style, HIGHLIGHT_COLORS["hormozi_yellow"])

        if is_landscape:
            # 16:9 Landscape Widescreen Styles (1920x1080)
            res_x, res_y = 1920, 1080
            styles = [
                # Subtitles: Bottom Center (MarginV=80, 52pt Impact)
                "Style: Default,Impact,52,&H00FFFFFF,&H0000FFFF,&H00000000,&H90000000,-1,0,0,0,100,100,1,0,1,5,3,2,60,60,80,1",
                # Watermark: Top-Right Corner (Alignment: 9, MarginR=40, MarginV=30, semi-transparent)
                "Style: CreditBadge,Arial Black,26,&H40FFFFFF,&H00000000,&H80000000,&H80000000,0,0,0,0,100,100,1,0,1,2,1,9,40,40,30,1",
                # Mission Chapter Title: Top Center (Alignment: 8, MarginV=60)
                "Style: HookTitle,Impact,52,&H0000FFFF,&H00000000,&H00000000,&HA0000000,-1,0,0,0,100,100,2,0,1,5,3,8,40,40,60,1"
            ]
        else:
            # 9:16 Vertical Reel Styles (1080x1920)
            res_x, res_y = 1080, 1920
            styles = [
                # Dialogue Style: 88pt Impact, 8px Outline, 4px Shadow, MarginV=420
                "Style: Default,Impact,88,&H00FFFFFF,&H0000FFFF,&H00000000,&H90000000,-1,0,0,0,100,100,2,0,1,8,4,2,50,50,420,1",
                # Streamer Credit Badge Style: Top Center (Alignment: 8, MarginV=140)
                "Style: CreditBadge,Arial Black,36,&H00FFFFFF,&H00000000,&H00000000,&H80000000,-1,0,0,0,100,100,1,0,1,3,2,8,40,40,140,1",
                # Hook Headline Style: Top Center below badge (Alignment: 8, MarginV=220)
                "Style: HookTitle,Impact,54,&H0000FFFF,&H00000000,&H00000000,&HA0000000,-1,0,0,0,100,100,1,0,1,6,3,8,40,40,210,1"
            ]

        ass_content = [
            "[Script Info]",
            "ScriptType: v4.00+",
            f"PlayResX: {res_x}",
            f"PlayResY: {res_y}",
            "ScaledBorderAndShadow: yes",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            *styles,
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
        ]

        # Add persistent Streamer Credit Badge if specified
        if streamer_credit:
            credit_clean = streamer_credit.strip()
            if not credit_clean.startswith("@"):
                credit_clean = f"@{credit_clean}"
            ass_content.append(
                f"Dialogue: 1,0:00:00.00,9:59:59.99,CreditBadge,,0,0,0,,{{\\c&H00F0FF&}}STREAMER: {{\\c&HFFFFFF&}}{credit_clean}"
            )

        # Add Hook Headline or Mission Title
        if hook_headline and hook_headline.strip():
            headline_clean = hook_headline.strip().upper()
            if is_landscape:
                # In landscape mission mode, chapter title fades in and out in first 8 seconds
                ass_content.append(
                    f"Dialogue: 1,0:00:01.00,0:00:08.00,HookTitle,,0,0,0,,{{\\fad(600,600)}}{{\\c&H0000FFFF&}}{headline_clean}"
                )
            else:
                # In vertical mode, headline stays visible throughout
                ass_content.append(
                    f"Dialogue: 1,0:00:00.00,9:59:59.99,HookTitle,,0,0,0,,{{\\c&H0000FFFF&}}{headline_clean}"
                )

        for phrase in phrases:
            words = phrase.get("words") or [{"start": phrase.get("start", 0.0), "end": phrase.get("end", 0.0), "text": phrase.get("text", "")}]
            p_end = phrase.get("end", words[-1]["start"] + 0.6)

            for active_idx, active_word in enumerate(words):
                w_start = active_word["start"]
                if active_idx < len(words) - 1:
                    w_end = words[active_idx + 1]["start"]
                else:
                    w_end = p_end

                if w_end <= w_start:
                    w_end = w_start + 0.35

                w_start_str = self._format_ass_time(w_start)
                w_end_str = self._format_ass_time(w_end)

                parts = []
                for idx, w in enumerate(words):
                    if idx == active_idx:
                        # Spoken active word: 125% pop scale and vibrant highlight
                        parts.append(f"{{\\c{highlight_color}\\fscx125\\fscy125}}{w['text']}{{\\r}}")
                    else:
                        # Companion phrase words: clean bold white
                        parts.append(f"{{\\c&H00FFFFFF&\\fscx100\\fscy100}}{w['text']}{{\\r}}")

                dialogue_text = " ".join(parts)
                ass_content.append(f"Dialogue: 0,{w_start_str},{w_end_str},Default,,0,0,0,,{dialogue_text}")

        output_ass_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_ass_path, "w", encoding="utf-8") as f:
            f.write("\n".join(ass_content))

        return output_ass_path

    @staticmethod
    def _format_ass_time(seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        sec_int = int(secs)
        centisecs = int(round((secs - sec_int) * 100))
        if centisecs >= 100:
            centisecs = 99
        return f"{hours}:{minutes:02d}:{sec_int:02d}.{centisecs:02d}"
