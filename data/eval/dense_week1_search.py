"""One-off: dense search (your default: charsplit_matched + nomic) for week-1 planning questions.
Run from jump-coach-agent:  PYTHONPATH=. uv run python ../data/eval/dense_week1_search.py
Writes ../data/eval/dense_week1_results.txt
"""
from pathlib import Path
from src.kb.search import search

QUERIES = [
    "How should I set up squat sets and reps in week one of a volume building month?",
    "How do squat sets and reps change from week to week in a volume phase?",
    "Should the Monday Wednesday Friday lifts have different squat intensities, heavy day and light day?",
    "What power clean load or percentage should I use in the volume building phase?",
    "What should I do on general days Tuesday and Thursday between lifting days?",
    "How should I warm up and build up sets before working sets in the squat?",
    "Do I need isometrics before every session if my knee only aches a little?",
]
out = Path("../data/eval/dense_week1_results.txt")
lines = []
for q in QUERIES:
    lines.append(f"\n###### {q}")
    for r in search(q, k=6, method="charsplit_matched", mode="dense"):
        lines.append(f"\n[{r['chunk_id']}] {r['title']} @{r['timestamp']} ({r['upload_date']}) score={r['score']:.3f}")
        lines.append(r["text"][:600].replace("\n", " "))
out.write_text("\n".join(lines))
print("done", out.resolve(), len(QUERIES), "queries")
