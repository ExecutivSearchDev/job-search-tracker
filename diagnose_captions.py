#!/usr/bin/env python3
"""
Diagnostic script to understand why caption extraction fails for jrhD02V3KN0
Tests multiple methods to pinpoint the exact issue
"""

import json
import requests
import re
import sys
import logging
from datetime import datetime

try:
    import yt_dlp
except ImportError:
    print("❌ yt-dlp not found. Install: pip install yt-dlp")
    sys.exit(1)

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

VIDEO_ID = "jrhD02V3KN0"
VIDEO_URL = f"https://www.youtube.com/watch?v={VIDEO_ID}"

print("=" * 80)
print(f"DIAGNOSTIC TEST: {VIDEO_ID}")
print(f"Title: 27 juin 2026")
print(f"URL: {VIDEO_URL}")
print("=" * 80)

# ============================================================================
# TEST 1: Direct page HTML inspection
# ============================================================================
print("\n[TEST 1] HTML Page Analysis")
print("-" * 80)

try:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    response = requests.get(VIDEO_URL, headers=headers, timeout=10)
    html = response.text

    print(f"✓ Page fetched ({len(html)} bytes)")

    # Check if captions mentioned in page
    if 'caption' in html.lower():
        print("✓ Word 'caption' found in HTML")
    else:
        print("✗ Word 'caption' NOT in HTML")

    # Check for subtitle-related keywords
    keywords = ['subtitle', 'timedtext', 'captions_track', 'subtitles', 'caption_track']
    for kw in keywords:
        if kw.lower() in html.lower():
            print(f"✓ Found '{kw}' in HTML")

    # Look for timedtext URLs (caption file URLs)
    timedtext_urls = re.findall(r'https://[^"]*timedtext[^"]*', html)
    if timedtext_urls:
        print(f"\n✓ Found {len(timedtext_urls)} timedtext URLs:")
        for url in timedtext_urls[:3]:
            print(f"   {url[:100]}...")
    else:
        print("✗ No timedtext URLs found in HTML")

    # Check for caption languages
    lang_match = re.findall(r'"captionTracks":\[([^\]]*)\]', html)
    if lang_match:
        print(f"\n✓ Found caption tracks data")
        print(f"   Raw: {lang_match[0][:200]}...")
    else:
        print("✗ No caption tracks found in HTML")

except Exception as e:
    print(f"✗ Error fetching page: {e}")

# ============================================================================
# TEST 2: yt-dlp metadata extraction (verbose)
# ============================================================================
print("\n[TEST 2] yt-dlp Metadata Extraction")
print("-" * 80)

