"""Phase 2: build data/clean/<handle>/<video_id>.json from data/raw.

For every segment, keeps the original `text` and adds:
  clean_text  - transcription errors fixed (data/corrections.yaml + data/clean_overrides/<id>.yaml),
                filler (um/uh) and stutter repeats removed, non-speech tags removed
  changes     - list of {from, to, rule, uncertain}
Timestamps are copied unchanged. Uncertain fixes are written as "<best guess> [?]".
Never edits raw files. Rerunning overwrites the clean file for that video.

Usage: uv run scripts/clean.py [--ids ID ...] [--channel HANDLE]
"""
import argparse, datetime as dt, glob, json, os, re
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION = "1.2"
VOCAB = set(w for line in open(os.path.join(ROOT, "config", "coaching_vocab.txt"))
            if not line.startswith("#") for w in line.split())


def load_rules():
    r = yaml.safe_load(open(os.path.join(ROOT, "data", "corrections.yaml")))
    r["_global"] = [(re.compile(g["pattern"], re.I), g["to"], g.get("keep_plural", False)) for g in r["global"]]
    r["_filler"] = re.compile(r"(?:,\s*)?\b(?:%s)\b,?\s*" % "|".join(r["filler_words"]), re.I)
    r["_tags"] = re.compile("|".join(r["nonspeech_tags"]), re.I)
    r["_repeat"] = re.compile(r"\b(\w+)((?:\s+\1\b)+)", re.I)
    return r


def apply_global(t, rules, changes):
    for rx, to, keep_plural in rules["_global"]:
        def sub(m):
            new = m.expand(to)
            if keep_plural and m.group(0).lower().endswith("s"):
                new += "s"
            if m.group(0)[0].isupper() and new[0].islower():
                new = new[0].upper() + new[1:]
            if new != m.group(0):
                changes.append({"from": m.group(0), "to": new, "rule": "glossary", "uncertain": False})
            return new
        t = rx.sub(sub, t)
    return t


def strip_filler(t, rules, changes):
    def tag(m):
        changes.append({"from": m.group(0).strip(), "to": "", "rule": "nonspeech", "uncertain": False}); return ""
    t = rules["_tags"].sub(tag, t)

    def fil(m):
        changes.append({"from": m.group(0).strip(), "to": "", "rule": "filler", "uncertain": False}); return " "
    t = rules["_filler"].sub(fil, t)

    def rep(m):
        if m.group(1).lower() in rules["repeat_keep"]:
            return m.group(0)
        changes.append({"from": m.group(0), "to": m.group(1), "rule": "repeat", "uncertain": False})
        return m.group(1)
    t = rules["_repeat"].sub(rep, t)
    t = re.sub(r"^>>\s*$", "", t.strip())
    t = re.sub(r"\s{2,}", " ", t).strip()
    return t


def apply_overrides(segs_clean, segs_changes, overrides, vid):
    problems = []
    for o in overrides:
        i = o["seg"]
        t = segs_clean[i]
        if o["from"] not in t:
            problems.append(f"{vid} seg {i}: '{o['from']}' not found in '{t}'"); continue
        to = o["to"] + (" [?]" if o.get("uncertain") else "")
        segs_clean[i] = t.replace(o["from"], to, 1)
        segs_changes[i].append({"from": o["from"], "to": to, "rule": "override",
                                "uncertain": bool(o.get("uncertain")), **({"note": o["note"]} if o.get("note") else {})})
    return problems


def clean_file(path, rules):
    d = json.load(open(path))
    vid = d["video_id"]
    clean, changes = [], []
    for s in d["segments"]:
        ch = []
        t = s["text"].replace("\n", " ")
        t = apply_global(t, rules, ch)
        t = strip_filler(t, rules, ch)
        clean.append(t); changes.append(ch)
    ov_path = os.path.join(ROOT, "data", "clean_overrides", f"{vid}.yaml")
    overrides = yaml.safe_load(open(ov_path)) if os.path.exists(ov_path) else []
    problems = apply_overrides(clean, changes, overrides or [], vid)
    out = dict(d)
    out["segments"] = [{"start": s["start"], "end": s["end"], "text": s["text"],
                        "clean_text": c, "changes": ch}
                       for s, c, ch in zip(d["segments"], clean, changes)]
    words = sum(len(c.split()) for c in clean)
    # Content check: share of words that are coaching vocabulary (config/coaching_vocab.txt).
    # Lyrics, music-only clips and casual chatter score ~0; coaching scores 0.04-0.2.
    toks = re.findall(r"[a-z']+", " ".join(clean).lower())
    vocab_hits = sum(t in VOCAB for t in toks)
    ratio = vocab_hits / len(toks) if toks else 0.0
    out["has_speech"] = words >= 15
    # Long videos are almost always coaching even when talk drifts (workouts, interviews), so they get a
    # much lower cutoff; the strict cutoff is aimed at music/lyric Shorts.
    cutoff = 0.02 if d.get("is_short") else 0.005
    out["coaching_content"] = words >= 15 and ratio >= cutoff
    out["coaching_vocab_ratio"] = round(ratio, 3)
    out["cleaning"] = {"version": VERSION, "cleaned_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                       "rules": "data/corrections.yaml", "overrides": os.path.relpath(ov_path, ROOT) if overrides else None,
                       "n_changes": sum(len(c) for c in changes),
                       "n_uncertain": sum(1 for c in changes for x in c if x["uncertain"])}
    dest = path.replace(os.sep + "raw" + os.sep, os.sep + "clean" + os.sep)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".tmp"
    json.dump(out, open(tmp, "w"), ensure_ascii=False, indent=1)
    os.replace(tmp, dest)
    return out, problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--channel")
    a = ap.parse_args()
    rules = load_rules()
    for p in sorted(glob.glob(os.path.join(ROOT, "data", "raw", a.channel or "*", "*.json"))):
        vid = os.path.basename(p)[:-5]
        if a.ids and vid not in a.ids:
            continue
        out, problems = clean_file(p, rules)
        c = out["cleaning"]
        print(f"{out['channel_handle']}/{vid}: {c['n_changes']} changes, {c['n_uncertain']} uncertain, coaching_content={out['coaching_content']} ({out['coaching_vocab_ratio']})")
        for pr in problems:
            print("  OVERRIDE NOT APPLIED:", pr)


if __name__ == "__main__":
    main()
