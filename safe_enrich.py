import json
import subprocess
import sys
import urllib.parse
from pathlib import Path

from youtube_transcript_api import YouTubeTranscriptApi

# ==========================================
# SETTINGS
# ==========================================
JSON_PATH = Path("output/kunal_shah_videos.json")
ATTEMPTED_PATH = Path("output/safe_enrich_attempted.json")
TEMP_DIR = Path("temp_safe_enrich")

BATCH_SIZE = 100
MAX_COMMENTS = 50

TEMP_DIR.mkdir(parents=True, exist_ok=True)

# ==========================================
# LOAD MAIN DATA
# ==========================================
data = json.loads(
    JSON_PATH.read_text(encoding="utf-8")
)

# ==========================================
# LOAD ATTEMPTED LINKS
# ==========================================
if ATTEMPTED_PATH.exists():
    try:
        attempted = set(
            json.loads(
                ATTEMPTED_PATH.read_text(encoding="utf-8")
            )
        )
    except Exception:
        attempted = set()
else:
    attempted = set()

# ==========================================
# SELECT NEXT FRESH INCOMPLETE RECORDS
# ==========================================
targets = [
    record
    for record in data
    if (
        not record.get("comments")
        or not record.get("transcription")
    )
    and record.get("video_link")
    and record.get("video_link") not in attempted
][:BATCH_SIZE]

print("TOTAL RECORDS:", len(data))
print("ALREADY ATTEMPTED:", len(attempted))
print("BATCH TARGETS:", len(targets))

if not targets:
    print("NO NEW TARGETS LEFT")
    sys.exit(0)

api = YouTubeTranscriptApi()

added_comments = 0
added_transcripts = 0

# ==========================================
# PROCESS TARGETS
# ==========================================
for i, record in enumerate(targets, 1):

    url = record.get("video_link", "")

    parsed = urllib.parse.urlparse(url)

    video_id = urllib.parse.parse_qs(
        parsed.query
    ).get("v", [None])[0]

    print()
    print(
        f"[{i}/{len(targets)}] PROCESSING {url}"
    )

    # ======================================
    # NO VIDEO ID
    # ======================================
    if not video_id:
        print("  SKIP: NO VIDEO ID")

        attempted.add(url)

        ATTEMPTED_PATH.write_text(
            json.dumps(
                sorted(attempted),
                indent=2,
                ensure_ascii=False
            ),
            encoding="utf-8"
        )

        continue

    # ======================================
    # TRANSCRIPTION
    # ONLY IF CURRENTLY MISSING
    # NEVER OVERWRITE EXISTING DATA
    # ======================================
    if not record.get("transcription"):

        try:
            fetched = api.fetch(video_id)

            parts = []

            for segment in fetched:

                text = getattr(
                    segment,
                    "text",
                    ""
                )

                if text:
                    text = text.strip()

                    if text:
                        parts.append(text)

            if parts:

                new_transcription = "\n\n".join(
                    parts
                )

                if (
                    new_transcription
                    and not record.get("transcription")
                ):
                    record["transcription"] = (
                        new_transcription
                    )

                    added_transcripts += 1

                    print(
                        "  TRANSCRIPT OK"
                        " | TOTAL ADDED:",
                        added_transcripts
                    )

            else:
                print("  TRANSCRIPT EMPTY")

        except Exception as e:
            print(
                "  TRANSCRIPT FAIL:",
                type(e).__name__
            )

    else:
        print(
            "  TRANSCRIPT ALREADY EXISTS"
        )

    # ======================================
    # COMMENTS
    # ONLY IF CURRENTLY MISSING
    # NEVER OVERWRITE EXISTING DATA
    # ======================================
    if not record.get("comments"):

        video_temp = TEMP_DIR / video_id

        video_temp.mkdir(
            parents=True,
            exist_ok=True
        )

        output_template = str(
            video_temp / "%(id)s.%(ext)s"
        )

        cmd = [
            sys.executable,
            "-m",
            "yt_dlp",

            "--skip-download",

            "--write-info-json",
            "--write-comments",

            "--extractor-args",
            "youtube:max_comments=50",

            "-o",
            output_template,

            url,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120
            )

            info_file = (
                video_temp
                / f"{video_id}.info.json"
            )

            if info_file.exists():

                try:
                    info = json.loads(
                        info_file.read_text(
                            encoding="utf-8"
                        )
                    )

                except Exception:
                    info = {}

                raw_comments = (
                    info.get("comments")
                    or []
                )

                comments = []

                for comment in raw_comments[
                    :MAX_COMMENTS
                ]:

                    comment_text = (
                        comment.get("text")
                        or ""
                    ).strip()

                    if not comment_text:
                        continue

                    comments.append({
                        "comment_text":
                            comment_text,

                        "author":
                            comment.get(
                                "author"
                            ),

                        "timestamp":
                            comment.get(
                                "timestamp"
                            ),
                    })

                if (
                    comments
                    and not record.get("comments")
                ):

                    record["comments"] = comments

                    added_comments += 1

                    print(
                        "  COMMENTS OK:",
                        len(comments),
                        "| TOTAL VIDEOS ADDED:",
                        added_comments
                    )

                else:
                    print(
                        "  COMMENTS EMPTY"
                    )

            else:
                print(
                    "  COMMENTS NO INFO FILE"
                )

                if result.stderr:
                    print(
                        "  YT-DLP:",
                        result.stderr[-200:]
                    )

        except subprocess.TimeoutExpired:
            print(
                "  COMMENTS TIMEOUT"
            )

        except Exception as e:
            print(
                "  COMMENTS FAIL:",
                type(e).__name__
            )

    else:
        print(
            "  COMMENTS ALREADY EXIST"
        )

    # ======================================
    # MARK URL AS ATTEMPTED
    # ======================================
    attempted.add(url)

    ATTEMPTED_PATH.write_text(
        json.dumps(
            sorted(attempted),
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    # ======================================
    # SAVE MAIN JSON AFTER EVERY VIDEO
    # ======================================
    JSON_PATH.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

# ==========================================
# FINAL SAVE
# ==========================================
JSON_PATH.write_text(
    json.dumps(
        data,
        indent=2,
        ensure_ascii=False
    ),
    encoding="utf-8"
)

ATTEMPTED_PATH.write_text(
    json.dumps(
        sorted(attempted),
        indent=2,
        ensure_ascii=False
    ),
    encoding="utf-8"
)

# ==========================================
# FINAL COUNTS
# ==========================================
with_comments = sum(
    bool(x.get("comments"))
    for x in data
)

with_transcription = sum(
    bool(x.get("transcription"))
    for x in data
)

with_both = sum(
    bool(x.get("comments"))
    and bool(x.get("transcription"))
    for x in data
)

missing_comments = sum(
    not bool(x.get("comments"))
    for x in data
)

missing_transcription = sum(
    not bool(x.get("transcription"))
    for x in data
)

print()
print("==============================")
print("FINISHED BATCH")
print("==============================")

print(
    "ADDED COMMENTS:",
    added_comments
)

print(
    "ADDED TRANSCRIPTS:",
    added_transcripts
)

print(
    "TOTAL ATTEMPTED:",
    len(attempted)
)

print()
print("CURRENT DATASET:")

print(
    "TOTAL:",
    len(data)
)

print(
    "COMMENTS:",
    with_comments
)

print(
    "TRANSCRIPTION:",
    with_transcription
)

print(
    "BOTH:",
    with_both
)

print(
    "MISSING COMMENTS:",
    missing_comments
)

print(
    "MISSING TRANSCRIPTION:",
    missing_transcription
)