import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import requests
from bs4 import BeautifulSoup
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, VideoUnavailable, NoTranscriptFound

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output"
OUTPUT_JSON = OUTPUT_DIR / "kunal_shah_videos.json"
PROGRESS_JSON = OUTPUT_DIR / "progress.json"
TEMP_ROOT = ROOT / "temp"

NAME_PATTERN = re.compile(r"kunal\s+shah", re.IGNORECASE)
TIMESTAMP_PATTERN = re.compile(r"(?<!\d)(?:(?P<hours>\d{1,2}):)?(?P<minutes>\d{1,2}):(?P<seconds>\d{2})(?!\d)")
MAX_COMMENT_COUNT = 50
VIDEO_DOMAINS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "instagram.com",
    "www.instagram.com",
    "facebook.com",
    "www.facebook.com",
    "fb.watch",
    "linkedin.com",
    "www.linkedin.com",
    "x.com",
    "www.x.com",
    "twitter.com",
    "www.twitter.com",
    "vimeo.com",
    "www.vimeo.com",
    "dailymotion.com",
    "www.dailymotion.com",
    "tiktok.com",
    "www.tiktok.com",
}


def canonicalize_video_url(raw_url: str) -> str:
    if not raw_url:
        return ""
    url = raw_url.strip()
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()
    if host in {"youtu.be", "www.youtu.be"}:
        video_id = parsed.path.lstrip("/")
        if video_id:
            return f"https://www.youtube.com/watch?v={video_id}"
    if any(host.endswith(suffix) for suffix in ["youtube.com", "youtu.be"]):
        query = urllib.parse.parse_qs(parsed.query)
        if parsed.path in {"/watch", "/shorts"} or host.endswith("youtube.com"):
            video_id = query.get("v", [None])[0]
            if video_id:
                return f"https://www.youtube.com/watch?v={video_id}"
        if parsed.path.startswith("/shorts/"):
            video_id = parsed.path.split("/shorts/")[-1].split("/")[0]
            return f"https://www.youtube.com/watch?v={video_id}"
    if host.endswith("youtube.com") and parsed.path.startswith("/shorts/"):
        video_id = parsed.path.split("/shorts/")[-1].split("/")[0]
        return f"https://www.youtube.com/watch?v={video_id}"
    cleaned = parsed._replace(query=urllib.parse.urlencode({k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items() if k not in {"utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "fbclid", "gclid"}}))
    return cleaned.geturl().rstrip("/")


def extract_timestamp(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    match = TIMESTAMP_PATTERN.search(text)
    if not match:
        return None
    hours = match.group("hours")
    minutes = match.group("minutes")
    seconds = match.group("seconds")
    if hours is not None:
        return f"{hours}:{minutes}:{seconds}"
    return f"{minutes}:{seconds}"


def extract_timestamps_from_text(text: Optional[str]) -> List[str]:
    if not text:
        return []
    timestamps: List[str] = []
    for match in TIMESTAMP_PATTERN.finditer(text):
        hours = match.group("hours")
        minutes = match.group("minutes")
        seconds = match.group("seconds")
        if hours is not None:
            timestamps.append(f"{hours}:{minutes}:{seconds}")
        else:
            timestamps.append(f"{minutes}:{seconds}")
    return timestamps


def looks_like_video_url(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return False
    host = parsed.netloc.lower().replace("www.", "")
    if host in VIDEO_DOMAINS or host.replace("www.", "") in VIDEO_DOMAINS:
        return True
    path = parsed.path.lower()
    return any(token in path for token in ["/video", "/videos", "/watch", "/shorts", "/reel", "/reels", "/embed", "/clip", "/clips", "/watch?v="])


def generate_search_queries() -> List[str]:
    base = ["Kunal Shah"]
    variants = [
        "Kunal Shah interview",
        "Kunal Shah podcast",
        "Kunal Shah clip",
        "Kunal Shah shorts",
        "Kunal Shah reel",
        "Kunal Shah transcript",
        "Kunal Shah captions",
        "Kunal Shah subtitles",
        "Kunal Shah timestamp",
        "Kunal Shah founder",
        "Kunal Shah CRED",
        "Kunal Shah startup",
        "Kunal Shah entrepreneur",
        "Kunal Shah finance",
        "Kunal Shah investor",
        "Kunal Shah podcast transcript",
        "Kunal Shah interview transcript",
        "Kunal Shah YouTube",
        "Kunal Shah Instagram reel",
        "Kunal Shah LinkedIn video",
        "Kunal Shah Facebook video",
        "Kunal Shah Twitter video",
        "Kunal Shah Vimeo",
        "Kunal Shah Dailymotion",
    ]
    return base + variants


def search_youtube_ids(query: str, max_results: int = 10) -> List[str]:
    ids: List[str] = []
    cmd = [sys.executable, "-m", "yt_dlp", "--skip-download", "--flat-playlist", "--print", "%(id)s", f"ytsearch{max_results}:{query}"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            return ids
        for line in result.stdout.splitlines():
            line = line.strip()
            if line and len(line) > 5:
                ids.append(line)
    except Exception:
        return ids
    return ids


def search_web_urls(query: str, max_results: int = 10) -> List[str]:
    urls: List[str] = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
    try:
        encoded = urllib.parse.quote_plus(query)
        response = requests.get(f"https://html.duckduckgo.com/html/?q={encoded}", headers=headers, timeout=20)
        response.raise_for_status()
    except Exception:
        return urls
    soup = BeautifulSoup(response.text, "html.parser")
    for a in soup.select("a.result__a"):
        href = a.get("href")
        if not href:
            continue
        parsed = urllib.parse.urlparse(href)
        if parsed.scheme and parsed.netloc:
            urls.append(href)
        else:
            if href.startswith("//"):
                urls.append(f"https:{href}")
    seen: Set[str] = set()
    filtered: List[str] = []
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        if looks_like_video_url(url):
            filtered.append(url)
        elif any(token in url.lower() for token in ["youtube.com", "youtu.be", "instagram.com", "facebook.com", "linkedin.com", "twitter.com", "vimeo.com", "dailymotion.com"]):
            filtered.append(url)
        if len(filtered) >= max_results:
            break
    return filtered


def collect_candidate_urls() -> List[str]:
    candidates: Set[str] = set()
    for query in generate_search_queries():
        for video_id in search_youtube_ids(query, max_results=8):
            candidates.add(f"https://www.youtube.com/watch?v={video_id}")
        for url in search_web_urls(query, max_results=8):
            candidates.add(canonicalize_video_url(url))
        time.sleep(1)
    return list(candidates)


def parse_comment_entries(items: Any) -> List[Dict[str, Any]]:
    comments: List[Dict[str, Any]] = []
    if isinstance(items, dict):
        items = items.get("comments", []) or []
    if not isinstance(items, list):
        return comments
    for item in items[:MAX_COMMENT_COUNT]:
        if not isinstance(item, dict):
            continue
        text = item.get("text") or item.get("comment") or item.get("content") or ""
        if not isinstance(text, str):
            text = str(text)
        # Keep only the essential fields for comments per user request
        comments.append({
            "comment_text": text.strip(),
            "author": item.get("author") or item.get("author_name") or item.get("author_id"),
            "like_count": item.get("like_count") or item.get("likes") or 0,
            "timestamp": extract_timestamp(text),
        })
    return comments


def parse_comments_json(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return parse_comment_entries(data)


def parse_transcript_segments(transcript: List[Dict[str, Any]], require_name: bool = True) -> List[Dict[str, Any]]:
    segments: List[Dict[str, Any]] = []
    for item in transcript:
        text = item.get("text") or ""
        if not isinstance(text, str):
            text = str(text)
        start = item.get("start")
        duration = item.get("duration")
        start_time = format_seconds(start)
        end_time = format_seconds(start + duration) if duration is not None else None
        segments.append({
            "start_time": start_time,
            "end_time": end_time,
            "text": text.strip(),
            "mentions_name": bool(NAME_PATTERN.search(text)),
        })
    filtered = [segment for segment in segments if segment["mentions_name"]]
    if require_name and filtered:
        return filtered
    return segments


def format_seconds(seconds: Optional[float]) -> Optional[str]:
    if seconds is None:
        return None
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def process_video(url: str, seen: Set[str], results: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    canonical_url = canonicalize_video_url(url)
    if not canonical_url or canonical_url in seen:
        return None
    seen.add(canonical_url)

    video_id = None
    if "youtube.com/watch?v=" in canonical_url:
        video_id = urllib.parse.parse_qs(urllib.parse.urlparse(canonical_url).query).get("v", [None])[0]
    elif canonical_url.startswith("https://www.youtube.com/watch?v="):
        video_id = canonical_url.split("v=")[-1]

    temp_dir = TEMP_ROOT / (video_id or "video")
    temp_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(temp_dir / "%(id)s.%(ext)s")
    cmd = [sys.executable, "-m", "yt_dlp", "--skip-download", "--write-info-json", "--write-comments", "--write-auto-subs", "--write-subs", "--sub-langs", "en", "--extractor-args", "youtube:player_client=web", "-o", output_template, canonical_url]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=240)
    except Exception:
        pass

    info_json = None
    info = {}
    candidate_info_files = []
    if video_id:
        candidate_info_files.extend([temp_dir / f"{video_id}.info.json", temp_dir / "info.json"])
    else:
        candidate_info_files.append(temp_dir / "info.json")
    for path in candidate_info_files:
        if path.exists():
            info_json = path
            break
    if info_json is None:
        for path in sorted(temp_dir.glob("*.info.json")):
            info_json = path
            break
    comments_json = None
    for path in [temp_dir / f"{video_id}.comments.json", temp_dir / "comments.json"] if video_id else [temp_dir / "comments.json"]:
        if path.exists():
            comments_json = path
            break
    title = None
    caption = None
    comments: List[Dict[str, Any]] = []
    transcription: List[Dict[str, Any]] = []

    if info_json and info_json.exists():
        try:
            info = json.loads(info_json.read_text(encoding="utf-8"))
        except Exception:
            info = {}
        title = info.get("title") or info.get("fulltitle")
        caption = info.get("description") or info.get("alt_title")
        if not caption:
            caption = info.get("uploader")
        if not title:
            title = info.get("id")

    if comments_json and comments_json.exists():
        comments = parse_comments_json(comments_json)
    elif info and isinstance(info, dict) and info.get("comments"):
        comments = parse_comment_entries(info)

    if video_id:
        try:
            transcript_items = YouTubeTranscriptApi.get_transcript(video_id, languages=["en"])
            # Always return full transcription (not only name-mention segments)
            transcription = parse_transcript_segments(transcript_items, require_name=False)
        except (TranscriptsDisabled, VideoUnavailable, NoTranscriptFound, Exception):
            transcript_files = list(temp_dir.glob("*.vtt")) + list(temp_dir.glob("*.en.vtt"))
            for file in transcript_files:
                try:
                    text = file.read_text(encoding="utf-8")
                except Exception:
                    continue
                lines = [line.strip() for line in text.splitlines()]
                if not lines:
                    continue
                segments = []
                current = None
                time_pattern = re.compile(r"(?P<start>\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(?P<end>\d{2}:\d{2}:\d{2}\.\d{3})")
                for line in lines:
                    if not line:
                        if current:
                            segments.append(current)
                            current = None
                        continue
                    match = time_pattern.match(line)
                    if match:
                        if current:
                            segments.append(current)
                        current = {
                            "start_time": match.group("start"),
                            "end_time": match.group("end"),
                            "text": "",
                            "mentions_name": False,
                        }
                        continue
                    if current is not None and not line.isdigit():
                        current["text"] += (" " if current["text"] else "") + line
                if current:
                    segments.append(current)
                transcription.extend([{
                    "start_time": seg.get("start_time") or "",
                    "end_time": seg.get("end_time") or "",
                    "text": seg.get("text", "").strip(),
                    "mentions_name": bool(NAME_PATTERN.search(seg.get("text", ""))),
                } for seg in segments])
            # do not filter transcription to only name-mention segments; keep full transcript

    # Collapse transcription segments into a single plain-text transcription string
    if isinstance(transcription, list):
        transcript_texts = [seg.get("text", "").strip() for seg in transcription if seg.get("text")]
        transcription_text = "\n\n".join(transcript_texts) if transcript_texts else ""
        transcription = transcription_text
    else:
        transcription = transcription or ""

    relevant_text = "\n".join(filter(None, [title, caption] + [c.get("comment_text") or "" for c in comments] + [transcription]))

    # If name isn't present in collected fields, try fetching the page HTML
    if not NAME_PATTERN.search(relevant_text):
        try:
            resp = requests.get(canonical_url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200 and NAME_PATTERN.search(resp.text):
                # found name on page HTML
                pass
            else:
                return None
        except Exception:
            return None

    record = {
        "video_link": canonical_url,
        "platform": infer_platform(canonical_url),
        "title": title,
        "caption": caption,
        "transcription": transcription,
        "comments": comments,
    }
    results.append(record)
    return record


def infer_platform(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc.lower()
    if "youtube" in host or "youtu.be" in host:
        return "YouTube"
    if "instagram" in host:
        return "Instagram"
    if "facebook" in host or "fb.watch" in host:
        return "Facebook"
    if "linkedin" in host:
        return "LinkedIn"
    if "twitter" in host or "x.com" in host:
        return "X"
    if "vimeo" in host:
        return "Vimeo"
    if "dailymotion" in host:
        return "Dailymotion"
    return "Other"


def load_existing_results(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(data, list):
        return data
    return []


def count_enriched_records(records: List[Dict[str, Any]]) -> int:
    return sum(
        1
        for record in records
        if (record.get("transcription") and len(str(record.get("transcription")).strip()) > 0)
        or (record.get("comments") and len(record.get("comments")) > 0)
    )


def save_progress(results: List[Dict[str, Any]], processed_count: int, enriched_count: Optional[int] = None) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"processed_count": processed_count, "results_count": len(results)}
    if enriched_count is not None:
        payload["enriched_count"] = enriched_count
    PROGRESS_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def dedupe_results(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: Set[str] = set()
    deduped: List[Dict[str, Any]] = []
    for record in records:
        link = record.get("video_link")
        if not link or link in seen:
            continue
        seen.add(link)
        deduped.append(record)
    return deduped


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    results = load_existing_results(OUTPUT_JSON)
    seen_links = {record.get("video_link") for record in results if record.get("video_link")}
    for seed_url in ["https://www.youtube.com/watch?v=nl1PIagzgUo"]:
        process_video(seed_url, seen_links, results)
    candidates = collect_candidate_urls()
    max_videos = 30
    for url in candidates[:max_videos]:
        process_video(url, seen_links, results)
        save_progress(results, len(results))
        OUTPUT_JSON.write_text(json.dumps(dedupe_results(results), indent=2), encoding="utf-8")
        time.sleep(1)
    OUTPUT_JSON.write_text(json.dumps(dedupe_results(results), indent=2), encoding="utf-8")
    print(f"Saved {len(results)} records to {OUTPUT_JSON}")


if __name__ == "__main__":
    main()


def run_collection(target: int = 1000, max_results_per_query: int = 200, sleep_between: float = 1.0, save_every: int = 10) -> None:
    """Collect candidate video URLs from searches and process them until `target` records are saved.

    This function is network-heavy and may take a long time. It saves progress periodically.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    results = load_existing_results(OUTPUT_JSON)
    seen_links = {r.get("video_link") for r in results if r.get("video_link")}

    # Build candidate pool from search queries
    candidates: Set[str] = set()
    queries = generate_search_queries()
    for q in queries:
        ids = search_youtube_ids(q, max_results=max_results_per_query)
        for vid in ids:
            candidates.add(f"https://www.youtube.com/watch?v={vid}")
        time.sleep(0.5)

    # Also augment with web search results for each query
    for q in queries:
        urls = search_web_urls(q, max_results=50)
        for u in urls:
            candidates.add(canonicalize_video_url(u))
        time.sleep(0.5)

    candidates_list = [c for c in candidates if c]
    print(f"Collected {len(candidates_list)} unique candidates; starting processing")

    processed = 0
    for url in candidates_list:
        if len(dedupe_results(results)) >= target:
            break
        if not url or url in seen_links:
            continue
        rec = process_video(url, seen_links, results)
        processed += 1
        if rec:
            print(f"Saved: {rec.get('video_link')}")
        else:
            print(f"Skipped: {url}")
        if processed % save_every == 0:
            OUTPUT_JSON.write_text(json.dumps(dedupe_results(results), indent=2), encoding="utf-8")
            save_progress(results, len(results))
            print(f"Progress saved: {len(dedupe_results(results))} records so far")
    # Remove artificial delay for maximum processing speed

    OUTPUT_JSON.write_text(json.dumps(dedupe_results(results), indent=2), encoding="utf-8")
    save_progress(results, len(results))
    print(f"Finished run_collection: {len(dedupe_results(results))} records saved to {OUTPUT_JSON}")


def run_fast_collection(target: int = 500, max_results_per_query: int = 200, save_every: int = 50) -> None:
    """Fast metadata-only collection using yt-dlp JSON output (no comments/subs).

    This is much faster: it fetches only video metadata and accepts videos
    where `NAME_PATTERN` appears in title or description. Results are saved
    periodically to `OUTPUT_JSON`.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results = load_existing_results(OUTPUT_JSON)
    seen_links = {r.get("video_link") for r in results if r.get("video_link")}

    candidates: Set[str] = set()
    queries = generate_search_queries()
    for q in queries:
        ids = search_youtube_ids(q, max_results=max_results_per_query)
        for vid in ids:
            candidates.add(f"https://www.youtube.com/watch?v={vid}")
    for q in queries:
        urls = search_web_urls(q, max_results=50)
        for u in urls:
            candidates.add(canonicalize_video_url(u))

    candidates_list = [c for c in candidates if c]
    print(f"Collected {len(candidates_list)} unique candidates; starting fast pass")

    processed = 0
    for url in candidates_list:
        if len(dedupe_results(results)) >= target:
            break
        if not url or url in seen_links:
            continue
        try:
            cmd = [sys.executable, "-m", "yt_dlp", "--skip-download", "-j", url]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if proc.returncode != 0 or not proc.stdout:
                print(f"Skipped (no info): {url}")
                processed += 1
                continue
            info = None
            try:
                info = json.loads(proc.stdout.splitlines()[-1]) if proc.stdout else None
            except Exception:
                try:
                    info = json.loads(proc.stdout)
                except Exception:
                    info = None
            if not info:
                print(f"Skipped (invalid json): {url}")
                processed += 1
                continue
            title = info.get("title")
            caption = info.get("description")
            combined = "\n".join(filter(None, [title or "", caption or ""]))
            if not NAME_PATTERN.search(combined):
                print(f"Skipped (no name): {url}")
                processed += 1
                continue
            record = {
                "video_link": canonicalize_video_url(url),
                "platform": infer_platform(url),
                "title": title,
                "caption": caption,
                "transcription": "",
                "comments": [],
            }
            results.append(record)
            seen_links.add(record["video_link"])
            print(f"Saved: {record['video_link']}")
        except Exception as e:
            print("Error processing", url, type(e).__name__, e)
        processed += 1
        if processed % save_every == 0:
            deduped_results = dedupe_results(results)
            OUTPUT_JSON.write_text(json.dumps(deduped_results, indent=2), encoding="utf-8")
            save_progress(deduped_results, len(deduped_results), enriched_count=count_enriched_records(deduped_results))
            print(f"Progress saved: {len(deduped_results)} records so far, enriched_count={count_enriched_records(deduped_results)}")

    OUTPUT_JSON.write_text(json.dumps(dedupe_results(results), indent=2), encoding="utf-8")
    save_progress(results, len(results))
    print(f"Finished run_fast_collection: {len(dedupe_results(results))} records saved to {OUTPUT_JSON}")


def enrich_saved_records(save_every: int = 10) -> None:
    """Enrich existing saved records with full transcripts and comments (up to MAX_COMMENT_COUNT).

    Runs sequentially and updates `output/kunal_shah_videos.json` as it progresses.
    This is intentionally slow to avoid rate limits; expect many network requests.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    results = load_existing_results(OUTPUT_JSON)
    mapping = {r.get("video_link"): r for r in results if r.get("video_link")}
    links = list(mapping.keys())
    processed = 0

    for link in links:
        rec = mapping.get(link)
        if not rec:
            continue
        needs_trans = not rec.get("transcription")
        needs_comments = not rec.get("comments")
        if not (needs_trans or needs_comments):
            continue
        print(f"Enriching: {link}")
        # run yt-dlp to write info, comments, and subs into a temp dir
        video_id = None
        try:
            parsed = urllib.parse.urlparse(link)
            if "youtube.com" in parsed.netloc and parsed.query:
                video_id = urllib.parse.parse_qs(parsed.query).get("v", [None])[0]
            elif parsed.path.startswith("/watch") and "v=" in parsed.query:
                video_id = urllib.parse.parse_qs(parsed.query).get("v", [None])[0]
        except Exception:
            video_id = None

        temp_dir = TEMP_ROOT / (video_id or f"enrich_{processed}")
        temp_dir.mkdir(parents=True, exist_ok=True)
        output_template = str(temp_dir / "%(id)s.%(ext)s")
        cmd = [sys.executable, "-m", "yt_dlp", "--skip-download", "--write-info-json", "--write-comments", "--write-auto-subs", "--write-subs", "--sub-langs", "en", "--extractor-args", "youtube:player_client=web", "-o", output_template, link]
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=240)
        except Exception:
            pass

        # locate info and comments files
        info_json = None
        if video_id:
            candidates = [temp_dir / f"{video_id}.info.json", temp_dir / "info.json"]
        else:
            candidates = [temp_dir / "info.json"]
        for p in candidates:
            if p.exists():
                info_json = p
                break
        if info_json is None:
            for p in sorted(temp_dir.glob("*.info.json")):
                info_json = p
                break

        comments_json = None
        for p in [temp_dir / f"{video_id}.comments.json", temp_dir / "comments.json"] if video_id else [temp_dir / "comments.json"]:
            if p.exists():
                comments_json = p
                break

        info = {}
        if info_json and info_json.exists():
            try:
                info = json.loads(info_json.read_text(encoding="utf-8"))
            except Exception:
                info = {}

        comments: List[Dict[str, Any]] = []
        if comments_json and comments_json.exists():
            comments = parse_comments_json(comments_json)
        elif info and isinstance(info, dict) and info.get("comments"):
            comments = parse_comment_entries(info)

        transcription = ""
        if video_id:
            try:
                transcript_items = YouTubeTranscriptApi.get_transcript(video_id, languages=["en"])
                segments = parse_transcript_segments(transcript_items, require_name=False)
                transcript_texts = [seg.get("text", "").strip() for seg in segments if seg.get("text")]
                transcription = "\n\n".join(transcript_texts) if transcript_texts else ""
            except Exception:
                # fallback to any .vtt files produced by yt-dlp
                transcript_files = list(temp_dir.glob("*.vtt")) + list(temp_dir.glob("*.en.vtt"))
                texts: List[str] = []
                for file in transcript_files:
                    try:
                        text = file.read_text(encoding="utf-8")
                    except Exception:
                        continue
                    lines = [line.strip() for line in text.splitlines()]
                    if not lines:
                        continue
                    current = None
                    time_pattern = re.compile(r"(?P<start>\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(?P<end>\d{2}:\d{2}:\d{2}\.\d{3})")
                    segments = []
                    for line in lines:
                        if not line:
                            if current:
                                segments.append(current)
                                current = None
                            continue
                        match = time_pattern.match(line)
                        if match:
                            if current:
                                segments.append(current)
                            current = {"start_time": match.group("start"), "end_time": match.group("end"), "text": "", "mentions_name": False}
                            continue
                        if current is not None and not line.isdigit():
                            current["text"] += (" " if current["text"] else "") + line
                    if current:
                        segments.append(current)
                    for seg in segments:
                        if seg.get("text"):
                            texts.append(seg.get("text").strip())
                transcription = "\n\n".join(texts) if texts else ""

        # update record
        rec["transcription"] = transcription
        rec["comments"] = comments[:MAX_COMMENT_COUNT]

        processed += 1
        if processed % save_every == 0:
            OUTPUT_JSON.write_text(json.dumps(dedupe_results(list(mapping.values())), indent=2), encoding="utf-8")
            save_progress(list(mapping.values()), len(mapping))
            print(f"Progress saved: {len(dedupe_results(list(mapping.values())))} records enriched so far")

    OUTPUT_JSON.write_text(json.dumps(dedupe_results(list(mapping.values())), indent=2), encoding="utf-8")
    save_progress(list(mapping.values()), len(mapping))
    print(f"Finished enrichment: {len(dedupe_results(list(mapping.values())))} records saved to {OUTPUT_JSON}")


def enrich_via_process_video(save_every: int = 5) -> None:
    """Re-run `process_video` on saved records to fetch comments and transcripts.

    This uses the same per-video logic as initial collection and is more likely
    to produce the comment/.vtt artifacts that `yt-dlp` writes. It runs
    sequentially and updates `OUTPUT_JSON` periodically.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    results = load_existing_results(OUTPUT_JSON)
    seen_links = {r.get("video_link") for r in results if r.get("video_link")}
    updated = list(results)
    processed = 0

    for rec in list(results):
        link = rec.get("video_link")
        if not link or link in {None, ""}:
            continue
        has_trans = bool(rec.get("transcription"))
        has_comments = bool(rec.get("comments") and len(rec.get("comments"))>0)
        if has_trans and has_comments:
            continue
        print(f"Reprocessing: {link}")
        try:
            process_video(link, seen_links, updated)
        except Exception as e:
            print('Error reprocessing', link, type(e).__name__, e)
        processed += 1
        if processed % save_every == 0:
            OUTPUT_JSON.write_text(json.dumps(dedupe_results(updated), indent=2), encoding="utf-8")
            save_progress(updated, len(updated))
            print(f"Progress saved: {len(dedupe_results(updated))} records so far")

    OUTPUT_JSON.write_text(json.dumps(dedupe_results(updated), indent=2), encoding="utf-8")
    save_progress(updated, len(updated))
    print(f"Finished reprocessing: {len(dedupe_results(updated))} records saved to {OUTPUT_JSON}")
