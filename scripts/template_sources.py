"""Print one video's chunks in time order, for drafting templates by hand. Reads only; writes nothing.

Usage:
    uv run python -m scripts.template_sources Icml891MLHA
    uv run python -m scripts.template_sources 9X_j-oF2ZDg --grep "quarter squat|stairs"
    uv run python -m scripts.template_sources --find "Full Blueprint"     # list matching videos
"""

from __future__ import annotations

import argparse
import re

from src.kb.paths import load_chunks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("video_id", nargs="?")
    parser.add_argument("--grep", help="only chunks whose text matches this regex (case-insensitive)")
    parser.add_argument("--find", help="list videos whose title matches this regex")
    parser.add_argument("--method", default="charsplit_matched")
    args = parser.parse_args()

    chunks = load_chunks(args.method)
    if args.find:
        seen = {}
        for c in chunks:
            if re.search(args.find, c["title"], re.I):
                seen.setdefault(c["video_id"], (c["channel_name"], c["upload_date"], c["title"]))
        for vid, (channel, uploaded, title) in sorted(seen.items(), key=lambda kv: kv[1][1]):
            print(f"{vid}  {uploaded}  {channel} – {title}")
        return
    hits = sorted((c for c in chunks if c["video_id"] == args.video_id), key=lambda c: c["start"])
    if not hits:
        raise SystemExit(f"no chunks for {args.video_id}")
    print(f"# {hits[0]['channel_name']} – {hits[0]['title']} ({hits[0]['upload_date']})\n")
    for c in hits:
        if args.grep and not re.search(args.grep, c["text"], re.I):
            continue
        print(f"{c['chunk_id']}  {c['timestamp']}  {c['text']}\n")


if __name__ == "__main__":
    main()
