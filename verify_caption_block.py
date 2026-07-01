#!/usr/bin/env python3
"""
Verify exactly how YouTube is blocking caption access
Test what yt-dlp sees vs what we can actually retrieve
"""

import json
import sys
import logging

try:
    import yt_dlp
except ImportError:
    print("❌ yt-dlp not found")
    sys.exit(1)

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

VIDEO_ID = "jrhD02V3KN0"
VIDEO_URL = f"https://www.youtube.com/watch?v={VIDEO_ID}"

print("=" * 80)
print(f"CAPTION ACCESS VERIFICATION")
print(f"Video: {VIDEO_ID}")
print("=" * 80)

# ============================================================================
# What does yt-dlp see?
# ============================================================================

print("\n[STEP 1] What yt-dlp detects")
print("-" * 80)

try:
    ydl_opts = {
        'quiet': False,
        'skip_download': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(VIDEO_URL, download=False)

        # Check what caption info exists
        auto_captions = info.get('automatic_captions', {})
        manual_captions = info.get('subtitles', {})

        print(f"✓ Automatic captions detected: {len(auto_captions)} language(s)")
        if auto_captions:
            for lang, caption_list in auto_captions.items():
                print(f"   {lang}:")
                print(f"     Total entries: {len(caption_list)}")
                if caption_list:
                    first = caption_list[0]
                    print(f"     First entry format: {type(first)}")
                    print(f"     First entry keys: {first.keys() if isinstance(first, dict) else 'N/A'}")

                    # Try to get the URL
                    if isinstance(first, dict):
                        url = first.get('url', 'NO URL')
                        ext = first.get('ext', 'NO EXT')
                        print(f"     URL: {url[:100] if url != 'NO URL' else url}")
                        print(f"     Extension: {ext}")

        print(f"\n✓ Manual captions detected: {len(manual_captions)} language(s)")
        if manual_captions:
            for lang, caption_list in manual_captions.items():
                print(f"   {lang}: {len(caption_list)} entries")

        # Check live status
        is_live = info.get('is_live', False)
        print(f"\n✓ Is live stream: {is_live}")

        # Check for subtitle-related keys
        sub_keys = {k: v for k, v in info.items() if 'caption' in k.lower() or 'subtitle' in k.lower()}
        if sub_keys:
            print(f"\n✓ Caption-related keys:")
            for key, val in sub_keys.items():
                print(f"   {key}: {type(val).__name__}")

except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# Try to fetch the caption URLs
# ============================================================================

print("\n[STEP 2] Try to fetch caption URLs")
print("-" * 80)

try:
    ydl_opts = {
        'quiet': True,
        'skip_download': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(VIDEO_URL, download=False)
        auto_captions = info.get('automatic_captions', {})

        if auto_captions:
            for lang, caption_list in auto_captions.items():
                if caption_list and isinstance(caption_list[0], dict):
                    url = caption_list[0].get('url')
                    if url:
                        print(f"\n{lang} - Attempting to fetch: {url[:80]}...")

                        import requests
                        try:
                            response = requests.get(url, timeout=5)
                            print(f"  Status: {response.status_code}")

                            if response.status_code == 200:
                                print(f"  ✓ URL IS ACCESSIBLE ({len(response.text)} bytes)")
                                # Show first 200 chars
                                print(f"  Content preview: {response.text[:200]}...")
                            else:
                                print(f"  ✗ URL blocked: {response.status_code} {response.reason}")

                        except Exception as e:
                            print(f"  ✗ Fetch failed: {e}")
                        break  # Test only first language

except Exception as e:
    print(f"✗ Error: {e}")

# ============================================================================
# Check for live caption streams
# ============================================================================

print("\n[STEP 3] Live caption/subtitle endpoints")
print("-" * 80)

try:
    import requests
    import re

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    response = requests.get(VIDEO_URL, headers=headers, timeout=10)

    # Look for streaming manifest
    if 'streamingData' in response.text:
        print("✓ Found streamingData (video can be accessed)")
    else:
        print("✗ No streamingData found")

    # Look for caption-related URLs
    caption_urls = re.findall(r'https://[^"]*timedtext[^"]*', response.text)
    if caption_urls:
        print(f"✓ Found {len(caption_urls)} timedtext URLs in page:")
        for url in caption_urls[:3]:
            print(f"   {url[:100]}...")
    else:
        print("✗ No timedtext URLs in page HTML")

except Exception as e:
    print(f"✗ Error: {e}")

# ============================================================================
# Summary
# ============================================================================

print("\n" + "=" * 80)
print("ANALYSIS SUMMARY")
print("=" * 80)

print("""
IF YOU SEE:
✓ 157 automatic captions detected → YouTube knows they exist
✗ URL blocked (403/429) → YouTube is actively blocking programmatic access
✗ URL not found → Captions aren't exposed to programmatic extraction

INTERPRETATION:
- If captions are detected but URLs blocked → Anti-bot protection active
- If captions exist but no URLs found → ASR-specific restriction
- If you can see them manually but bots can't → YouTube's intentional design

NEXT STEPS:
1. Run this diagnostic to see the exact error
2. If URLs are blocked, consider audio extraction + Whisper
3. If no URLs exist, manual extraction is the only option
""")
