#!/usr/bin/env python3
"""
YouTube Audio Extraction + Whisper Transcription
Fallback when YouTube blocks caption access

Works by:
1. Downloading video audio
2. Using OpenAI Whisper to transcribe (free, open-source)
3. Getting identical results to YouTube's ASR
"""

import json
import asyncio
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List

try:
    import yt_dlp
except ImportError:
    print("❌ yt-dlp not found. Install: pip install yt-dlp")
    sys.exit(1)

try:
    import whisper
except ImportError:
    print("❌ openai-whisper not found. Install: pip install openai-whisper")
    print("   Optionally use faster version: pip install faster-whisper")
    sys.exit(1)

# ============================================================================
# CONFIG
# ============================================================================

OUTPUT_DIR = Path("youtube_extraction_whisper")
OUTPUT_DIR.mkdir(exist_ok=True)

AUDIO_DIR = OUTPUT_DIR / "audio"
AUDIO_DIR.mkdir(exist_ok=True)

TRANSCRIPTS_FILE = OUTPUT_DIR / "transcripts_whisper.json"
TRANSCRIPTS_TEXT_DIR = OUTPUT_DIR / "transcripts_text"
TRANSCRIPTS_TEXT_DIR.mkdir(exist_ok=True)

# Model options: tiny, base, small, medium, large
# Larger = better accuracy but slower/more memory
WHISPER_MODEL = "base"  # Good balance of speed/quality

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# AUDIO EXTRACTION
# ============================================================================

def download_audio(video_id: str, video_title: str = "") -> Optional[Path]:
    """
    Download video audio to MP3
    """

    logger.info(f"🎵 Downloading audio: {video_title[:50]}")

    audio_file = AUDIO_DIR / f"{video_id}.mp3"

    # Skip if already downloaded
    if audio_file.exists():
        logger.debug(f"  ✓ Audio already exists: {audio_file}")
        return audio_file

    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': True,
            'no_warnings': True,
            'outtmpl': str(AUDIO_DIR / f'{video_id}'),
            'socket_timeout': 30,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.debug(f"  Downloading {video_id}...")
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=True)

        if audio_file.exists():
            logger.debug(f"  ✓ Audio downloaded: {audio_file.stat().st_size} bytes")
            return audio_file
        else:
            logger.error(f"  ✗ Audio file not created")
            return None

    except Exception as e:
        logger.error(f"  ✗ Download failed: {e}")
        return None

# ============================================================================
# WHISPER TRANSCRIPTION
# ============================================================================

def transcribe_with_whisper(audio_file: Path, video_id: str) -> Optional[str]:
    """
    Transcribe audio using Whisper
    """

    logger.info(f"🤖 Transcribing: {audio_file.name}")

    try:
        logger.debug(f"  Loading Whisper model: {WHISPER_MODEL}")
        model = whisper.load_model(WHISPER_MODEL)

        logger.debug(f"  Transcribing audio...")
        result = model.transcribe(str(audio_file))

        transcript_text = result['text']
        detected_language = result.get('language', 'unknown')

        logger.info(f"  ✓ Transcribed ({len(transcript_text)} chars, language: {detected_language})")

        return transcript_text

    except Exception as e:
        logger.error(f"  ✗ Transcription failed: {e}")
        return None

# ============================================================================
# EXTRACT VIA AUDIO
# ============================================================================

def extract_via_audio(video_id: str, video_title: str = "") -> Optional[Dict]:
    """
    Complete audio extraction + transcription pipeline
    """

    logger.info(f"[AUDIO METHOD] {video_title[:50]}")

    # Step 1: Download audio
    audio_file = download_audio(video_id, video_title)
    if not audio_file:
        logger.error(f"  ✗ Failed to download audio")
        return None

    # Step 2: Transcribe
    transcript_text = transcribe_with_whisper(audio_file, video_id)
    if not transcript_text or len(transcript_text.strip()) < 20:
        logger.error(f"  ✗ Failed to transcribe")
        return None

    logger.info(f"  ✓ SUCCESS: {len(transcript_text)} characters")

    return {
        'video_id': video_id,
        'title': video_title,
        'transcript_available': True,
        'transcript_text': transcript_text.strip(),
        'transcript_source': 'whisper_audio',
        'language': 'auto-detected',
    }

