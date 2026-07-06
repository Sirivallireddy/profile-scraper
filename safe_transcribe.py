import json
import subprocess
import sys
import urllib.parse
from pathlib import Path

from faster_whisper import WhisperModel

# ==========================================
# SETTINGS
# ==========================================
JSON_PATH = Path("output/kunal_shah_videos.json")
ATTEMPTED_PATH = Path("output/transcription_attempted.json")
AUDIO_DIR = Path("temp_transcription_audio")

BATCH_SIZE = 5

# tiny = fastest, lower accuracy
# base = good first test
# small = better accuracy, slower
MODEL_SIZE = "base"

AUDIO_DIR.mkdir(
    parents=True,
    exist_ok=True
)

# ==========================================
# LOAD MAIN JSON
# ==========================================
data = json.loads(
    JSON_PATH.read_text(
        encoding="utf-8"
    )
)

# ==========================================
# LOAD ATTEMPTED TRACKER
# ==========================================
if ATTEMPTED_PATH.exists():
    try:
        attempted = set(
            json.loads(
                ATTEMPTED_PATH.read_text(
                    encoding="utf-8"
                )
            )
        )
    except Exception:
        attempted = set()
else:
    attempted = set()

# ==========================================
# SELECT NEXT 5 MISSING TRANSCRIPTIONS
# ==========================================
targets = [
    record
    for record in data
    if not record.get("transcription")
    and record.get("video_link")
    and record.get("video_link") not in attempted
][:BATCH_SIZE]

print("TOTAL RECORDS:", len(data))

print(
    "CURRENT TRANSCRIPTIONS:",
    sum(
        bool(x.get("transcription"))
        for x in data
    )
)

print(
    "CURRENT COMMENTS:",
    sum(
        bool(x.get("comments"))
        for x in data
    )
)

print(
    "ALREADY TRANSCRIPTION ATTEMPTED:",
    len(attempted)
)

print(
    "BATCH TARGETS:",
    len(targets)
)

if not targets:
    print("NO NEW TRANSCRIPTION TARGETS LEFT")
    sys.exit(0)

# ==========================================
# LOAD WHISPER MODEL ONCE
# ==========================================
print()
print("LOADING WHISPER MODEL:", MODEL_SIZE)
print("First run may download the model...")

try:
    model = WhisperModel(
        MODEL_SIZE,
        device="cpu",
        compute_type="int8"
    )
except Exception as e:
    print(
        "MODEL LOAD FAILED:",
        type(e).__name__,
        str(e)
    )
    sys.exit(1)

print("WHISPER MODEL READY")

added_transcripts = 0
failed = 0

# ==========================================
# PROCESS VIDEOS
# ==========================================
for i, record in enumerate(targets, 1):

    url = record.get(
        "video_link",
        ""
    )

    parsed = urllib.parse.urlparse(url)

    video_id = urllib.parse.parse_qs(
        parsed.query
    ).get("v", [None])[0]

    print()
    print(
        f"[{i}/{len(targets)}] PROCESSING {url}"
    )

    if not video_id:
        print("  SKIP: NO VIDEO ID")
        attempted.add(url)
        failed += 1

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
    # NEVER OVERWRITE EXISTING TRANSCRIPT
    # ======================================
    if record.get("transcription"):
        print(
            "  TRANSCRIPTION ALREADY EXISTS"
        )
        attempted.add(url)
        continue

    video_dir = AUDIO_DIR / video_id

    video_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    output_template = str(
        video_dir / "audio.%(ext)s"
    )

    # ======================================
    # DOWNLOAD AUDIO ONLY
    # ======================================
    cmd = [
        sys.executable,
        "-m",
        "yt_dlp",

        "-f",
        "bestaudio/best",

        "--no-playlist",

        "-o",
        output_template,

        url
    ]

    print("  DOWNLOADING AUDIO...")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600
        )

    except subprocess.TimeoutExpired:
        print("  AUDIO DOWNLOAD TIMEOUT")

        attempted.add(url)
        failed += 1

        ATTEMPTED_PATH.write_text(
            json.dumps(
                sorted(attempted),
                indent=2,
                ensure_ascii=False
            ),
            encoding="utf-8"
        )

        continue

    except Exception as e:
        print(
            "  AUDIO DOWNLOAD FAIL:",
            type(e).__name__
        )

        attempted.add(url)
        failed += 1
        continue

    # ======================================
    # FIND DOWNLOADED AUDIO FILE
    # ======================================
    audio_files = [
        p
        for p in video_dir.glob("audio.*")
        if p.is_file()
        and not p.name.endswith(
            ".part"
        )
    ]

    if not audio_files:
        print(
            "  NO AUDIO FILE FOUND"
        )

        if result.stderr:
            print(
                "  YT-DLP:",
                result.stderr[-300:]
            )

        attempted.add(url)
        failed += 1

        ATTEMPTED_PATH.write_text(
            json.dumps(
                sorted(attempted),
                indent=2,
                ensure_ascii=False
            ),
            encoding="utf-8"
        )

        continue

    audio_file = audio_files[0]

    print(
        "  AUDIO READY:",
        audio_file.name
    )

    # ======================================
    # TRANSCRIBE WITH WHISPER
    # ======================================
    print(
        "  TRANSCRIBING..."
    )

    try:
        segments, info = model.transcribe(
            str(audio_file),

            beam_size=1,

            vad_filter=True
        )

        transcript_parts = []

        for segment in segments:

            text = (
                segment.text
                or ""
            ).strip()

            if text:
                transcript_parts.append(
                    text
                )

        new_transcription = (
            "\n\n".join(
                transcript_parts
            )
        )

        # ==================================
        # SAFE WRITE
        # NEVER OVERWRITE GOOD TRANSCRIPT
        # ==================================
        if (
            new_transcription
            and not record.get(
                "transcription"
            )
        ):
            record[
                "transcription"
            ] = new_transcription

            added_transcripts += 1

            print(
                "  TRANSCRIPTION OK"
            )

            print(
                "  CHARACTERS:",
                len(new_transcription)
            )

        else:
            print(
                "  TRANSCRIPTION EMPTY"
            )

            failed += 1

    except Exception as e:
        print(
            "  WHISPER FAIL:",
            type(e).__name__,
            str(e)[:200]
        )

        failed += 1

    # ======================================
    # MARK ATTEMPTED
    # ======================================
    attempted.add(url)

    # ======================================
    # SAVE TRACKER AFTER EVERY VIDEO
    # ======================================
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

    # ======================================
    # DELETE AUDIO AFTER TRANSCRIPTION
    # Saves disk space
    # ======================================
    try:
        audio_file.unlink()
    except Exception:
        pass

# ==========================================
# FINAL SAFE SAVE
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

missing_transcription = sum(
    not bool(x.get("transcription"))
    for x in data
)

print()
print("==============================")
print("FINISHED TRANSCRIPTION BATCH")
print("==============================")

print(
    "ADDED TRANSCRIPTS:",
    added_transcripts
)

print(
    "FAILED:",
    failed
)

print(
    "TOTAL TRANSCRIPTION ATTEMPTED:",
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
    "MISSING TRANSCRIPTION:",
    missing_transcription
)