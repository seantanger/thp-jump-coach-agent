"""Corpus statistics for REPORT.md. Usage: uv run scripts/stats.py"""
import csv, collections, glob, json, os, re
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
idx = list(csv.DictReader(open(os.path.join(ROOT, "data", "videos_index.csv"))))
out = {}
for tab in ("videos", "shorts"):
    out[tab] = collections.Counter((r["channel_handle"], r["status"]) for r in idx if r["source_tab"] == tab)
cap = collections.Counter(); secs = collections.Counter(); segs = 0; words = 0
glossary = collections.Counter(); overrides = 0; uncertain = 0; noncoach = []
years = collections.Counter()
for p in glob.glob(os.path.join(ROOT, "data", "clean", "*", "*.json")):
    d = json.load(open(p))
    if d["is_short"]:
        continue
    ch = d["channel_handle"]
    cap[(ch, d["caption_type"])] += 1
    secs[ch] += d["duration_seconds"]
    years[(ch, d["upload_date"][:4])] += 1
    segs += len(d["segments"])
    for s in d["segments"]:
        words += len(s["clean_text"].split())
        for c in s["changes"]:
            if c["rule"] == "glossary":
                glossary[(c["from"].lower(), c["to"])] += 1
            if c["uncertain"]:
                uncertain += 1
    if not d.get("coaching_content", True):
        noncoach.append(f'{ch}/{d["video_id"]} {d["title"][:60]}')
fails = collections.Counter()
for line in open(os.path.join(ROOT, "logs", "failed.txt")):
    p = line.rstrip("\n").split("\t")
    if len(p) >= 4:
        vid = p[2]
        if not glob.glob(os.path.join(ROOT, "data", "raw", "*", vid + ".json")):
            fails[p[3].split(" (")[0][:60]] += 1
print("INDEX", {k: dict(v) for k, v in out.items()})
print("CAPTIONS", dict(cap))
print("HOURS", {k: round(v / 3600, 1) for k, v in secs.items()}, "total", round(sum(secs.values()) / 3600, 1))
print("SEGMENTS", segs, "WORDS", words, "UNCERTAIN", uncertain)
print("FAILS", dict(fails))
print("YEARS", sorted(years.items()))
print("TOP_GLOSSARY", glossary.most_common(25))
print("NONCOACH", noncoach)
