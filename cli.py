import sys
import argparse
from pathlib import Path
from src.config import DOWNLOADS_DIR
from src.downloader import YouTubeDownloader
from src.analyzer import ViralAnalyzer
from src.reframer import VideoReframer
from src.subtitles import SubtitleEngine

def main():
    parser = argparse.ArgumentParser(description="AI Viral Clip Catcher CLI with Animated Subtitles")
    parser.add_argument("url", help="YouTube video or stream URL")
    parser.add_argument("--duration", type=int, default=45, help="Target clip duration in seconds (default: 45)")
    parser.add_argument("--mode", choices=["blur_padding", "center_crop"], default="blur_padding", help="9:16 layout mode")
    parser.add_argument("--top", type=int, default=1, help="Number of clips to generate (default: 1)")
    parser.add_argument("--no-subs", action="store_true", help="Disable animated subtitles")
    parser.add_argument("--sub-style", choices=["hormozi_yellow", "neon_green", "cyber_cyan", "fire_orange", "pure_white"], default="hormozi_yellow", help="Subtitle animation highlight style")
    parser.add_argument("--no-anti-copyright", action="store_true", help="Disable anti-copyright shield (micro-shift & color grade)")
    parser.add_argument("--streamer-credit", type=str, default=None, help="Streamer handle to credit at top (e.g. @TechnoGamerz)")
    parser.add_argument("--headline", type=str, default=None, help="Viral hook headline banner (e.g. 'HE DID NOT SEE THIS COMING')")

    args = parser.parse_args()

    print(f"\n⚡ [J.A.R.V.I.S.] Scanning YouTube stream: {args.url}")
    downloader = YouTubeDownloader()
    info = downloader.get_video_info(args.url)
    print(f"🎬 Title: {info['title']}")
    print(f"👤 Channel: {info['uploader']}")
    print(f"⏱️ Duration: {int(info['duration'])}s")

    subtitle_engine = SubtitleEngine()
    json3_path = None
    if not args.no_subs:
        print("📝 Fetching word-level caption timestamps...")
        json3_path = subtitle_engine.fetch_subtitles(args.url, info["id"])
        if json3_path:
            print("   ✔ Word-level captions acquired successfully.")
        else:
            print("   ⚠️ No captions found on video; proceeding without subtitles.")

    print("\n📈 Analyzing audience retention & replay heatmap...")
    analyzer = ViralAnalyzer(target_duration=args.duration)
    candidates = analyzer.analyze_heatmap(
        heatmap=info.get("heatmap", []),
        total_duration=info.get("duration", 0),
        top_n=args.top
    )

    if not candidates:
        print("❌ No candidate moments found.")
        return

    reframer = VideoReframer()
    for c in candidates:
        print(f"\n🔥 Processing Rank #{c['rank']} (Score: {c['virality_score']}%)")
        print(f"   Timeframe: {c['start_formatted']} ➔ {c['end_formatted']} (Peak at {c['peak_formatted']})")

        print("   1. Stream-slicing target segment...")
        raw_clip = downloader.download_clip_section(
            url=args.url,
            start_sec=c['start_time'],
            end_sec=c['end_time'],
            output_filename=f"raw_{info['id']}_rank{c['rank']}.mp4"
        )

        ass_path = None
        phrases = []
        if not args.no_subs:
            words = []
            if json3_path and json3_path.exists():
                print(f"   2. Parsing word timestamps for subtitle generation...")
                words = subtitle_engine.parse_word_timestamps(
                    json3_path=json3_path,
                    clip_start_sec=c['start_time'],
                    clip_end_sec=c['end_time']
                )

            if not words:
                print("   2. Caption file empty; running local speech recognition fallback...")
                words = subtitle_engine.transcribe_audio_fallback(raw_clip, clip_duration=c['duration'])

            if words:
                phrases = subtitle_engine.group_into_phrases(words, max_words_per_phrase=3)
                print(f"      ✔ Generated {len(words)} word animations across {len(phrases)} phrases")

        credit = args.streamer_credit or (f"@{info['uploader']}" if not args.no_anti_copyright and info.get('uploader') else None)
        if phrases or credit or args.headline:
            ass_path = DOWNLOADS_DIR / f"sub_{info['id']}_rank{c['rank']}.ass"
            subtitle_engine.generate_ass_file(
                phrases=phrases,
                output_ass_path=ass_path,
                style=args.sub_style,
                streamer_credit=credit if not args.no_anti_copyright else None,
                hook_headline=args.headline
            )

        print(f"   3. Rendering 9:16 vertical video (anti_copyright={not args.no_anti_copyright})...")
        output_reels = reframer.convert_to_9_16(
            input_video_path=raw_clip,
            mode=args.mode,
            output_filename=f"reels_9x16_{info['id']}_rank{c['rank']}.mp4",
            subtitles_ass_path=ass_path,
            anti_copyright=not args.no_anti_copyright
        )
        print(f"   ✔ Complete! 9:16 Reel saved to: {output_reels.resolve()}")

    print("\n✨ All operations concluded successfully, sir.")

if __name__ == "__main__":
    main()
