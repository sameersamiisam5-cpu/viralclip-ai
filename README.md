# 🎬 AI Clipping Tool — Viral 9:16 Shorts & Reels Engine

An intelligent automated clipping pipeline designed to take multi-hour YouTube streams (e.g., GTA VI marathons, esports, podcasts) and extract the highest-probability viral moments into vertical **9:16** format (1080x1920) with **karaoke-style dynamic animated subtitles**, ready for TikTok, YouTube Shorts, and Instagram Reels.

---

## ⚡ Core Architecture

1. **Replay Heatmap Extraction (Zero-Download Intelligence):**
   * Inspects YouTube audience retention and "Most Replayed" intensity before downloading the video.
   * Peak spikes pinpoint the exact moments viewers rewound to watch fails, screams, and big reveals.

2. **Stream-Slicing via HTTP Range Requests:**
   * Instead of downloading 10-30GB for a 6-hour stream, `yt-dlp` stream-slices **only the target 30–60 second clip** in seconds.

3. **Phase 2: Animated Karaoke Subtitles:**
   * Automatically extracts word-level millisecond timestamps from YouTube captions.
   * Compiles custom Advanced SubStation Alpha (`.ass`) karaoke scripts.
   * Highlights the actively spoken word in **Electric Yellow (Hormozi style)**, **Neon Green**, **Cyber Cyan**, or **Fire Orange** with a dynamic pop animation (`Impact` font, bold outline, drop shadow, positioned for vertical reels).

4. **FFmpeg 9:16 Reframer:**
   * **Ambient Blur Fill (Default):** Keeps the full 16:9 gameplay at native resolution centered, while dynamically zooming, blurring, and dimming the gameplay in the background to fill the 1080x1920 canvas. (Preserves radar, ammo, health bar, and HUD).
   * **Center Crop 9:16:** Direct vertical slice of the center action.

---

## 🚀 Quick Start

### Option 1: 1-Click Launch (Web Dashboard)
Double-click `start.bat` or run:
```bash
.\.venv\Scripts\python.exe run_server.py
```
Open your browser to: **http://localhost:8000**

1. Paste any YouTube stream / video URL.
2. Select your **Animated Subtitles Style** (🟡 Hormozi Yellow, 🟢 Neon Green, 🔵 Cyber Cyan, 🟠 Fire Orange).
3. Click **⚡ Analyze Stream**.
4. View the **Audience Retention Curve** and ranked viral opportunities.
5. Click **⚡ Render 9:16** to preview and download your reel with subtitles burned in.

---

### Option 2: CLI Power Mode
Directly extract the #1 viral moment with animated subtitles from terminal:
```bash
.\.venv\Scripts\python.exe cli.py "https://www.youtube.com/watch?v=..." --duration 45 --mode blur_padding --sub-style hormozi_yellow
```

---

## 📁 Project Structure
```
AI-cliping-tool/
├── .venv/                 # Dedicated Python 3.14 environment
├── downloads/             # Temp raw video segment slices & ASS subtitle files
├── output/                # Rendered 9:16 vertical videos with subtitles
├── src/
│   ├── analyzer.py        # Peak detection & virality scoring algorithm
│   ├── config.py          # Resolutions, directories, and thresholds
│   ├── downloader.py      # yt-dlp metadata, heatmap & stream slicer
│   ├── reframer.py        # FFmpeg 9:16 filter pipeline + ASS subtitle burn-in
│   └── subtitles.py       # Word-level timestamp parser & ASS karaoke generator
├── static/
│   └── index.html         # Cyberpunk dark-mode web dashboard
├── web_app.py             # FastAPI backend engine
├── cli.py                 # Command-line interface
├── run_server.py          # Server launcher
└── start.bat              # Windows 1-click launcher
```

---

## 🔮 Planned Upgrades
- [ ] Auto face-cam bounding box detection (Streamer cam on top + gameplay below).
- [ ] Automated kinetic subtitles & captions with Whisper word-level timestamps.
- [ ] Streamer scream / decibel spike detector for live streams without heatmaps.
