#!/usr/bin/env python3
"""
YouTube Caption Extractor - Browser Automation Method
Uses Playwright to extract captions from the rendered page
Works because captions are visible in the page HTML after JavaScript renders
"""

import json
import asyncio
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List

try:
    from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
except ImportError:
    print("❌ Playwright not found. Install: pip install playwright")
    print("   Then run: playwright install chromium")
    sys.exit(1)

# ============================================================================
# CONFIG
# ============================================================================

OUTPUT_DIR = Path("youtube_extraction_browser")
OUTPUT_DIR.mkdir(exist_ok=True)

TRANSCRIPTS_FILE = OUTPUT_DIR / "transcripts_browser.json"
TRANSCRIPTS_TEXT_FILE = OUTPUT_DIR / "transcripts_browser"
TRANSCRIPTS_TEXT_FILE.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# CAPTION EXTRACTION - BROWSER METHOD
# ============================================================================

async def extract_captions_browser(video_id: str, video_title: str = "") -> Optional[Dict]:
    """
    Extract captions by opening YouTube in a real browser
    and parsing the rendered DOM
    """

    logger.info(f"🌐 Opening browser for {video_id}")

    try:
        async with async_playwright() as p:
            # Launch browser
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                # Pretend to be a real user
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            page = await context.new_page()

            # Set timeout and navigate
            page.set_default_timeout(30000)  # 30 second timeout
            url = f"https://www.youtube.com/watch?v={video_id}"

            logger.debug(f"  Navigating to {url}")
            await page.goto(url, wait_until="networkidle")

            # Wait for video player to load
            try:
                await page.wait_for_selector(".html5-main-video", timeout=10000)
                logger.debug("  ✓ Video player loaded")
            except PlaywrightTimeout:
                logger.debug("  ⚠ Video player timeout (captions might still load)")

            # Wait for captions to potentially load
            await asyncio.sleep(3)

            # METHOD 1: Look for caption window (current rendering)
            captions_text = ""
            try:
                logger.debug("  Trying caption window extraction...")

                # Try different caption selectors
                selectors = [
                    ".ytp-caption-segment",  # Most common
                    ".captions-text",
                    "[aria-label*='caption']",
                    ".caption-window span",
                    "span.captions-text",
                ]

                for selector in selectors:
                    try:
                        elements = await page.query_selector_all(selector)
                        if elements:
                            logger.debug(f"    Found {len(elements)} elements with '{selector}'")
                            for elem in elements:
                                text = await elem.text_content()
                                if text:
                                    captions_text += text + " "
                    except Exception as e:
                        logger.debug(f"    Selector '{selector}' failed: {e}")
                        continue

                if captions_text.strip():
                    logger.debug(f"    ✓ Got captions from DOM ({len(captions_text)} chars)")
                    await browser.close()
                    return {
                        'video_id': video_id,
                        'title': video_title,
                        'transcript_available': True,
                        'transcript_text': captions_text.strip(),
                        'transcript_source': 'browser_dom',
                        'language': 'unknown',
                    }

            except Exception as e:
                logger.debug(f"    Caption window extraction failed: {e}")

            # METHOD 2: Extract from page HTML/JavaScript
            logger.debug("  Trying JavaScript extraction...")
            try:
                # Get all text nodes from the page
                all_text = await page.evaluate("""
                    () => {
                        // Try to get caption data from YouTube's data structure
                        const captionElements = Array.from(
                            document.querySelectorAll(
                                '.ytp-caption-segment, .captions-text, [role="img"]'
                            )
                        );
                        const text = captionElements
                            .map(el => el.textContent || el.innerText)
                            .filter(t => t && t.trim().length > 0)
                            .join(' ');
                        return text;
                    }
                """)

                if all_text and len(all_text.strip()) > 20:
                    logger.debug(f"    ✓ Got captions from JS ({len(all_text)} chars)")
                    await browser.close()
                    return {
                        'video_id': video_id,
                        'title': video_title,
                        'transcript_available': True,
                        'transcript_text': all_text.strip(),
                        'transcript_source': 'browser_js',
                        'language': 'unknown',
                    }

            except Exception as e:
                logger.debug(f"    JavaScript extraction failed: {e}")

            # METHOD 3: Check for caption tracks in ytInitialData
            logger.debug("  Trying ytInitialData extraction...")
            try:
                caption_data = await page.evaluate("""
                    () => {
                        // Try to find caption tracks in the initial data
                        if (window.ytInitialData) {
                            const data = JSON.stringify(window.ytInitialData);
                            const match = data.match(/"captionTracks":\\s*\\[(.*?)\\]/);
                            if (match) return match[1].substring(0, 500);
                        }
                        return null;
                    }
                """)

                if caption_data:
                    logger.debug(f"    Found caption track data: {caption_data[:100]}...")

            except Exception as e:
                logger.debug(f"    ytInitialData extraction failed: {e}")

            await browser.close()
            logger.debug("  ✗ No captions extracted")
            return None

    except Exception as e:
        logger.error(f"  ✗ Browser error: {e}")
        return None

