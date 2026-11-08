# Retrieval eval

**gold partly verified (8/30); rescored from the saved top-10 of the 2026-11-08 13:18 search** (2026-11-08 13:23). 30 in-scope questions (5 out-of-scope excluded). A hit = a top-k chunk from a gold video overlapping a gold time range. recall@k = share of questions with at least one hit in the top k. video@5 = a gold video is in the top 5 (diagnostic: separates wrong-place-in-right-video from wrong-video misses).

| method | mode | recall@1 | recall@5 | recall@10 | MRR | video@5 | promo in top-5 | pre-2024 in top-5 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `timewindow` | dense | 0.47 | 0.73 | 0.80 | 0.58 | 0.83 | 8.0% | 4.7% |
| `timewindow` | dense since 2026 | 0.43 | 0.57 | 0.67 | 0.51 | 0.67 | 12.0% | 0.0% |
| `timewindow` | bm25 | 0.10 | 0.50 | 0.63 | 0.24 | 0.63 | 4.7% | 18.7% |
| `timewindow` | bm25 since 2026 | 0.13 | 0.43 | 0.47 | 0.23 | 0.63 | 10.7% | 0.0% |
| `timewindow` | hybrid | 0.37 | 0.63 | 0.77 | 0.48 | 0.77 | 7.3% | 6.0% |
| `timewindow` | hybrid since 2026 | 0.37 | 0.50 | 0.57 | 0.43 | 0.67 | 10.0% | 0.0% |
| `charsplit_matched` | dense | 0.47 | 0.87 | 0.87 | 0.61 | 0.90 | 8.0% | 2.7% |
| `charsplit_matched` | dense since 2026 | 0.37 | 0.73 | 0.77 | 0.51 | 0.80 | 10.7% | 0.0% |
| `charsplit_matched` | bm25 | 0.17 | 0.47 | 0.53 | 0.29 | 0.63 | 2.7% | 22.0% |
| `charsplit_matched` | bm25 since 2026 | 0.17 | 0.37 | 0.43 | 0.25 | 0.53 | 2.0% | 0.0% |
| `charsplit_matched` | hybrid | 0.33 | 0.67 | 0.87 | 0.48 | 0.77 | 6.0% | 6.7% |
| `charsplit_matched` | hybrid since 2026 | 0.30 | 0.53 | 0.73 | 0.41 | 0.70 | 5.3% | 0.0% |
| `charsplit_350` | dense | 0.47 | 0.70 | 0.90 | 0.58 | 0.77 | 2.0% | 2.0% |
| `charsplit_350` | dense since 2026 | 0.47 | 0.60 | 0.70 | 0.51 | 0.67 | 4.0% | 0.0% |
| `charsplit_350` | bm25 | 0.13 | 0.53 | 0.53 | 0.28 | 0.60 | 0.7% | 20.0% |
| `charsplit_350` | bm25 since 2026 | 0.17 | 0.33 | 0.53 | 0.24 | 0.53 | 1.3% | 0.0% |
| `charsplit_350` | hybrid | 0.37 | 0.77 | 0.83 | 0.52 | 0.80 | 2.7% | 7.3% |
| `charsplit_350` | hybrid since 2026 | 0.23 | 0.60 | 0.73 | 0.39 | 0.67 | 4.7% | 0.0% |

## Misses for the best config (`charsplit_matched` / dense, by recall@5 then MRR)

4 questions with no hit in the top 5.

| question | topic | first hit rank | top-3 chunks |
|---|---|---:|---|
| q06: Is it better to spend a few months only on strength, then switch to power, then plyos, or train everything at the same time? | programming | - | `L3VH8cJ7XP4@315#0` (05:15), `erOaPQ6HF8s@1070#0` (17:50), `sWadXNLwO9Q@1311#0` (21:51) |
| q11: My reactive strength score keeps going up but my vertical doesn't. Is that number a good way to track progress? | plyometrics | - | `mHeNxLZN0BY@55#0` (00:55), `pGW46ON4Wgc@0#0` (00:00), `pGW46ON4Wgc@144#0` (02:24) |
| q16: Why would getting stronger in the lowering phase of a lift make me jump higher? | strength | - | `NvhrrOBL7jk@869#0` (14:29), `EVaOYvvxDQU@0#0` (00:00), `nyARzQ1FOsc@945#0` (15:45) |
| q27: Is it bad to hold long stretches right before I jump? | mobility | - | `igRw-WBV4UE@1165#0` (19:25), `HPHG7qfvTps@418#0` (06:58), `jtlbfgtYgJk@1368#0` (22:48) |
