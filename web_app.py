import os
import shutil
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel

from src.config import OUTPUT_DIR, DOWNLOADS_DIR
from src.downloader import YouTubeDownloader
from src.analyzer import ViralAnalyzer
from src.reframer import VideoReframer
from src.subtitles import SubtitleEngine
from src.watcher import LiveStreamWatcher
from src.uploader import YouTubeUploader, TOKEN_FILE, SECRETS_FILE
from src.safety_scanner import SafetyScanner

app = FastAPI(title="AI Clipping Tool - Viral 9:16 Engine")

# Mount output folder for video playback & download
app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")

downloader = YouTubeDownloader()
reframer = VideoReframer()
subtitle_engine = SubtitleEngine()
live_watcher = LiveStreamWatcher()
youtube_uploader = YouTubeUploader()

CAPTIONS_CACHE = {}

class AnalyzeRequest(BaseModel):
    url: str
    target_duration: int = 45
    top_n: int = 5

class ClipRequest(BaseModel):
    url: str
    video_id: str
    start_sec: float
    end_sec: float
    mode: str = "blur_padding"
    rank: int = 1
    enable_subtitles: bool = True
    subtitle_style: str = "hormozi_yellow"
    anti_copyright: bool = True
    auto_mute_music: bool = True
    streamer_credit: Optional[str] = None
    hook_headline: Optional[str] = None

class WatcherStartRequest(BaseModel):
    url: str
    sensitivity: float = 75.0
    auto_render: bool = True

class YouTubeSetupRequest(BaseModel):
    client_id: str
    client_secret: str

class YouTubeUploadRequest(BaseModel):
    filename: str
    title: str
    description: str
    tags: Optional[str] = None
    privacy: str = "public"
    streamer_credit: Optional[str] = None

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)

@app.post("/api/watcher/start")
async def start_watcher(req: WatcherStartRequest):
    res = live_watcher.start(
        url=req.url,
        sensitivity=req.sensitivity,
        auto_render=req.auto_render,
        streamer_credit=req.streamer_credit
    )
    return res

@app.post("/api/watcher/stop")
async def stop_watcher():
    return live_watcher.stop()

@app.get("/api/watcher/status")
async def get_watcher_status():
    return live_watcher.get_status()

@app.get("/api/library")
async def get_library():
    try:
        clips = []
        for file in sorted(OUTPUT_DIR.glob("*.mp4"), key=os.path.getmtime, reverse=True):
            clips.append({
                "filename": file.name,
                "url": f"/output/{file.name}",
                "size_mb": round(file.stat().st_size / (1024 * 1024), 2),
                "modified": os.path.getmtime(file)
            })
        return {"success": True, "clips": clips}
    except Exception as e:
        return {"success": False, "error": str(e), "clips": []}

@app.post("/api/analyze")
async def analyze_video(req: AnalyzeRequest):
    try:
        print(f"\n[API] Analyzing: {req.url}")
        info = downloader.get_video_info(req.url)
        analyzer = ViralAnalyzer(target_duration=req.target_duration)
        
        # Multi-Modal Hybrid Analyzer: Combines Heatmap + Audio Screams/Excitement + Smart Speech Snapping
        candidates = analyzer.analyze_hybrid(
            heatmap=info.get("heatmap", []),
            total_duration=info.get("duration", 0),
            audio_source=info.get("webpage_url") or req.url,
            top_n=req.top_n
        )
        
        # Pre-fetch subtitles if possible
        json3_path = subtitle_engine.fetch_subtitles(req.url, info["id"])
        if json3_path:
            CAPTIONS_CACHE[info["id"]] = json3_path

        # Automated Streamer Copyright Safety Scan
        safety_info = SafetyScanner.evaluate_channel(
            uploader=info.get("uploader", ""),
            title=info.get("title", "")
        )

        print(f"[API] Found {len(candidates)} candidates. Safety: {safety_info['badge_text']}")
        return {
            "success": True,
            "info": info,
            "candidates": candidates,
            "has_subtitles": bool(json3_path),
            "safety": safety_info
        }
    except Exception as e:
        print(f"[API Error] /api/analyze failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/clip")
