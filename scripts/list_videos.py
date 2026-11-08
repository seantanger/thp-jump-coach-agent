"""List every video on each channel in config/channels.yaml.

Reads the channel's /videos, /shorts and /streams tabs (flat listing, no per-video
requests) and writes data/listings/<handle>.csv. Shorts are identified by the tab
they appear on, not by duration.

Usage: uv run scripts/list_videos.py [--channel HANDLE]
"""
import argparse, csv, os, sys, time
import yaml, yt_dlp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TABS = ["videos", "shorts", "streams"]


def list_tab(url, tab):
    opts = {"extract_flat": True, "quiet": True, "no_warnings": True, "ignoreerrors": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"{url}/{tab}", download=False)
    if not info:
        return [], {}
    return info.get("entries") or [], info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel")
    args = ap.parse_args()
    cfg = yaml.safe_load(open(os.path.join(ROOT, "config", "channels.yaml")))
    os.makedirs(os.path.join(ROOT, "data", "listings"), exist_ok=True)
    for ch in cfg["channels"]:
        if args.channel and ch["handle"] != args.channel:
            continue
        rows, seen = [], set()
        for tab in TABS:
            entries, info = list_tab(ch["url"], tab)
            print(f"{ch['handle']}/{tab}: {len(entries)}", file=sys.stderr)
            for e in entries:
                if not e or e.get("id") in seen:
                    continue
                seen.add(e["id"])
                rows.append({
                    "channel_handle": ch["handle"],
                    "channel_id": info.get("channel_id") or "",
                    "video_id": e["id"],
                    "title": e.get("title") or "",
                    "duration": e.get("duration") or "",
                    "view_count": e.get("view_count") or "",
                    "is_short": tab == "shorts",
                    "source_tab": tab,
                })
            time.sleep(2)
        out = os.path.join(ROOT, "data", "listings", f"{ch['handle']}.csv")
        with open(out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["video_id"])
            w.writeheader(); w.writerows(rows)
        print(f"wrote {out} ({len(rows)} videos)", file=sys.stderr)


if __name__ == "__main__":
    main()
