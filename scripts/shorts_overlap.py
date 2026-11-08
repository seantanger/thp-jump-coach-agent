"""Measure how many collected Shorts are clips of collected long videos.

For each Short, takes word 6-grams of its transcript and finds the long video (any channel)
containing the largest share of them. Classifies:
  clip      >= 50% of the Short's 6-grams appear in one long video
  partial   20-50%
  original  < 20%
  no_speech fewer than 15 spoken words (music / b-roll)
Also reports the matched start time in the long video and whether the Short's
description links to a long video. Writes data/shorts_overlap.csv.

Usage: uv run scripts/shorts_overlap.py
"""
import csv, glob, json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
N = 6
TAG = re.compile(r"\[[^\]]*\]|>>")


def words(t):
    return re.findall(r"[a-z0-9']+", TAG.sub(" ", t.lower()))


def load():
    shorts, longs = [], []
    for p in glob.glob(os.path.join(ROOT, "data", "raw", "*", "*.json")):
        d = json.load(open(p))
        (shorts if d["is_short"] else longs).append(d)
    return shorts, longs


def main():
    shorts, longs = load()
    idx = {}
    for L in longs:
        seq = []  # (word, segment start)
        for s in L["segments"]:
            seq += [(w, s["start"]) for w in words(s["text"])]
        grams = {}
        for i in range(len(seq) - N + 1):
            grams.setdefault(tuple(w for w, _ in seq[i:i + N]), seq[i][1])
        idx[L["video_id"]] = (L, grams)
    rows = []
    for S in shorts:
        w = [x for s in S["segments"] for x in words(s["text"])]
        g = [tuple(w[i:i + N]) for i in range(len(w) - N + 1)]
        best, share, at = None, 0.0, None
        if g:
            for vid, (L, grams) in idx.items():
                hits = [grams[x] for x in g if x in grams]
                sh = len(hits) / len(g)
                if sh > share:
                    best, share, at = L, sh, min(hits)
        if len(w) < 15:
            cls = "no_speech"
        elif share >= 0.5:
            cls = "clip"
        elif share >= 0.2:
            cls = "partial"
        else:
            cls = "original"
        desc_link = bool(re.search(r"youtu(\.be/|be\.com/watch)", S["description"] or ""))
        rows.append({
            "channel_handle": S["channel_handle"], "short_id": S["video_id"], "title": S["title"][:90],
            "upload_date": S["upload_date"], "words": len(w), "class": cls, "match_share": round(share, 2),
            "source_video_id": best["video_id"] if best and cls in ("clip", "partial") else "",
            "source_channel": best["channel_handle"] if best and cls in ("clip", "partial") else "",
            "source_upload_date": best["upload_date"] if best and cls in ("clip", "partial") else "",
            "source_start": round(at, 1) if at is not None and cls in ("clip", "partial") else "",
            "description_links_video": desc_link,
        })
    rows.sort(key=lambda r: (r["channel_handle"], r["upload_date"]), reverse=True)
    out = os.path.join(ROOT, "data", "shorts_overlap.csv")
    with open(out, "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0].keys())); wr.writeheader(); wr.writerows(rows)
    from collections import Counter
    for h in sorted({r["channel_handle"] for r in rows}):
        print(h, dict(Counter(r["class"] for r in rows if r["channel_handle"] == h)))
    print(f"compared against {len(longs)} long videos; wrote {out}")


if __name__ == "__main__":
    main()
