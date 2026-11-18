import streamlit as st
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
import time

from src.downloader import YouTubeDownloader
from src.analyzer import ViralAnalyzer
from src.reframer import VideoReframer
from src.config import OUTPUT_DIR

# Page configuration
st.set_page_config(
    page_title="AI Clipping Tool - Viral 9:16 Shorts",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #FF3366;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.1rem;
        color: #A0AEC0;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background-color: #1A202C;
        border-radius: 10px;
        padding: 15px;
        border: 1px solid #2D3748;
        margin-bottom: 10px;
    }
    .viral-badge {
        background: linear-gradient(90deg, #FF3366 0%, #FF6B6B 100%);
        color: white;
        padding: 4px 10px;
        border-radius: 12px;
        font-weight: bold;
        font-size: 0.85rem;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header">🎬 AI Stream Clipper & 9:16 Reframer</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Catch high-energy viral moments from multi-hour YouTube streams & convert to vertical Reels/Shorts.</div>', unsafe_allow_html=True)

# Sidebar settings
st.sidebar.header("⚙️ Configuration")
target_duration = st.sidebar.slider("Target Clip Duration (sec)", min_value=20, max_value=90, value=45, step=5)
framing_mode = st.sidebar.selectbox(
    "Framing Layout (9:16)",
    options=["blur_padding", "center_crop"],
    format_func=lambda x: "✨ Ambient Blur Background (Best for Gaming)" if x == "blur_padding" else "✂️ Center Crop 9:16"
)
top_n_clips = st.sidebar.slider("Number of Viral Clips to Detect", min_value=1, max_value=10, value=5)

# Initialize modules
@st.cache_resource
def get_services():
    return YouTubeDownloader(), VideoReframer()

downloader, reframer = get_services()
analyzer = ViralAnalyzer(target_duration=target_duration)

# Session state initialization
if 'video_info' not in st.session_state:
    st.session_state.video_info = None
if 'candidates' not in st.session_state:
    st.session_state.candidates = []
if 'last_url' not in st.session_state:
    st.session_state.last_url = ""

# Input Form
with st.container():
    col_input, col_btn = st.columns([4, 1])
    with col_input:
        youtube_url = st.text_input("Enter YouTube Video / Livestream URL:", placeholder="https://www.youtube.com/watch?v=...")
    with col_btn:
        st.write("") # spacing
        st.write("")
        analyze_clicked = st.button("🚀 Analyze Stream", use_container_width=True)

if analyze_clicked and youtube_url:
    with st.spinner("Analyzing stream metadata & audience replay retention graph..."):
        try:
            info = downloader.get_video_info(youtube_url)
            st.session_state.video_info = info
            st.session_state.last_url = youtube_url
            
            # Analyze heatmap
            candidates = analyzer.analyze_heatmap(
                heatmap=info.get('heatmap', []),
                total_duration=info.get('duration', 0),
                top_n=top_n_clips
            )
            st.session_state.candidates = candidates
            st.success("Analysis complete! Viral peaks detected.")
        except Exception as e:
            st.error(f"Failed to analyze video: {str(e)}")

# Display Video Overview & Candidates if available
if st.session_state.video_info:
    info = st.session_state.video_info
    
    st.divider()
    v_col1, v_col2 = st.columns([1, 2])
    with v_col1:
        if info.get('thumbnail'):
            st.image(info['thumbnail'], use_container_width=True)
    with v_col2:
        st.subheader(info.get('title', 'Unknown Title'))
        st.write(f"**Channel:** {info.get('uploader', 'N/A')}")
        duration_sec = info.get('duration', 0)
        hours = int(duration_sec // 3600)
        minutes = int((duration_sec % 3600) // 60)
        st.write(f"**Duration:** {hours}h {minutes}m ({int(duration_sec)} seconds)")
        if info.get('view_count'):
            st.write(f"**Total Views:** {info['view_count']:,}")

    # Replay Heatmap Visualization
    heatmap = info.get('heatmap') or []
    if heatmap and len(heatmap) > 0:
        st.write("### 📈 Audience Replay Graph (Viral Intensity)")
        times = [(pt['start_time'] + pt['end_time']) / 2.0 / 60.0 for pt in heatmap] # in minutes
        values = [pt['value'] for pt in heatmap]
        
        fig, ax = plt.subplots(figsize=(10, 2.5), facecolor='#0E1117')
        ax.set_facecolor('#0E1117')
        ax.plot(times, values, color='#FF3366', linewidth=2)
        ax.fill_between(times, values, color='#FF3366', alpha=0.3)
        
        # Mark candidate peaks
        for c in st.session_state.candidates:
            peak_min = c['peak_time'] / 60.0
            ax.axvline(x=peak_min, color='#00FFAA', linestyle='--', alpha=0.7)
            
        ax.tick_params(colors='#A0AEC0')
        ax.set_xlabel("Timeline (Minutes)", color='#A0AEC0')
        ax.set_ylabel("Replay Density", color='#A0AEC0')
        for spine in ax.spines.values():
            spine.set_color('#2D3748')
        st.pyplot(fig)

    # Candidate Moments List
    st.write("### 🔥 Top Expected Viral Moments")
    if not st.session_state.candidates:
        st.info("No candidates detected. Adjust duration or verify stream.")
    else:
        for c in st.session_state.candidates:
            with st.expander(
                f"Rank #{c['rank']} | Peak at {c['peak_formatted']} | Virality Score: {c['virality_score']}%",
                expanded=(c['rank'] == 1)
            ):
                c_col1, c_col2, c_col3 = st.columns([2, 2, 2])
                with c_col1:
                    st.write(f"**Clip Window:** {c['start_formatted']} ➔ {c['end_formatted']}")
                    st.write(f"**Duration:** {c['duration']} seconds")
                with c_col2:
                    st.write(f"**Peak Retention Time:** `{c['peak_formatted']}`")
                    st.write(f"**Predicted Engagement:** 🔥 `{c['virality_score']}%`")
                with c_col3:
                    render_btn = st.button(
                        f"⚡ Clip & Reframe (Rank #{c['rank']})",
                        key=f"render_{c['rank']}",
                        use_container_width=True
                    )

                if render_btn:
                    with st.status(f"Processing Clip #{c['rank']} into 9:16...", expanded=True) as status:
                        st.write("1. Stream-slicing target segment from YouTube...")
                        clip_file = downloader.download_clip_section(
                            url=st.session_state.last_url,
                            start_sec=c['start_time'],
                            end_sec=c['end_time'],
                            output_filename=f"clip_{info['id']}_rank{c['rank']}.mp4"
                        )
                        st.write(f"✔ Segment extracted: {clip_file.name}")
                        
                        st.write("2. Reframing into 9:16 vertical video via FFmpeg...")
                        rendered_file = reframer.convert_to_9_16(
                            input_video_path=clip_file,
                            mode=framing_mode,
                            output_filename=f"reels_{info['id']}_rank{c['rank']}.mp4"
                        )
                        st.write(f"✔ 9:16 Reel rendered: {rendered_file.name}")
                        status.update(label=f"Clip #{c['rank']} ready!", state="complete")

                    # Preview and Download
                    st.video(str(rendered_file))
                    with open(rendered_file, "rb") as f:
                        st.download_button(
                            label=f"📥 Download 9:16 Reel (Rank #{c['rank']})",
                            data=f,
                            file_name=rendered_file.name,
                            mime="video/mp4",
                            use_container_width=True
                        )