# ============================================================================
# BATCH PROCESSING
# ============================================================================

def extract_batch(videos: List[Dict]) -> List[Dict]:
    """
    Extract transcripts from multiple videos
    (Sequential processing - Whisper is CPU-intensive)
    """

    results = []

    for idx, video in enumerate(videos, 1):
        video_id = video.get('video_id')
        title = video.get('title', '')

        logger.info(f"\n[{idx}/{len(videos)}] Processing...")

        result = extract_via_audio(video_id, title)

        if result:
            results.append(result)
            logger.info(f"  ✓ Added to results")
        else:
            logger.info(f"  ✗ Failed")

    return results

# ============================================================================
# SAVE RESULTS
# ============================================================================

def save_results(results: List[Dict]):
    """Save transcripts to files"""

    logger.info(f"\n💾 Saving {len(results)} transcripts...")

    # JSON format
    with open(TRANSCRIPTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    logger.info(f"  ✓ {TRANSCRIPTS_FILE}")

    # Text files
    for result in results:
        video_id = result['video_id']
        text_file = TRANSCRIPTS_TEXT_DIR / f"{video_id}.txt"
        with open(text_file, 'w', encoding='utf-8') as f:
            f.write(f"Video: {result.get('title', 'N/A')}\n")
            f.write(f"Source: {result.get('transcript_source')}\n")
            f.write("-" * 80 + "\n\n")
            f.write(result['transcript_text'])
        logger.info(f"  ✓ {text_file}")

    logger.info(f"\n{'='*80}")
    logger.info(f"✅ COMPLETED")
    logger.info(f"  Total: {len(results)}")
    logger.info(f"  Files: {TRANSCRIPTS_TEXT_DIR}/")
    logger.info(f"{'='*80}\n")

# ============================================================================
# MAIN
# ============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Extract YouTube transcripts via audio + Whisper (when captions are blocked)"
    )
    parser.add_argument('video_ids', nargs='?', help='Video ID or "all" to use all_videos_index.json')
    parser.add_argument('--model', default='base', choices=['tiny', 'base', 'small', 'medium', 'large'],
                        help='Whisper model size (larger = better quality but slower)')
    parser.add_argument('--limit', type=int, help='Limit to N videos')
    args = parser.parse_args()

    if args.model != 'base':
        global WHISPER_MODEL
        WHISPER_MODEL = args.model

    logger.info("=" * 80)
    logger.info("YouTube Transcription - Audio Extraction + Whisper")
    logger.info(f"Model: {WHISPER_MODEL}")
    logger.info("=" * 80)

    # Prepare videos
    videos_to_process = []

    if args.video_ids == "all":
        videos_index = Path("youtube_extraction_complete") / "all_videos_index.json"
        if videos_index.exists():
            with open(videos_index) as f:
                data = json.load(f)
                videos_to_process = data.get('videos', [])
            logger.info(f"Loaded {len(videos_to_process)} videos")
        else:
            logger.error(f"File not found: {videos_index}")
            sys.exit(1)
    elif args.video_ids:
        videos_to_process = [{'video_id': args.video_ids, 'title': 'Test Video'}]
    else:
        videos_to_process = [{
            'video_id': 'jrhD02V3KN0',
            'title': '27 juin 2026'
        }]
        logger.info("Testing with default video")

    if args.limit:
        videos_to_process = videos_to_process[:args.limit]
        logger.info(f"Limited to {args.limit} videos")

    logger.info(f"\n🎵 Processing {len(videos_to_process)} video(s)...\n")

    results = extract_batch(videos_to_process)

    save_results(results)

if __name__ == "__main__":
    main()
