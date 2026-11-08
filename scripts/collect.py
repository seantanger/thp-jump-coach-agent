"""Phase 1: download transcripts for listed videos into data/raw/<handle>/<video_id>.json.

Incremental: videos that already have a raw file are skipped (use --force to redo).
Prefers manual English captions, falls back to auto-generated (both via yt-dlp).
Stops cleanly if YouTube rate-limits (HTTP 429) so nothing is wrongly logged as failed. Videos with no
transcript are appended to logs/failed.txt. Rebuilds data/videos_index.csv at the end.

Usage:
  uv run scripts/collect.py --ids ID1 ID2 ...     # specific videos (pilot)
  uv run scripts/collect.py [--channel HANDLE] [--tab videos|shorts] [--limit N]   # everything listed
  uv run scripts/collect.py --index-only          # just rebuild the index
Run scripts/list_videos.py first.
"""
import argparse, csv, datetime as dt, glob, json, os, random, sys, time
import html, xml.etree.ElementTree as ET
import yaml, yt_dlp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EN = ["en", "en-US", "en-GB", "en-CA"]
FAILED = os.path.join(ROOT, "logs", "failed.txt")
INDEX = os.path.join(ROOT, "data", "videos_index.csv")


def load_listings():
    rows = {}
    for p in sorted(glob.glob(os.path.join(ROOT, "data", "listings", "*.csv"))):
        for r in csv.DictReader(open(p)):
            rows[r["video_id"]] = r
    return rows


def channel_names():
    cfg = yaml.safe_load(open(os.path.join(ROOT, "config", "channels.yaml")))
    return {c["handle"]: c["name"] for c in cfg["channels"]}


def raw_path(handle, vid):
    return os.path.join(ROOT, "data", "raw", handle, f"{vid}.json")


def log_failed(handle, vid, reason):
    os.makedirs(os.path.dirname(FAILED), exist_ok=True)
    with open(FAILED, "a") as f:
        reason = " ".join(str(reason).split())[:300]  # one line per entry
        f.write(f"{dt.datetime.now().isoformat(timespec='seconds')}\t{handle}\t{vid}\t{reason}\n")


class RateLimited(Exception):
    """YouTube is throttling this IP. Stop the run; nothing is logged as a permanent failure."""


BLOCK_SIGNS = ("429", "Too Many Requests", "not a bot", "IpBlocked", "RequestBlocked")


def fetch_meta(ydl, vid):
    try:
        return ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
    except Exception as e:
        if any(b in str(e) for b in BLOCK_SIGNS):
            raise RateLimited(str(e)[:200])
        raise


def pick_track(meta):
    """Manual English captions first, then English auto captions (en-orig = original-language ASR)."""
    subs, auto = meta.get("subtitles") or {}, meta.get("automatic_captions") or {}
    for lang in EN + sorted(k for k in subs if k.startswith("en")):
        if lang in subs:
            return subs[lang], "manual", lang
    for lang in ["en-orig", "en"]:
        if lang in auto:
            return auto[lang], "auto", "en"
    return None, None, None


def fetch_transcript(ydl, meta):
    track, kind, lang = pick_track(meta)
    if track is None:
        return None, None, None
    fmt = next((f for f in track if f.get("ext") == "srv1"), None)
    if fmt is None:
        raise ValueError("no srv1 caption format offered")
    try:
        xml = ydl.urlopen(fmt["url"]).read().decode("utf-8")
    except Exception as e:
        if any(b in str(e) for b in BLOCK_SIGNS):
            raise RateLimited(str(e)[:200])
        raise
    segs = []
    for t in ET.fromstring(xml).findall("text"):
        start, dur = float(t.get("start", 0)), float(t.get("dur", 0))
        txt = html.unescape("".join(t.itertext())).strip()
        if txt:
            segs.append({"start": round(start, 3), "end": round(start + dur, 3), "text": txt})
    return segs, kind, lang


