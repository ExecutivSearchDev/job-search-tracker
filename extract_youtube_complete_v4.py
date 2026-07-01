#!/usr/bin/env python3
"""
YouTube Channel Extractor v4 - Improved caption extraction with better reliability
"""

import json
import csv
import os
import sys
import time
import logging
import tempfile
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict
from urllib.error import URLError

try:
    import yt_dlp
except ImportError:
    print("❌ yt-dlp not found. Install: pip install yt-dlp")
    sys.exit(1)

# ============================================================================
# CONFIG
# ============================================================================

CHANNEL_HANDLE = "@Elmamounmoubarkdribi"
OUTPUT_DIR = Path("youtube_extraction_complete")
OUTPUT_DIR.mkdir(exist_ok=True)

VIDEOS_INDEX_FILE = OUTPUT_DIR / "all_videos_index.json"
TRANSCRIPTS_FILE = OUTPUT_DIR / "transcripts_complete.json"
TRANSCRIPTS_CSV_FILE = OUTPUT_DIR / "transcripts_complete.csv"
ERROR_LOG_FILE = OUTPUT_DIR / "extraction_debug.log"
STATS_FILE = OUTPUT_DIR / "extraction_stats.json"
PROGRESS_FILE = OUTPUT_DIR / "extraction_progress.json"