# ============================================================================
# BATCH EXTRACTION
# ============================================================================

async def extract_captions_batch(videos: List[Dict], max_concurrent: int = 2) -> List[Dict]:
    """
    Extract captions from multiple videos concurrently
    (Limited concurrency to be respectful to YouTube)
    """

    results = []
    semaphore = asyncio.Semaphore(max_concurrent)

    async def extract_with_semaphore(video):
        async with semaphore:
            video_id = video.get('video_id')
            title = video.get('title', '')

            logger.info(f"[{len(results)+1}/{len(videos)}] {title[:50]}")

            result = await extract_captions_browser(video_id, title)

            if result:
                results.append(result)
                logger.info(f"  → ✓ CAPTIONS FOUND ({len(result['transcript_text'])} chars)")
            else:
                logger.info(f"  → ✗ No captions")

            await asyncio.sleep(2)  # Rate limit

    # Run extraction tasks
    tasks = [extract_with_semaphore(video) for video in videos]
    await asyncio.gather(*tasks)

    return results

# ============================================================================
# MAIN
# ============================================================================

async def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Extract YouTube captions using browser automation"
    )
    parser.add_argument('video_ids', nargs='?', help='Video ID to test (or "all" to use all_videos_index.json)')
    parser.add_argument('--concurrent', type=int, default=2, help='Max concurrent browsers (default: 2)')
    parser.add_argument('--timeout', type=int, default=30, help='Timeout per video in seconds (default: 30)')
    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("YouTube Caption Extractor - Browser Automation")
    logger.info("=" * 80)

    # Prepare videos list
    videos_to_process = []

    if args.video_ids == "all":
        # Load from videos index
        videos_index = Path("youtube_extraction_complete") / "all_videos_index.json"
        if videos_index.exists():
            with open(videos_index) as f:
                data = json.load(f)
                videos_to_process = data.get('videos', [])
            logger.info(f"Loaded {len(videos_to_process)} videos from index")
        else:
            logger.error(f"File not found: {videos_index}")
            sys.exit(1)
    elif args.video_ids:
        # Single video test
        video_id = args.video_ids
        videos_to_process = [{'video_id': video_id, 'title': 'Test Video'}]
    else:
        # Default: test the known video
        video_id = "jrhD02V3KN0"
        videos_to_process = [{
            'video_id': video_id,
            'title': '27 juin 2026'
        }]
        logger.info(f"Testing with default video: {video_id}")

    # Extract captions
    logger.info(f"\n🌐 Starting extraction from {len(videos_to_process)} video(s)...\n")
    results = await extract_captions_batch(videos_to_process, max_concurrent=args.concurrent)

    # Save results
    logger.info(f"\n💾 Saving {len(results)} results...")

    # JSON format
    with open(TRANSCRIPTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    logger.info(f"  ✓ {TRANSCRIPTS_FILE}")

    # Individual text files
    for result in results:
        video_id = result['video_id']
        text_file = TRANSCRIPTS_TEXT_FILE / f"{video_id}.txt"
        with open(text_file, 'w', encoding='utf-8') as f:
            f.write(f"Video ID: {video_id}\n")
            f.write(f"Title: {result.get('title', 'N/A')}\n")
            f.write(f"Source: {result.get('transcript_source', 'N/A')}\n")
            f.write(f"Language: {result.get('language', 'N/A')}\n")
            f.write("-" * 80 + "\n\n")
            f.write(result['transcript_text'])
        logger.info(f"  ✓ {text_file}")

    # Summary
    logger.info(f"\n{'='*80}")
    logger.info(f"✅ EXTRACTION COMPLETE")
    logger.info(f"{'='*80}")
    logger.info(f"Total videos: {len(videos_to_process)}")
    logger.info(f"With captions: {len(results)}")
    logger.info(f"Success rate: {len(results)/len(videos_to_process)*100:.1f}%")
    logger.info(f"Files saved to: {OUTPUT_DIR}/")
    logger.info(f"{'='*80}\n")

if __name__ == "__main__":
    asyncio.run(main())