try:
    ydl_opts = {
        'quiet': False,
        'no_warnings': False,
        'writesubtitles': True,
        'writeautomaticsub': True,
        'subtitlesformat': 'vtt',
        'skip_download': True,
        'socket_timeout': 30,
        'outtmpl': '/tmp/test_%(id)s',
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        print(f"Extracting info for {VIDEO_ID}...")
        info = ydl.extract_info(VIDEO_URL, download=False)

        # Check subtitles
        subtitles = info.get('subtitles', {})
        auto_captions = info.get('automatic_captions', {})

        print(f"\n✓ Subtitles found: {len(subtitles)} language(s)")
        if subtitles:
            for lang, caps in subtitles.items():
                print(f"   - {lang}: {len(caps)} entries")
                if caps and isinstance(caps[0], dict):
                    print(f"      First entry: {caps[0]}")

        print(f"✓ Automatic captions found: {len(auto_captions)} language(s)")
        if auto_captions:
            for lang, caps in auto_captions.items():
                print(f"   - {lang}: {len(caps)} entries")
                if caps and isinstance(caps[0], dict):
                    print(f"      First entry: {caps[0]}")

        # Check other video info
        print(f"\nVideo Info:")
        print(f"  Title: {info.get('title', 'N/A')}")
        print(f"  Duration: {info.get('duration', 'N/A')} seconds")
        print(f"  View count: {info.get('view_count', 'N/A')}")
        print(f"  Is live: {info.get('is_live', False)}")

        # Check for caption-related keys
        caption_keys = [k for k in info.keys() if 'caption' in k.lower() or 'subtitle' in k.lower()]
        if caption_keys:
            print(f"\nCaption-related keys in info:")
            for key in caption_keys:
                value = info.get(key)
                if isinstance(value, dict):
                    print(f"  {key}: {len(value)} items")
                elif isinstance(value, list):
                    print(f"  {key}: {len(value)} items")
                else:
                    print(f"  {key}: {value}")

except Exception as e:
    print(f"✗ yt-dlp extraction failed: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# TEST 3: Check if video is restricted/private
# ============================================================================
print("\n[TEST 3] Video Accessibility")
print("-" * 80)

try:
    with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
        info = ydl.extract_info(VIDEO_URL, download=False)

        status = info.get('is_playable', None)
        availability = info.get('availability', 'unknown')

        print(f"✓ Playable: {status}")
        print(f"✓ Availability: {availability}")

        if info.get('age_limit'):
            print(f"⚠ Age restricted: {info.get('age_limit')}")

        if info.get('is_live'):
            print(f"⚠ Live stream: Yes")

        print(f"✓ Video is accessible")

except Exception as e:
    print(f"✗ Accessibility check failed: {e}")

# ============================================================================
# TEST 4: Try youtube-transcript-api
# ============================================================================
print("\n[TEST 4] youtube-transcript-api")
print("-" * 80)

try:
    from youtube_transcript_api import YouTubeTranscriptApi

    try:
        # Try to get available transcripts
        transcript_list = YouTubeTranscriptApi.list_transcripts(VIDEO_ID)

        print(f"✓ Manual transcripts: {len(transcript_list.manually_created_transcripts)}")
        for transcript in transcript_list.manually_created_transcripts:
            print(f"   - {transcript.language}: {transcript.language_code}")

            # Try to fetch
            try:
                data = transcript.fetch()
                print(f"      ✓ Fetched {len(data)} entries")
                if data:
                    print(f"      First entry: {data[0]}")
            except Exception as e:
                print(f"      ✗ Fetch failed: {e}")

        print(f"✓ Auto-generated transcripts: {len(transcript_list.automatically_generated_transcripts)}")
        for transcript in transcript_list.automatically_generated_transcripts:
            print(f"   - {transcript.language}: {transcript.language_code}")

            try:
                data = transcript.fetch()
                print(f"      ✓ Fetched {len(data)} entries")
                if data:
                    print(f"      First entry: {data[0]}")
            except Exception as e:
                print(f"      ✗ Fetch failed: {e}")

        if not transcript_list.manually_created_transcripts and not transcript_list.automatically_generated_transcripts:
            print("✗ No transcripts available through API")

    except Exception as e:
        print(f"✗ Transcript API error: {e}")

except ImportError:
    print("⚠ youtube-transcript-api not installed")
    print("  Install: pip install youtube-transcript-api")

# ============================================================================
# TEST 5: Check for captionTracks in initial data
# ============================================================================
print("\n[TEST 5] Initial Data Structure (ytInitialData)")
print("-" * 80)

try:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    response = requests.get(VIDEO_URL, headers=headers, timeout=10)
    html = response.text

    # Find ytInitialData
    match = re.search(r'var ytInitialData = ({.*?});', html, re.DOTALL)
    if match:
        print("✓ Found ytInitialData")
        try:
            data = json.loads(match.group(1))

            # Look for caption tracks
            def find_caption_tracks(obj, depth=0):
                if depth > 10:  # Limit recursion
                    return []
                results = []
                if isinstance(obj, dict):
                    if 'captionTracks' in obj:
                        results.append(obj['captionTracks'])
                    for v in obj.values():
                        results.extend(find_caption_tracks(v, depth + 1))
                elif isinstance(obj, list):
                    for item in obj:
                        results.extend(find_caption_tracks(item, depth + 1))
                return results

            tracks = find_caption_tracks(data)
            if tracks:
                print(f"✓ Found {len(tracks)} caption track collections")
                for i, track_set in enumerate(tracks):
                    print(f"   Collection {i}: {len(track_set) if isinstance(track_set, list) else 1} track(s)")
                    if isinstance(track_set, list) and track_set:
                        print(f"      {track_set[0]}")
            else:
                print("✗ No captionTracks found in ytInitialData")
        except json.JSONDecodeError as e:
            print(f"✗ Failed to parse ytInitialData: {e}")
    else:
        print("✗ ytInitialData not found in HTML")

except Exception as e:
    print(f"✗ Initial data check failed: {e}")

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "=" * 80)
print("DIAGNOSTIC SUMMARY")
print("=" * 80)
print("""
This diagnostic script checks 5 methods:
1. HTML page structure - looking for caption references
2. yt-dlp metadata - standard subtitle extraction
3. Video accessibility - checking if video is playable
4. youtube-transcript-api - transcript API access
5. Initial data structure - checking ytInitialData for captions

Review the results above to identify which method(s) could work.

NEXT STEP: Browser automation (Playwright) will be tested next.
It directly extracts captions from the rendered page DOM.
""")