# Temp directory for subtitle files
TEMP_DIR = Path(tempfile.gettempdir()) / "yt_extraction_temp"
TEMP_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(ERROR_LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================================================
# PROGRESS TRACKING
# ============================================================================

def load_progress() -> Dict:
    """Load extraction progress"""
    if PROGRESS_FILE.exists():
        try:
            with open(PROGRESS_FILE, 'r') as f:
                return json.load(f)
        except:
            return {'processed_ids': []}
    return {'processed_ids': []}

def save_progress(progress: Dict):
    """Save extraction progress"""
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(progress, f)

# ============================================================================
# EXTRACT VIDEOS
# ============================================================================

def extract_all_videos(channel_handle: str) -> List[Dict]:
    """Extract all videos from channel"""

    logger.info(f"🔍 Extracting videos from {channel_handle}...")

    ydl_opts = {
        'quiet': False,
        'extract_flat': 'in_playlist',
        'skip_unavailable_fragments': True,
        'socket_timeout': 30,
    }

    videos = []

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(
                f"https://www.youtube.com/{channel_handle}/videos",
                download=False
            )

            if 'entries' in info:
                logger.info(f"✓ Found {len(info['entries'])} videos")

                for entry in info['entries']:
                    if entry is None:
                        continue

                    video_id = entry.get('id')
                    if not video_id:
                        continue

                    video_data = {
                        'video_id': video_id,
                        'title': entry.get('title', 'N/A'),
                        'description': entry.get('description', ''),
                        'duration': entry.get('duration', 'N/A'),
                        'upload_date': entry.get('upload_date', 'N/A'),
                        'view_count': entry.get('view_count', 0),
                        'url': f"https://www.youtube.com/watch?v={video_id}",
                    }
                    videos.append(video_data)

    except URLError as e:
        logger.error(f"❌ Network error extracting videos: {e}")
        return videos
    except Exception as e:
        logger.error(f"❌ Error extracting videos: {e}")
        return videos

    return videos

# ============================================================================
# EXTRACT CAPTIONS - IMPROVED WITH PROPER FILE HANDLING
# ============================================================================

def extract_captions_with_retry(video_id: str, max_retries: int = 3) -> Optional[Dict]:
    """
    Extract captions/subtitles using yt-dlp with proper file handling
    """

    video_temp_dir = TEMP_DIR / video_id
    video_temp_dir.mkdir(exist_ok=True)

    for attempt in range(max_retries):
        try:
            logger.debug(f"  Attempt {attempt + 1}/{max_retries} for {video_id}")

            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'writesubtitles': True,
                'writeautomaticsub': True,
                'subtitlesformat': 'vtt',  # VTT is more reliable than json3
                'skip_download': True,
                'socket_timeout': 30,
                'retries': 2,
                'fragment_retries': 2,
                'outtmpl': str(video_temp_dir / '%(id)s'),
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(
                    f"https://www.youtube.com/watch?v={video_id}",
                    download=False
                )

                # Try to extract from info dict first (metadata)
                if info.get('subtitles') or info.get('automatic_captions'):
                    transcript_data = extract_from_metadata(video_id, info)
                    if transcript_data:
                        logger.debug(f"    ✓ SUCCESS (from metadata): {len(transcript_data['transcript_text'])} chars")
                        return transcript_data

                # Try to read from downloaded files
                transcript_data = extract_from_downloaded_files(video_id, video_temp_dir)
                if transcript_data:
                    logger.debug(f"    ✓ SUCCESS (from files): {len(transcript_data['transcript_text'])} chars")
                    return transcript_data

        except URLError as e:
            logger.debug(f"    - Network error: {str(e)[:100]}")
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff
                time.sleep(wait_time)
        except Exception as e:
            logger.debug(f"    - Exception: {type(e).__name__}: {str(e)[:100]}")
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                time.sleep(wait_time)

    logger.debug(f"    ✗ No captions found after {max_retries} attempts")
    # Cleanup temp files
    if video_temp_dir.exists():
        shutil.rmtree(video_temp_dir, ignore_errors=True)
    return None

def extract_from_metadata(video_id: str, info: Dict) -> Optional[Dict]:
    """Extract caption text from yt-dlp metadata"""

    subtitles = info.get('subtitles', {})
    auto_captions = info.get('automatic_captions', {})

    # Prioritize: manual subtitles > auto-generated > fallback to first available
    languages_to_try = []

    # Prefer English if available
    if 'en' in subtitles:
        languages_to_try.append(('en', subtitles['en']))
    elif 'en' in auto_captions:
        languages_to_try.append(('en', auto_captions['en']))

    # Add other languages
    for lang in subtitles:
        if lang != 'en':
            languages_to_try.append((lang, subtitles[lang]))

    for lang in auto_captions:
        if lang != 'en' and (lang, auto_captions[lang]) not in languages_to_try:
            languages_to_try.append((lang, auto_captions[lang]))

    if not languages_to_try and (subtitles or auto_captions):
        # Fallback: use first available
        if subtitles:
            first_lang = list(subtitles.keys())[0]
            languages_to_try.append((first_lang, subtitles[first_lang]))
        else:
            first_lang = list(auto_captions.keys())[0]
            languages_to_try.append((first_lang, auto_captions[first_lang]))

    # Try each language
    for lang, captions in languages_to_try:
        transcript_text = extract_text_from_captions(captions)
        if transcript_text and len(transcript_text.strip()) > 20:  # Require minimum content
            return {
                'video_id': video_id,
                'transcript_available': True,
                'transcript_text': transcript_text.strip(),
                'transcript_source': 'yt-dlp_metadata',
                'language': lang,
            }

    return None

def extract_text_from_captions(captions: List) -> str:
    """Extract text from caption list, handling different formats"""

    transcript_text = ""

    if not isinstance(captions, list):
        return ""

    for caption in captions:
        if isinstance(caption, dict):
            # Format: {'text': 'caption text', 'start': X, 'end': Y}
            if 'text' in caption:
                text = caption['text']
            else:
                # Try to get text from url (for some formats)
                continue
        else:
            # Might be a string directly
            text = str(caption)

        if text:
            transcript_text += text + " "

    return transcript_text

def extract_from_downloaded_files(video_id: str, temp_dir: Path) -> Optional[Dict]:
    """Try to extract captions from downloaded VTT/SRT files"""

    # Look for subtitle files
    vtt_files = list(temp_dir.glob(f"{video_id}*.vtt"))
    srt_files = list(temp_dir.glob(f"{video_id}*.srt"))

    # Prefer English, then any file
    files_to_check = []
    for f in vtt_files + srt_files:
        if 'en' in f.name.lower():
            files_to_check.insert(0, f)
        else:
            files_to_check.append(f)

    for subtitle_file in files_to_check:
        try:
            transcript_text = ""

            if subtitle_file.suffix.lower() == '.vtt':
                # VTT format: skip header and timestamps
                with open(subtitle_file, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                    for line in lines[1:]:  # Skip WEBVTT header
                        line = line.strip()
                        if line and not '-->' in line and line:
                            transcript_text += line + " "

            elif subtitle_file.suffix.lower() == '.srt':
                # SRT format: skip numbers and timestamps
                with open(subtitle_file, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                    for i, line in enumerate(lines):
                        line = line.strip()
                        # Skip empty lines, numbers, and timestamps
                        if line and not line.isdigit() and '-->' not in line:
                            transcript_text += line + " "

            if len(transcript_text.strip()) > 20:
                lang = extract_language_from_filename(subtitle_file.name)
                return {
                    'video_id': video_id,
                    'transcript_available': True,
                    'transcript_text': transcript_text.strip(),
                    'transcript_source': 'yt-dlp_files',
                    'language': lang,
                }

        except Exception as e:
            logger.debug(f"    - Error reading {subtitle_file.name}: {str(e)[:50]}")
            continue

    return None

def extract_language_from_filename(filename: str) -> str:
    """Extract language code from subtitle filename"""

    # Format typically: videoID.en.vtt or videoID.en.vtt
    parts = Path(filename).stem.split('.')
    if len(parts) > 1:
        lang = parts[-1]
        if len(lang) == 2 or len(lang) == 5:  # 'en' or 'en_US'
            return lang
    return 'unknown'

# ============================================================================
# EXTRACT ALL TRANSCRIPTS
# ============================================================================

def extract_all_transcripts(videos: List[Dict]) -> tuple:
    """Extract transcripts from all videos with progress tracking"""

    logger.info(f"\n📝 Extracting captions from {len(videos)} videos...")

    progress = load_progress()
    processed_ids = set(progress.get('processed_ids', []))

    videos_with_transcripts = []
    stats = {
        'total': len(videos),
        'with_transcripts': 0,
        'without_transcripts': 0,
        'start_time': datetime.now().isoformat(),
        'resumed': len(processed_ids) > 0,
    }

    for idx, video in enumerate(videos, 1):
        video_id = video['video_id']

        # Skip if already processed
        if video_id in processed_ids:
            logger.debug(f"[{idx}/{len(videos)}] Skipping (already processed): {video['title'][:60]}")
            continue

        logger.info(f"[{idx}/{len(videos)}] {video['title'][:60]}")

        transcript_data = extract_captions_with_retry(video_id, max_retries=3)

        if transcript_data:
            combined = {**video, **transcript_data}
            videos_with_transcripts.append(combined)
            stats['with_transcripts'] += 1
            logger.info(f"  → ✓ CAPTION FOUND ({len(transcript_data['transcript_text'])} chars)")
        else:
            stats['without_transcripts'] += 1
            logger.info(f"  → ✗ No captions")

        processed_ids.add(video_id)
        progress['processed_ids'] = list(processed_ids)
        save_progress(progress)

        # Rate limiting - be respectful to YouTube
        time.sleep(1.0)

    stats['end_time'] = datetime.now().isoformat()
    stats['coverage_percent'] = (stats['with_transcripts'] / stats['total'] * 100) if stats['total'] > 0 else 0

    # Cleanup temp directory
    if TEMP_DIR.exists():
        shutil.rmtree(TEMP_DIR, ignore_errors=True)

    return videos_with_transcripts, stats

# ============================================================================
# SAVE RESULTS
# ============================================================================

def save_results(videos: List[Dict], videos_with_transcripts: List[Dict], stats: Dict):
    """Save results to files"""

    logger.info("\n💾 Saving results...")

    # Save videos index
    try:
        with open(VIDEOS_INDEX_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                'channel': CHANNEL_HANDLE,
                'total_videos': len(videos),
                'extraction_date': datetime.now().isoformat(),
                'videos': videos
            }, f, indent=2, ensure_ascii=False)
        logger.info(f"  ✓ {VIDEOS_INDEX_FILE}")
    except Exception as e:
        logger.error(f"  ✗ Error saving videos index: {e}")

    # Save transcripts JSON
    try:
        with open(TRANSCRIPTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(videos_with_transcripts, f, indent=2, ensure_ascii=False)
        logger.info(f"  ✓ {TRANSCRIPTS_FILE}")
    except Exception as e:
        logger.error(f"  ✗ Error saving transcripts JSON: {e}")

    # Save transcripts CSV
    if videos_with_transcripts:
        try:
            with open(TRANSCRIPTS_CSV_FILE, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'video_id', 'title', 'upload_date', 'duration', 'view_count',
                    'transcript_source', 'language', 'transcript_length', 'url'
                ])
                writer.writeheader()

                for video in videos_with_transcripts:
                    writer.writerow({
                        'video_id': video['video_id'],
                        'title': video['title'][:100],
                        'upload_date': video['upload_date'],
                        'duration': video['duration'],
                        'view_count': video.get('view_count', 0),
                        'transcript_source': video.get('transcript_source', 'N/A'),
                        'language': video.get('language', 'N/A'),
                        'transcript_length': len(video.get('transcript_text', '')),
                        'url': video['url']
                    })
            logger.info(f"  ✓ {TRANSCRIPTS_CSV_FILE}")
        except Exception as e:
            logger.error(f"  ✗ Error saving transcripts CSV: {e}")

    # Save stats
    try:
        with open(STATS_FILE, 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=2)
        logger.info(f"  ✓ {STATS_FILE}")
    except Exception as e:
        logger.error(f"  ✗ Error saving stats: {e}")

    summary = f"""
================================================================================
✅ EXTRACTION COMPLETE
================================================================================
Total Videos: {stats['total']}
With Captions: {stats['with_transcripts']}
Without Captions: {stats['without_transcripts']}
Coverage: {stats['coverage_percent']:.1f}%
Resumed: {stats.get('resumed', False)}

Files saved to: {OUTPUT_DIR}/
Debug log: {ERROR_LOG_FILE}
================================================================================
"""
    logger.info(summary)

# ============================================================================
# MAIN
# ============================================================================

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, help='Limit to N videos')
    parser.add_argument('--reset-progress', action='store_true', help='Reset progress tracking')
    args = parser.parse_args()

    if args.reset_progress:
        if PROGRESS_FILE.exists():
            PROGRESS_FILE.unlink()
            logger.info("✓ Progress reset")

    logger.info("=" * 80)
    logger.info("YouTube Extractor v4 - Improved Caption Extraction")
    logger.info("=" * 80)

    all_videos = extract_all_videos(CHANNEL_HANDLE)

    if not all_videos:
        logger.error("❌ No videos found")
        sys.exit(1)

    if args.limit:
        all_videos = all_videos[:args.limit]
        logger.info(f"Limited to {args.limit} videos")

    logger.info(f"✓ Total videos to process: {len(all_videos)}")

    videos_with_transcripts, stats = extract_all_transcripts(all_videos)

    save_results(all_videos, videos_with_transcripts, stats)

    logger.info("\n✅ Done!")

if __name__ == "__main__":
    main()
