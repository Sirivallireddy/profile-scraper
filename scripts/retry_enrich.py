import json
import time
import subprocess
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_JSON = ROOT / "output" / "kunal_shah_videos.json"
TEMP_ROOT = ROOT / "temp"
MAX_COMMENT_COUNT = 50


def parse_comments_json(path: Path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None


def read_info(path: Path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None


if __name__ == '__main__':
    if not OUTPUT_JSON.exists():
        print('no output file')
        sys.exit(1)
    data = json.loads(OUTPUT_JSON.read_text(encoding='utf-8'))
    changed = 0
    for rec in data:
        link = rec.get('video_link')
        if not link:
            continue
        has_trans = bool(rec.get('transcription'))
        has_comments = bool(rec.get('comments') and len(rec.get('comments'))>0)
        if has_trans and has_comments:
            continue
        print('Retrying:', link)
        parsed = urllib.parse.urlparse(link)
        video_id = None
        try:
            if 'youtube' in parsed.netloc:
                video_id = urllib.parse.parse_qs(parsed.query).get('v',[None])[0]
        except Exception:
            video_id = None
        temp_dir = TEMP_ROOT / (video_id or f"retry_{int(time.time())}")
        temp_dir.mkdir(parents=True, exist_ok=True)
        output_template = str(temp_dir / '%(id)s.%(ext)s')
        success = False
        for attempt in range(2):
            try:
                cmd = [sys.executable, '-m', 'yt_dlp', '--skip-download', '--write-info-json', '--write-comments', '--write-auto-subs', '--write-subs', '--sub-langs', 'en', '-o', output_template, link]
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
                # proceed to parse files
                info = None
                if video_id:
                    cand = [temp_dir / f"{video_id}.info.json", temp_dir / "info.json"]
                else:
                    cand = [temp_dir / "info.json"]
                info_path = None
                for p in cand:
                    if p.exists():
                        info_path = p
                        break
                if info_path is None:
                    files = list(temp_dir.glob('*.info.json'))
                    info_path = files[0] if files else None
                if info_path:
                    info = read_info(info_path)
                    if info and not rec.get('transcription'):
                        # no transcript here, leave
                        pass
                # comments
                comments = []
                comm_path = None
                if video_id:
                    for p in [temp_dir / f"{video_id}.comments.json", temp_dir / "comments.json"]:
                        if p.exists():
                            comm_path = p
                            break
                else:
                    if (temp_dir / 'comments.json').exists():
                        comm_path = temp_dir / 'comments.json'
                if comm_path and comm_path.exists():
                    data_comm = parse_comments_json(comm_path)
                    if isinstance(data_comm, dict) and data_comm.get('comments'):
                        items = data_comm.get('comments')
                    elif isinstance(data_comm, list):
                        items = data_comm
                    else:
                        items = []
                    comments = []
                    for item in items[:MAX_COMMENT_COUNT]:
                        text = item.get('text') or item.get('comment') or item.get('content') or ''
                        comments.append({'comment_text': text.strip(), 'author': item.get('author'), 'like_count': item.get('like_count') or item.get('likes') or 0, 'timestamp': None})
                if comments:
                    rec['comments'] = comments
                # transcript fallback: look for .vtt
                if not rec.get('transcription'):
                    texts = []
                    for file in list(temp_dir.glob('*.vtt')) + list(temp_dir.glob('*.en.vtt')):
                        try:
                            txt = file.read_text(encoding='utf-8')
                        except Exception:
                            continue
                        lines = [l.strip() for l in txt.splitlines()]
                        current = None
                        timepat = None
                        segs = []
                        for line in lines:
                            if not line:
                                if current:
                                    segs.append(current)
                                    current = None
                                continue
                            if '-->' in line:
                                if current:
                                    segs.append(current)
                                parts = line.split('-->')
                                current = {'start_time': parts[0].strip(), 'end_time': parts[1].strip(), 'text': ''}
                                continue
                            if current is not None:
                                current['text'] += (' ' if current['text'] else '') + line
                        if current:
                            segs.append(current)
                        for s in segs:
                            if s.get('text'):
                                texts.append(s.get('text').strip())
                    if texts:
                        rec['transcription'] = '\n\n'.join(texts)
                # write after each success attempt
                OUTPUT_JSON.write_text(json.dumps(data, indent=2), encoding='utf-8')
                success = True
                changed += 1
                break
            except Exception as e:
                print('attempt failed', attempt, link, type(e).__name__, e)
                time.sleep(2)
        time.sleep(1)
    print('finished; updated', changed)
    OUTPUT_JSON.write_text(json.dumps(data, indent=2), encoding='utf-8')