def collect_one(ydl, row, names, force=False, fails=None):
    handle, vid = row["channel_handle"], row["video_id"]
    out = raw_path(handle, vid)
    if os.path.exists(out) and not force:
        return "skipped"
    reason = (fails or {}).get(vid, "")
    if (reason.startswith("no English captions") or "confirm your age" in reason) and not force:
        return "skipped"  # permanent failure already logged; use --force to retry (other errors are retried)
    try:
        meta = fetch_meta(ydl, vid)
    except RateLimited:
        raise
    except Exception as e:
        log_failed(handle, vid, f"metadata error: {e}"); return "failed"
    try:
        segs, kind, lang = fetch_transcript(ydl, meta)
    except RateLimited:
        raise
    except Exception as e:
        log_failed(handle, vid, f"transcript error: {type(e).__name__}: {e}"); return "failed"
    if segs is None:
        log_failed(handle, vid, "no English captions on YouTube (usually no speech: music/b-roll)"); return "failed"
    if not segs:
        log_failed(handle, vid, "caption track empty"); return "failed"
    ud = meta.get("upload_date") or ""
    doc = {
        "video_id": vid,
        "channel_id": meta.get("channel_id") or row.get("channel_id", ""),
        "channel_handle": handle,
        "channel_name": names.get(handle, meta.get("channel", "")),
        "title": meta.get("title") or row["title"],
        "url": f"https://www.youtube.com/{'shorts/' if row['is_short'] == 'True' else 'watch?v='}{vid}",
        "upload_date": f"{ud[:4]}-{ud[4:6]}-{ud[6:]}" if len(ud) == 8 else "",
        "duration_seconds": int(meta.get("duration") or 0),
        "is_short": row["is_short"] == "True",
        "source_tab": row["source_tab"],
        "caption_type": kind,
        "caption_language": lang,
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "tool": f"yt-dlp {yt_dlp.version.__version__} (metadata + srv1 captions)",
        "description": meta.get("description") or "",
        "segments": segs,
    }
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = out + ".tmp"
    json.dump(doc, open(tmp, "w"), ensure_ascii=False, indent=1)
    os.replace(tmp, out)
    return "collected"


def failed_ids():
    if not os.path.exists(FAILED):
        return {}
    d = {}
    for line in open(FAILED):
        p = line.rstrip("\n").split("\t")
        if len(p) >= 4:
            d[p[2]] = p[3]
    return d


def build_index(listings):
    fails = failed_ids()
    fields = ["channel_handle", "video_id", "title", "url", "upload_date", "duration",
              "is_short", "source_tab", "caption_type", "status"]
    with open(INDEX, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for vid, r in listings.items():
            p = raw_path(r["channel_handle"], vid)
            if os.path.exists(p):
                d = json.load(open(p))
                w.writerow({"channel_handle": r["channel_handle"], "video_id": vid, "title": d["title"],
                            "url": d["url"], "upload_date": d["upload_date"], "duration": d["duration_seconds"],
                            "is_short": d["is_short"], "source_tab": d["source_tab"],
                            "caption_type": d["caption_type"], "status": "collected"})
            else:
                short = r["is_short"] == "True"
                w.writerow({"channel_handle": r["channel_handle"], "video_id": vid, "title": r["title"],
                            "url": f"https://www.youtube.com/{'shorts/' if short else 'watch?v='}{vid}",
                            "upload_date": "", "duration": r["duration"], "is_short": short,
                            "source_tab": r["source_tab"], "caption_type": "",
                            "status": "failed" if vid in fails else "pending"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--channel")
    ap.add_argument("--tab", choices=["videos", "shorts", "streams"], help="only this channel tab")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--index-only", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="max videos this run (0 = no limit)")
    ap.add_argument("--sleep", type=float, default=20.0, help="base pause between videos, seconds")
    a = ap.parse_args()
    listings, names = load_listings(), channel_names()
    if not a.index_only:
        todo = [listings[i] for i in a.ids] if a.ids else \
               [r for r in listings.values() if (not a.channel or r["channel_handle"] == a.channel)
                and (not a.tab or r["source_tab"] == a.tab)]
        n, fails = 0, failed_ids()
        opts = {"quiet": True, "no_warnings": True, "skip_download": True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            for r in todo:
                try:
                    res = collect_one(ydl, r, names, a.force, fails)
                except RateLimited as e:
                    print(f"RATE LIMITED at {r['video_id']}: {e}\nStopping. Wait (an hour or more) and rerun; "
                          "finished videos are skipped automatically.", flush=True)
                    build_index(listings); sys.exit(3)
                print(f"{res:9} {r['channel_handle']}/{r['video_id']} {r['title'][:60]}", flush=True)
                if res != "skipped":
                    n += 1
                    if a.limit and n >= a.limit: break
                    time.sleep(a.sleep + random.uniform(0, a.sleep / 2))
    build_index(listings)


if __name__ == "__main__":
    main()