async def process_clip(req: ClipRequest):
    try:
        duration_sec = req.end_sec - req.start_sec
        print(f"\n[API] Processing Clip #{req.rank} ({req.start_sec}s -> {req.end_sec}s, dur={duration_sec}s, mode={req.mode})")
        raw_clip_filename = f"raw_{req.video_id}_rank{req.rank}.mp4"
        is_landscape = (req.mode == "landscape_16_9")
        prefix = "episode_16x9" if is_landscape else "reels_9x16"
        out_filename = f"{prefix}_{req.video_id}_rank{req.rank}.mp4"

        # Step 1: Stream-slice target segment with video + audio
        print("[API] 1. Stream-slicing target segment with audio...")
        raw_path = downloader.download_clip_section(
            url=req.url,
            start_sec=req.start_sec,
            end_sec=req.end_sec,
            output_filename=raw_clip_filename
        )
        print(f"[API] Raw clip ready: {raw_path} ({raw_path.stat().st_size} bytes)")

        # Step 2: Handle Subtitles / Attribution / Viral Hook Headline
        ass_path = None
        phrases = []
        if req.enable_subtitles:
            words = []
            json3_path = CAPTIONS_CACHE.get(req.video_id)
            if json3_path and json3_path.exists():
                words = subtitle_engine.parse_word_timestamps(
                    json3_path=json3_path,
                    clip_start_sec=req.start_sec,
                    clip_end_sec=req.end_sec
                )

            # If YouTube captions were unavailable, use speech recognition fallback (for clips <= 120s)
            if not words and duration_sec <= 120:
                print("[API] YouTube captions unavailable; running audio speech recognition fallback...")
                words = subtitle_engine.transcribe_audio_fallback(raw_path, clip_duration=duration_sec)

            if words:
                phrases = subtitle_engine.group_into_phrases(words, max_words_per_phrase=3)

        # Generate ASS overlay if subtitles are present OR streamer credit OR hook headline requested
        # In landscape 16:9, only burn ASS if user enabled subtitles or provided a hook headline
        # This allows 15-20 min landscape episodes to render in ~60s via lossless stream-copy!
        credit = req.streamer_credit
        should_overlay = bool(phrases or req.hook_headline or (credit and not is_landscape))
        if should_overlay:
            ass_path = DOWNLOADS_DIR / f"sub_{req.video_id}_rank{req.rank}.ass"
            subtitle_engine.generate_ass_file(
                phrases=phrases,
                output_ass_path=ass_path,
                style=req.subtitle_style,
                streamer_credit=credit,
                hook_headline=req.hook_headline,
                is_landscape=is_landscape
            )
            print(f"[API] Overlay generated: Credit='{credit}', Headline='{req.hook_headline}', Phrases={len(phrases)}, Landscape={is_landscape}")

        # Step 3: Render video (Landscape 16:9 or Vertical 9:16) with Anti-Copyright Shield
        print(f"[API] 3. Rendering video ({req.mode}, anti_copyright={req.anti_copyright})...")
        rendered_path = reframer.convert_to_9_16(
            input_video_path=raw_path,
            mode=req.mode,
            output_filename=out_filename,
            subtitles_ass_path=ass_path,
            anti_copyright=req.anti_copyright,
            auto_mute_music=req.auto_mute_music
        )
        print(f"[API] Complete! Final output: {rendered_path} ({rendered_path.stat().st_size} bytes)")

        return {
            "success": True,
            "video_url": f"/output/{out_filename}",
            "filename": out_filename,
            "subtitles_burned": bool(ass_path),
            "anti_copyright": req.anti_copyright
        }
    except Exception as e:
        print(f"[API Error] /api/clip failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# 📺 YOUTUBE CHANNEL INTEGRATION ENDPOINTS
# ==========================================

ACTIVE_OAUTH_FLOWS: Dict[str, Any] = {}

@app.get("/api/youtube/status")
async def youtube_status():
    """Returns connected channel status and profile info."""
    return youtube_uploader.get_channel_info()

@app.post("/api/youtube/setup")
async def youtube_setup(req: YouTubeSetupRequest):
    """Save Google Cloud OAuth client credentials."""
    try:
        youtube_uploader.save_client_secrets(req.client_id, req.client_secret)
        return {"success": True, "message": "Client credentials saved successfully."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/youtube/auth-url")
async def youtube_auth_url():
    """Generates the Google OAuth authorization URL."""
    flow = youtube_uploader.create_oauth_flow()
    if not flow:
        return {"configured": False, "auth_url": None, "message": "Please configure client_id and client_secret first."}
    
    auth_url, state = flow.authorization_url(prompt="consent", access_type="offline", include_granted_scopes="true")
    ACTIVE_OAUTH_FLOWS[state] = flow
    try:
        verifiers = {}
        v_file = Path("oauth_verifiers.json")
        if v_file.exists():
            with open(v_file, "r", encoding="utf-8") as f:
                verifiers = json.load(f)
        verifiers[state] = getattr(flow, "code_verifier", None)
        with open(v_file, "w", encoding="utf-8") as f:
            json.dump(verifiers, f)
    except Exception as e:
        print(f"[OAuth Warning] Could not persist code_verifier: {e}")
        
    return {"configured": True, "auth_url": auth_url}

@app.get("/api/youtube/callback")
async def youtube_callback(code: str, state: Optional[str] = None):
    """Handles OAuth callback and saves refresh token."""
    try:
        flow = ACTIVE_OAUTH_FLOWS.get(state) if state else None
        if not flow:
            flow = youtube_uploader.create_oauth_flow()
            v_file = Path("oauth_verifiers.json")
            if state and v_file.exists():
                try:
                    with open(v_file, "r", encoding="utf-8") as f:
                        verifiers = json.load(f)
                    if state in verifiers and verifiers[state]:
                        flow.code_verifier = verifiers[state]
                except Exception as e:
                    print(f"[OAuth] Could not load saved code_verifier: {e}")

        flow.fetch_token(code=code)
        creds = flow.credentials
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
        if state and state in ACTIVE_OAUTH_FLOWS:
            ACTIVE_OAUTH_FLOWS.pop(state, None)
            
        return HTMLResponse("""
            <html>
                <body style="background:#0B0E14;color:#00F0FF;font-family:sans-serif;display:flex;flex-direction:column;align-items:center;justify-content:center;height:90vh;">
                    <h2 style="margin-bottom:10px;">✔ YouTube Channel Successfully Connected!</h2>
                    <p style="color:#aaa;">Redirecting to your AI Clipping Dashboard...</p>
                    <script>
                        setTimeout(() => { window.location.href = '/?youtube_connected=1'; }, 2000);
                    </script>
                </body>
            </html>
        """)
    except Exception as e:
        return HTMLResponse(f"<h3>Authentication error: {e}</h3><a href='/'>Return to dashboard</a>")

@app.post("/api/youtube/upload")
async def upload_to_youtube(req: YouTubeUploadRequest):
    """Uploads a rendered video file directly to the connected YouTube channel."""
    try:
        video_path = OUTPUT_DIR / req.filename
        if not video_path.exists():
            raise HTTPException(status_code=404, detail="Video file not found in output library.")

        tags_list = [t.strip() for t in req.tags.split(",") if t.strip()] if req.tags else ["Gaming", "GTA", "Shorts"]
        
        result = youtube_uploader.upload_video(
            video_path=video_path,
            title=req.title,
            description=req.description,
            tags=tags_list,
            category_id="20",  # Gaming category
            privacy_status=req.privacy
        )
        return result
    except Exception as e:
        print(f"[API Error] YouTube Upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/", response_class=HTMLResponse)
async def index():
    html_file = Path(__file__).parent / "static" / "index.html"
    return html_file.read_text(encoding="utf-8")
