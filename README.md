# Profile Scraper

Profile Scraper is a Python-based content discovery and enrichment pipeline designed to collect publicly available video content related to a target person or profile.

The current implementation primarily focuses on YouTube-based discovery and extraction. It collects relevant video records and enriches them with available metadata, comments, captions, and transcriptions.

## Current Dataset

Current Kunal Shah collection:

- 1000+ video records
- Up to 50 comments collected per video

## Features

- Discovers relevant videos related to a target profile
- Collects video URLs
- Extracts video titles
- Extracts descriptions and captions
- Collects available comments
- Limits comments to a maximum of 50 per video
- Retrieves available transcripts and captions
- Supports incremental enrichment
- Avoids unnecessary duplicate processing
- Preserves previously collected data
- Saves results in structured JSON format
- Supports resume-safe processing through progress tracking

## Output Format

Each record follows a structure similar to:

```json
{
  "video_link": "https://www.youtube.com/watch?v=VIDEO_ID",
  "platform": "youtube",
  "title": "Video title",
  "caption": "Video description",
  "transcription": "Available transcription text",
  "comments": [
    {
      "comment_text": "Example comment"
    }
  ]
}
```

## Project Structure

```text
profile-scraper/
├── pipeline.py
├── safe_enrich.py
├── safe_transcribe.py
├── requirements.txt
├── output/
│   └── kunal_shah_videos.json
├── scripts/
│   └── retry_enrich.py
└── tests/
    └── test_pipeline.py
```

## Installation

Clone the repository:

```bash
git clone https://github.com/Sirivallireddy/profile-scraper.git
cd profile-scraper
```

Create a virtual environment:

```bash
python -m venv .venv
```

Activate the virtual environment on Windows:

```bash
.venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## Running the Pipeline

Run the main collection pipeline:

```bash
python pipeline.py
```

Run incremental enrichment for missing comments and available transcripts:

```bash
python safe_enrich.py
```

Run the local audio transcription fallback:

```bash
python safe_transcribe.py
```

## Data Collection Workflow

The pipeline follows this general workflow:

1. Discover relevant public video URLs
2. Normalize and deduplicate URLs
3. Extract video metadata
4. Collect titles and descriptions
5. Attempt transcript and caption extraction
6. Collect up to 50 available comments per video
7. Save records incrementally
8. Retry incomplete records through enrichment scripts
9. Preserve successfully collected data
10. Store the final dataset in JSON format

## Notes and Limitations

The current dataset is primarily sourced from YouTube.

Comments and transcriptions may be unavailable for some videos because of:

- Disabled comments
- Disabled captions
- Missing transcript tracks
- Deleted or unavailable videos
- Platform restrictions
- Rate limits
- IP-based restrictions

The pipeline preserves successfully collected data and keeps unavailable fields empty when extraction is not possible.

## Current Results

The current collection contains 828 relevant records.

Coverage achieved:

- Comments available for 421 records
- Transcriptions available for 160 records
- Both comments and transcriptions available for 104 records

The remaining records are retained with available metadata so they can be incrementally enriched in future runs.

## Future Improvements

- Generic target-person input
- Single-command execution
- Multi-platform discovery
- Instagram content extraction
- X/Twitter content discovery
- LinkedIn content discovery
- Podcast and broader web-source integration
- Unified cross-platform deduplication
- Improved transcription fallback
- Configurable target count
- Parallelized enrichment with safe checkpointing

## Author

Sirivalli Reddy
Each record follows a structure similar to:

```json
{
  "video_link": "https://www.youtube.com/watch?v=VIDEO_ID",
  "platform": "youtube",
  "title": "Video title",
  "caption": "Video description",
  "transcription": "Available transcription text",
  "comments": [
    {
      "comment_text": "Example comment"
    }
  ]
}
