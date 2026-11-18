import math
import struct
import shutil
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

class ViralAnalyzer:
    def __init__(self, target_duration: int = 45, min_gap_seconds: int = 90, ffmpeg_bin: str = "ffmpeg"):
        self.target_duration = target_duration
        self.min_gap_seconds = min_gap_seconds
        self.ffmpeg_bin = shutil.which(ffmpeg_bin) or "ffmpeg"

    def scan_audio_energy(
        self,
        audio_source: str,
        duration: Optional[float] = None,
        sample_rate: int = 8000
    ) -> List[Dict[str, Any]]:
        """
        Fast stream-scans audio without decoding full video.
        Calculates RMS energy (decibels) per 0.5s bucket using pure Python.
        Detects screams, laughter, table slams, and high excitement.
        """
        cmd = [self.ffmpeg_bin, "-y"]
        if duration and duration > 0:
            cmd.extend(["-t", str(duration)])
        cmd.extend([
            "-i", str(audio_source),
            "-vn",
            "-ar", str(sample_rate),
            "-ac", "1",
            "-f", "s16le",
            "pipe:1"
        ])

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL
            )
        except Exception as e:
            print(f"[ViralAnalyzer] Audio energy scan failed: {e}")
            return []

        bucket_samples = int(sample_rate * 0.5)  # 0.5 sec buckets
        bytes_per_bucket = bucket_samples * 2   # 16-bit = 2 bytes per sample

        points = []
        t = 0.0

        while True:
            raw = proc.stdout.read(bytes_per_bucket)
            if not raw or len(raw) < bytes_per_bucket:
                break
            
            n_samples = len(raw) // 2
            samples = struct.unpack(f"<{n_samples}h", raw)
            
            # Root Mean Square (RMS) energy
            sum_sq = sum(s * s for s in samples)
            rms = math.sqrt(sum_sq / n_samples)
            db = 20.0 * math.log10(rms + 1e-6)
            
            points.append({
                "time": round(t, 2),
                "db": round(db, 2)
            })
            t += 0.5

        proc.stdout.close()
        proc.wait()
        return points

    def detect_audio_spikes(
        self,
        energy_points: List[Dict[str, Any]],
        window_sec: float = 10.0
    ) -> List[Dict[str, Any]]:
        """
        Detects relative loudness surges above the rolling background average.
        Streamer screaming or laughing creates massive relative spikes (+12dB to +20dB).
        """
        if not energy_points or len(energy_points) < 5:
            return []

        half_win = int((window_sec / 0.5) / 2)
        scored_spikes = []

        dbs = [p["db"] for p in energy_points]
        min_db = min(dbs)
        max_db = max(dbs)
        db_range = max_db - min_db if max_db > min_db else 1.0

        for i, pt in enumerate(energy_points):
            w_start = max(0, i - half_win)
            w_end = min(len(energy_points), i + half_win + 1)
            local_baseline = sum(dbs[w_start:w_end]) / max(1, (w_end - w_start))

            # Surge is how much louder this moment is compared to surrounding talk/gameplay
            surge = pt["db"] - local_baseline
            
            # Normalized 0-100 score based on absolute loudness & relative surge
            norm_db = ((pt["db"] - min_db) / db_range) * 50.0
            norm_surge = min(50.0, max(0.0, surge * 3.5))
            combined_score = round(min(100.0, norm_db + norm_surge), 1)

            if surge > 2.0:  # Noticeable energy spike
                scored_spikes.append({
                    "time": pt["time"],
                    "db": pt["db"],
                    "surge": round(surge, 2),
                    "score": combined_score
                })

        # Sort by virality excitement score descending
        return sorted(scored_spikes, key=lambda s: s["score"], reverse=True)

    def snap_boundaries_to_silence(
        self,
        proposed_start: float,
        proposed_end: float,
        energy_points: List[Dict[str, Any]],
        search_radius: float = 2.5
    ) -> Tuple[float, float]:
        """
        Snaps proposed cut window to natural speech pauses.
        Prevents cutting off sentences mid-word.
        """
        if not energy_points:
            return proposed_start, proposed_end

        # Search for minimum loudness (speech pause/valley) around proposed start
        start_candidates = [
            p for p in energy_points
            if abs(p["time"] - proposed_start) <= search_radius
        ]
        best_start = proposed_start
        if start_candidates:
            quietest = min(start_candidates, key=lambda p: p["db"])
            # Start 0.1s after the silence ends
            best_start = max(0.0, round(quietest["time"] + 0.1, 1))

        # Search for speech pause around proposed end
        end_candidates = [
            p for p in energy_points
            if abs(p["time"] - proposed_end) <= search_radius
        ]
        best_end = proposed_end
        if end_candidates:
            quietest = min(end_candidates, key=lambda p: p["db"])
            best_end = round(quietest["time"], 1)

        # Enforce minimum sensible duration
        if best_end - best_start < 20.0:
            best_start = proposed_start
            best_end = proposed_end

        return best_start, best_end

    def analyze_hybrid(
        self,
        heatmap: List[Dict[str, Any]],
        total_duration: float,
        audio_source: Optional[str] = None,
        top_n: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Multi-Modal Virality Engine:
        Combines Audience Replay Heatmap + Audio Energy / Scream Detector.
        If Heatmap is missing (e.g. fresh Day-1 GTA VI stream), Audio Energy becomes primary!
        Also detects continuous 10-20 min mission blocks when target_duration >= 180s.
        """
        # Continuous Mission / Episode Mode (10m, 15m, 20m)
        if self.target_duration >= 180:
            return self.find_continuous_mission_window(
                heatmap=heatmap,
                total_duration=total_duration,
                window_sec=float(self.target_duration),
                top_n=top_n
            )

        has_heatmap = bool(heatmap and len(heatmap) >= 5)
        energy_points = []
        audio_spikes = []

        if audio_source:
            try:
                energy_points = self.scan_audio_energy(audio_source, duration=min(total_duration, 1800))
                audio_spikes = self.detect_audio_spikes(energy_points)
            except Exception as e:
                print(f"[ViralAnalyzer] Audio spike scan failed: {e}")

        # Case 1: Heatmap available
        if has_heatmap:
            heatmap_candidates = self.analyze_heatmap(heatmap, total_duration, top_n=top_n * 2)
            
            # Boost candidate scores if audio excitement peaks near the heatmap peak
            for c in heatmap_candidates:
                peak_t = c["peak_time"]
                near_spikes = [s for s in audio_spikes if abs(s["time"] - peak_t) <= 15.0]
                if near_spikes:
                    top_spike = near_spikes[0]
                    # Blend 60% heatmap + 40% audio excitement
                    c["virality_score"] = round((c["virality_score"] * 0.6) + (top_spike["score"] * 0.4), 1)
                    c["trigger"] = f"Replay + Scream ({top_spike['surge']}dB surge)"
                else:
                    c["trigger"] = "Audience Replay Heatmap"

                # Apply smart boundary snapping to natural speech pauses
                if energy_points:
                    s_snap, e_snap = self.snap_boundaries_to_silence(c["start_time"], c["end_time"], energy_points)
                    c["start_time"] = s_snap
                    c["end_time"] = e_snap
                    c["duration"] = round(e_snap - s_snap, 1)
                    c["start_formatted"] = self._format_timestamp(s_snap)
                    c["end_formatted"] = self._format_timestamp(e_snap)

            # Re-sort by boosted virality score
            ranked = sorted(heatmap_candidates, key=lambda x: x["virality_score"], reverse=True)[:top_n]
            for idx, r in enumerate(ranked):
                r["rank"] = idx + 1
            return ranked

        # Case 2: Fresh Stream (No Heatmap yet) -> Pure Audio Energy / Scream Detector!
        if audio_spikes:
            candidates = []
            for s in audio_spikes:
                peak_time = s["time"]
                lead_in = self.target_duration * 0.60
                raw_start = max(0.0, peak_time - lead_in)
                raw_end = min(total_duration, raw_start + self.target_duration)

                # Snap to silence
                start_time, end_time = self.snap_boundaries_to_silence(raw_start, raw_end, energy_points)

                # Ensure minimum separation between candidates
                is_overlapping = any(
                    abs(c["start_time"] - start_time) < (self.target_duration * 0.75)
                    for c in candidates
                )
                if not is_overlapping:
                    candidates.append({
                        "rank": len(candidates) + 1,
                        "peak_time": round(peak_time, 1),
                        "start_time": round(start_time, 1),
                        "end_time": round(end_time, 1),
                        "duration": round(end_time - start_time, 1),
                        "virality_score": s["score"],
                        "trigger": f"🔥 Streamer Loud Reaction (+{s['surge']}dB Surge)",
                        "start_formatted": self._format_timestamp(start_time),
                        "end_formatted": self._format_timestamp(end_time),
                        "peak_formatted": self._format_timestamp(peak_time),
                    })

                if len(candidates) >= top_n:
                    break

            if candidates:
                return candidates

        # Case 3: Ultimate fallback
        return self._generate_fallback_candidates(total_duration, top_n)

    def analyze_heatmap(self, heatmap: List[Dict[str, Any]], total_duration: float, top_n: int = 5) -> List[Dict[str, Any]]:
        """
        Pure Python virality analyzer for YouTube Replay Heatmaps.
        Finds local retention peaks without external C-extensions.
        """
        if not heatmap or len(heatmap) < 5:
            return self._generate_fallback_candidates(total_duration, top_n)

        points = []
        for pt in heatmap:
            mid_t = (pt['start_time'] + pt['end_time']) / 2.0
            val = float(pt['value'])
            points.append((mid_t, val))

        values = [p[1] for p in points]
        min_val = min(values)
        max_val = max(values)
        val_range = max_val - min_val if max_val > min_val else 1.0

        scored_points = []
        for mid_t, val in points:
            score = ((val - min_val) / val_range) * 100.0
            scored_points.append({
                'time': mid_t,
                'score': score
            })

        raw_peaks = []
        n = len(scored_points)
        for i in range(1, n - 1):
            prev_s = scored_points[i - 1]['score']
            curr_s = scored_points[i]['score']
            next_s = scored_points[i + 1]['score']

            if curr_s >= prev_s and curr_s >= next_s and curr_s > 10.0:
                raw_peaks.append(scored_points[i])

        if not raw_peaks:
            raw_peaks = sorted(scored_points, key=lambda p: p['score'], reverse=True)
        else:
            raw_peaks = sorted(raw_peaks, key=lambda p: p['score'], reverse=True)

        candidates = []
        for p in raw_peaks:
            peak_time = p['time']
            score = round(p['score'], 1)

            lead_in = self.target_duration * 0.60
            start_time = max(0.0, peak_time - lead_in)
            end_time = min(total_duration, start_time + self.target_duration)

            if end_time >= total_duration:
                start_time = max(0.0, total_duration - self.target_duration)

            is_overlapping = any(
                abs(c['start_time'] - start_time) < (self.target_duration * 0.8)
                for c in candidates
            )

            if not is_overlapping:
                candidates.append({
                    'rank': len(candidates) + 1,
                    'peak_time': round(peak_time, 1),
                    'start_time': round(start_time, 1),
                    'end_time': round(end_time, 1),
                    'duration': round(end_time - start_time, 1),
                    'virality_score': score,
                    'trigger': 'Audience Replay Heatmap',
                    'start_formatted': self._format_timestamp(start_time),
                    'end_formatted': self._format_timestamp(end_time),
                    'peak_formatted': self._format_timestamp(peak_time),
                })

            if len(candidates) >= top_n:
                break

        return candidates

    def _generate_fallback_candidates(self, total_duration: float, top_n: int = 5) -> List[Dict[str, Any]]:
        candidates = []
        if total_duration <= self.target_duration:
            candidates.append({
                'rank': 1,
                'peak_time': total_duration / 2.0,
                'start_time': 0.0,
                'end_time': total_duration,
                'duration': total_duration,
                'virality_score': 85.0,
                'trigger': 'Full Segment',
                'start_formatted': "00:00:00",
                'end_formatted': self._format_timestamp(total_duration),
                'peak_formatted': self._format_timestamp(total_duration / 2.0),
            })
            return candidates

        start_offset = min(60.0, total_duration * 0.05)
        available_range = total_duration - start_offset - self.target_duration
        step = max(self.min_gap_seconds, available_range / (top_n + 1))

        for i in range(top_n):
            start = start_offset + (i * step)
            end = min(total_duration, start + self.target_duration)
            if end > total_duration:
                break
            candidates.append({
                'rank': i + 1,
                'peak_time': round((start + end) / 2.0, 1),
                'start_time': round(start, 1),
                'end_time': round(end, 1),
                'duration': round(end - start, 1),
                'virality_score': round(75.0 - (i * 3.5), 1),
                'trigger': 'Pacing Interval',
                'start_formatted': self._format_timestamp(start),
                'end_formatted': self._format_timestamp(end),
                'peak_formatted': self._format_timestamp((start + end) / 2.0),
            })

        return candidates

    def find_continuous_mission_window(
        self,
        heatmap: List[Dict[str, Any]],
        total_duration: float,
        window_sec: float = 900.0,
        top_n: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Scans a multi-hour stream for the continuous 10-20 minute mission/story block
        with the highest cumulative viewer retention & continuous excitement density.
        """
        min_label = int(round(window_sec / 60))
        if total_duration <= window_sec:
            return [{
                "rank": 1,
                "peak_time": total_duration / 2.0,
                "start_time": 0.0,
                "end_time": total_duration,
                "duration": total_duration,
                "virality_score": 95.0,
                "trigger": f"🎬 Continuous {min_label}-Min Full Mission Video",
                "start_formatted": "00:00:00",
                "end_formatted": self._format_timestamp(total_duration),
                "peak_formatted": self._format_timestamp(total_duration / 2.0),
            }]

        points = []
        if heatmap and len(heatmap) >= 5:
            for pt in heatmap:
                mid_t = (pt['start_time'] + pt['end_time']) / 2.0
                val = float(pt['value'])
                points.append((mid_t, val))
        else:
            step = 30.0
            t = 0.0
            while t < total_duration:
                points.append((t, 50.0))
                t += step

        # Sliding window calculation across total_duration with 60-second step
        step_sec = 60.0
        max_start = max(0.0, total_duration - window_sec)
        num_steps = int(max_start / step_sec) + 1

        window_scores = []
        for i in range(num_steps):
            w_start = i * step_sec
            w_end = min(total_duration, w_start + window_sec)
            
            pts_in_window = [p[1] for p in points if w_start <= p[0] <= w_end]
            avg_score = (sum(pts_in_window) / len(pts_in_window)) if pts_in_window else 0.0
            
            best_pt = max([p for p in points if w_start <= p[0] <= w_end], key=lambda x: x[1], default=(w_start + (window_sec / 2), 0.0))

            window_scores.append({
                "start": w_start,
                "end": w_end,
                "score": avg_score,
                "peak_time": best_pt[0]
            })

        if window_scores:
            scores_val = [w["score"] for w in window_scores]
            min_s = min(scores_val)
            max_s = max(scores_val)
            s_range = max_s - min_s if max_s > min_s else 1.0
            for w in window_scores:
                w["norm_score"] = round(70.0 + (((w["score"] - min_s) / s_range) * 29.0), 1)

        sorted_windows = sorted(window_scores, key=lambda w: w["norm_score"], reverse=True)

        candidates = []
        for w in sorted_windows:
            start_t = round(w["start"], 1)
            end_t = round(w["end"], 1)
            
            is_overlap = any(
                abs(c["start_time"] - start_t) < (window_sec * 0.5)
                for c in candidates
            )
            if not is_overlap:
                candidates.append({
                    "rank": len(candidates) + 1,
                    "peak_time": round(w["peak_time"], 1),
                    "start_time": start_t,
                    "end_time": end_t,
                    "duration": round(end_t - start_t, 1),
                    "virality_score": w.get("norm_score", 85.0),
                    "trigger": f"🎬 Continuous {min_label}-Min Climax Mission / Arc",
                    "start_formatted": self._format_timestamp(start_t),
                    "end_formatted": self._format_timestamp(end_t),
                    "peak_formatted": self._format_timestamp(w["peak_time"]),
                })

            if len(candidates) >= top_n:
                break

        return candidates

    @staticmethod
    def _format_timestamp(seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
