# Transcript dataset: pilot report

**Status:** pilot complete (5 videos, both phases). Waiting for approval before the full run.
**Date:** 2026-10-17 · **Brief:** project doc `claude/transcript-dataset-brief.md` (v2, multi-channel)

## Channels found (full listing done, transcripts only for pilot)

| Channel | Regular videos | Shorts | Streams | Hours (regular videos only*) |
|---|---|---|---|---|
| John Evans (@JohnEvans) | 428 | 128 | 0 | 169.6 |
| THP Strength (@thpstrength1) | 764 | 1,527 | 0 | 168.8 |
| **Total** | **1,192** | **1,655** | 0 | **338.4** |

*The flat channel listing doesn't return Shorts durations; they'll be filled in during collection. Shorts are ≤3 min, so they add at most ~80 h.

All 2,847 videos are in `data/videos_index.csv` (5 `collected`, 2,842 `pending`). Per-channel listings are in `data/listings/`.

## Pilot results

| Video | Channel | Type | Length | Captions | Clean changes | `[?]` |
|---|---|---|---|---|---|---|
| [How To Get Rid Of Knee Pain (Full Blueprint)](https://www.youtube.com/watch?v=9X_j-oF2ZDg) | JE | long, knee | 19:29 | auto | 39 | 3 |
| [How Strong Do You Have To Be For A 40 Inch Vertical](https://www.youtube.com/watch?v=LPz1LvtCklY) | JE | long, Q&A | 27:02 | auto | 59 | 6 |
| [How strong do you have to be for a 50 inch vertical?](https://www.youtube.com/shorts/SeU7UBRQDgs) | JE | Short | 0:17 | auto | 3 | 0 |
| [Modified Depth Jumps That Actually Load Your Patella](https://www.youtube.com/watch?v=LlFFD4BhhIw) | THP | regular, knee/plyo | 5:21 | auto | 3 | 1 |
| [We Prioritize the Health of Our Athletes… #shorts](https://www.youtube.com/shorts/ovTkqma68Zg) | THP | Short, testimonial | 1:08 | auto | 3 | 0 |

- **Found / collected / failed:** 5 / 5 / 0. `logs/failed.txt` is empty.
- **Manual vs auto captions:** 0 manual, 5 auto. The knee video has only auto English (plus auto-translations), so expect nearly the whole corpus to be auto.
- **Pilot content:** 53.3 minutes.
- Clean files keep the raw `text`, `start` and `end` for every segment. A script check confirmed they match the raw files exactly.

## Findings that affect the full run

1. **Music-only Shorts.** The JE Short `SeU7UBRQDgs` has no speech; its captions are song lyrics and `[music]` tags. The clean file flags it `has_speech: false` so later phases can skip it. Expect many more like this among the 1,655 Shorts.
2. **Many Shorts are probably clips or testimonials,** not new coaching (e.g. `ovTkqma68Zg` is an athlete testimonial). Both raise a scope question (see "Decision needed").
3. **Sales pitches.** Most long videos end with a pitch for coaching ("click the link below…"). These should be tagged `promo` in Phase 4 so the agent never cites them as advice.
4. **The two channels overlap.** THP videos are narrated by John Evans ("my story about getting better at two-foot jumping"). Expect duplicate content, and for conflict handling you can treat them as one source.
5. **Overlapping timestamps.** Auto captions sometimes have a segment start before the previous one ends. This is normal for YouTube auto captions and was left unchanged, as required.
6. **Rate limits.** Collection runs on your Mac (about 4–6 s pause per video plus metadata). The full run is about 2,847 videos ≈ 4–5 hours, done in batches using `--limit`.

## How cleaning works (rerunnable)

- `data/corrections.yaml` holds global glossary rules applied to every video: misheard terms (e.g. "tenonopathy" → "tendinopathy", "tenant" → "tendon"), filler removal (um/uh), stutter repeats ("and and" → "and", keeping emphatic ones like "really, really" and "you you"), and removal of non-speech tags.
- `data/clean_overrides/<video_id>.yaml` holds context-dependent fixes for single segments. I reviewed each pilot transcript in full by hand to write these.
- Each segment's `changes` lists every edit with its rule. Each file's `cleaning` block records the version and counts.
- **Bug found and fixed during the pilot:** the repeat rule turned "I promise you you will" into "you will". I added "you" to the protected list and reran the cleaning, which overwrote all 5 clean files. Raw files were never touched.

## `[?]` fixes to review (10)

| Video @ time | Original | Best guess | Why unsure |
|---|---|---|---|
| 9X_j-oF2ZDg @ 4:59 | ramp up force indiscreetly | indiscreetly [?] | kept as said; maybe "indiscriminately" or "in discrete steps" |
| 9X_j-oF2ZDg @ 9:46 | reactive on degenerative tenonopathy | reactive or degenerative [?] | "on"/"or" unclear |
| 9X_j-oF2ZDg @ 19:02 | make sure you don't drain | don't detrain [?] | context: adding upper-body work in early phases |
| LPz1LvtCklY @ 6:49 | now he's already yelling | squatting [?] | context is lift numbers (335 for 3) |
| LPz1LvtCklY @ 6:52 | he already yelled like 335 | squatted [?] | same |
| LPz1LvtCklY @ 20:05 | For studying Travis Slay | For studying Travis [?] | unclear phrase/name |
| LPz1LvtCklY @ 24:17 | Boo Schexnayder, set up one of the greatest | Boo Schexnayder, who's [?] | mishearing of "who's" |
| LPz1LvtCklY @ 25:11 | they're sparring year round | sprinting [?] | point is stiff contacts all year |
| LPz1LvtCklY @ 25:53 | Tobin uh Nudson | Tobin Knudson [?] | surname spelling unverified |
| LlFFD4BhhIw @ 0:27 | jump? know that depth jumps… | Knowing [?] | first word of the sentence cut off |

To change a fix, edit the matching line in `data/clean_overrides/<id>.yaml` and rerun `uv run scripts/clean.py --ids <id>`.

## Terms added to the glossary (38, in `data/glossary.yaml` → `added`)

- **Tendon terms:** tendinopathy, tendonitis, tendon, tenocytes, nociceptive, musculotendinous unit, tendon disrepair, reactive / degenerative tendinopathy, PFP (patellofemoral pain), triceps surae.
- **Training terms:** heavy slow resistance (HSR), depth drop, kettlebell, long conjugate sequence system, stretch-shortening cycle, shock loading/training, RFD, MVC, reverse Nordic, clean pull, Prilepin's chart.
- **People and sources:** Verkhoshansky, Ebonie Rio, Jill Cook, Boo Schexnayder, Mike Young, thpstrength.com.
- **John Evans athletes and people:** Tony Crosby, Donovan Hawkins, Dylan McCarthy, Dominic (Dom) Gonzalez, Nate/Nathan George, Satyarth, Fabian Delryd, Stefan Holm, Tobin Knudson [?].
- **THP:** Devonte Scott.

## Topics that came up often (for Phase 4 tagging)

- **Knee health / tendon rehab:** the tendinopathy continuum, isometrics (70% MVC, 45 s, every 6 h), HSR (4×6–8, 4-count tempo), pain-scale loading (2–5/10), the 24–48 h response, return-to-jump progression.
- **Strength:** strength standards (×bodyweight squat / power clean), Prilepin and %1RM programming, beginner → intermediate → advanced.
- **Plyos:** depth jumps vs depth drops, shock loading volume, modified deep-knee depth jumps, RSI ranges.
- **Technique / jumper type:** one-foot vs two-foot jumpers, speed jumpers, stiff vs compliant, patella vs Achilles loading.
- **Programming:** long conjugate sequence system, emphasis cycles (concentric → isometric → eccentric → RFD → SSC), unload weeks.
- **Athlete level:** beginner / intermediate / advanced / elite pro.
- **Athlete stories and testimonials.**
- **Promo / sales pitch** (to exclude from retrieval).

## Scripts

Python environment is managed with uv (`pyproject.toml`, `uv.lock`, Python 3.12). On a new machine run `uv sync` once, then use `uv run scripts/<name>.py`.


| Script | What it does |
|---|---|
| `scripts/list_videos.py [--channel H]` | lists /videos, /shorts and /streams for each channel in `config/channels.yaml` |
| `scripts/collect.py --ids …` / `[--channel H] [--limit N]` | incremental transcript download, then rebuilds the index |
| `scripts/clean.py [--ids …] [--channel H]` | Phase 2 cleaning |

## Decision needed before the full run

1. **Shorts:** collect all 1,655, or only regular videos plus Shorts that have speech? (Recommendation: collect all, since it's cheap, and filter with `has_speech` and dedupe later.)
2. **Context-dependent cleaning at scale:** global rules cover the recurring errors. Hand-reviewing 2,800 transcripts isn't practical, so I propose a model-assisted pass that writes override files with `[?]` marks, plus a spot-check sample for you.

## Shorts sample (2026-10-17, partial)

Goal: find out whether Shorts are just clips of long videos. Sampled the first 30 Shorts listed on each channel.

**What happened:** YouTube rate-limited caption downloads (HTTP 429) after about 70 requests in 10 minutes. It was still blocking 75 minutes later. Only John Evans Shorts were reached: 13 collected and 10 with no captions on YouTube. No THP Shorts were collected.

**Collection changes made because of this** (`scripts/collect.py`):
- Captions now come from yt-dlp (srv1 format), not youtube-transcript-api. The old library reported rate-limit blocks as "transcripts disabled", which wrongly filled `failed.txt`. That file was reset; the bad entries are kept in `logs/failed_attempts_2026-10-17_rate-limited.txt`.
- A video is logged as failed only when YouTube's metadata shows no English captions.
- On a 429 the run stops cleanly. Rerunning skips finished videos.
- Default pause is now 20 s between videos.

**John Evans Shorts (23 reached):**

| Kind | Count | Examples |
|---|---|---|
| Original scripted voiceover (stand-alone coaching, often cites a study) | 7 | "Caffeine makes you faster", "Olympic lifts help you jump higher", "Quit wasting time deep squatting" |
| Training footage with coaching commentary | 3 | "Russian training secrets revealed", "500lb 90degree squat" |
| Music / song lyrics / court chatter, no coaching | 5 | "Best dunk ever not ai", "Top 10 Plyometrics" (lyrics only) |
| No captions at all (music-only highlight clips) | 10 | "Tony Crosby is a FREAK athlete", "Isaiah Rivera crazy block in game" |

**Conclusions:**
- About 40% of the John Evans Shorts reached have stand-alone coaching content. Skipping Shorts would lose it.
- About 60% have no coaching value. They're cheap to detect: either no captions, or the new `coaching_content` flag (below).
- The exact clip rate is still unmeasured. The sampled Shorts span Oct 2025 to Oct 2026, so checking them needs most long videos from that period: roughly 900, since YouTube's listing dates are coarse. That is effectively the full run, so clip detection (`scripts/shorts_overlap.py`) will run as part of it.

**New content flag** (`scripts/clean.py` v1.1): every clean file now has `coaching_content` and `coaching_vocab_ratio`. These are based on the share of coaching words (`config/coaching_vocab.txt`). Lyrics and chatter score 0–0.01; coaching scores 0.04–0.2. The cutoff is 0.02, and on the 18 files so far it separated all of them correctly. It replaces the old music check, which couldn't catch lyrics.

## Full run: regular videos (completed 2026-10-25)

Collection ran 2026-10-19 → 2026-10-25 on Sean's Mac at a slow pace (35–45 s between videos), in batches whenever the Mac was awake. Shorts are **not** collected yet (only the 14 from the sample) — that phase waits for Sean's go-ahead.

### Counts

| | John Evans | THP Strength | Total |
|---|---|---|---|
| Regular videos listed (Oct 17) | 428 | 764 | 1,192 |
| Collected | 406 | 760 | **1,166** |
| Failed | 22 | 4 | 26 |
| Hours of content (collected) | 166.5 | 167.9 | **334.4** |
| Caption type | 406 auto | 760 auto | **0 manual / 1,166 auto** |

Corpus size: ~565k caption segments, ~3.7M words. Upload years — JE: 2019–2026 (most in 2024); THP: 2024–2026 (most in 2026).

### Failures (26, all in `logs/failed.txt`)

- **25 — no English captions on YouTube.** Mostly old JE dunk-session / highlight logs ("First Dunk On 10 Feet", "Training", "Max out") and a few THP music/b-roll clips. Would need speech-to-text (e.g. Whisper) if any matter.
- **1 — age-restricted** (`nRzwzlQvM7c`, "First cock back dunk at 30 y/o"): needs a signed-in session; not worth it.
- `failed.txt` also has one stale transient error for `vlWONzK9ofs` (network timeout) — it was retried and collected fine.

### Collection incidents

- YouTube rate-limited caption downloads (HTTP 429) twice: ~24 h (Oct 17–18) and ~4.5 days (Oct 19 → Oct 23). The script stops cleanly on 429 and resumes where it left off; nothing was lost or mislogged after the first fix (see pilot section).
- Mac sleep/offline windows paused the run several times; each restart cleaned + indexed before collecting.
- The Cowork shell timeout dropped from ~3 min to ~90 s on Oct 24, so batches went from 3 to 2 videos per call.

### Cleaning (clean.py v1.2)

- Every segment keeps `text` + `clean_text` + `changes`; timestamps untouched.
- `coaching_content: false` (long videos, cutoff 0.005): only 2 — a car video ("Senna LM Start Up Mclaren") and "Smoove taught me how to windmill" (music). Both should be excluded from retrieval.
- **New corpus-wide misheard terms added to `data/corrections.yaml` after a full-corpus scan:**
  - "Ecentric" → eccentric (304)
  - "pio"/"pios" → plyo/plyos (~340) — e.g. "Stop just doing pio"
  - "tenant opathy" → tendinopathy (8)
  - "Verkoshansky" → Verkhoshansky (7)
- Most frequent fixes overall: eccentric 304, plyo(s) 342, tendon (from "tenant"/"tenon") ~310, bottleneck 59, kettlebell 35, tendinopathy ~58, Ebonie Rio 14, thpstrength.com 13.
- Only 10 `[?]` fixes exist (all from the pilot overrides) — the context-dependent review for the other 1,160 videos hasn't been done; see "Next".

### Topics by title (1,166 regular videos; a video can hit several)

| Topic | Videos |
|---|---|
| Dunking / athlete stories (Isaiah, Dom, Donovan, Austin…) | 219 |
| Strength / lifting (squat, clean, eccentrics, isometrics) | 211 |
| Knee / tendon pain & rehab | 124 |
| Jump technique (penultimate, approach, one- vs two-foot) | 122 |
| Programming / periodization (conjugate, deload, volume) | 106 |
| Plyometrics / depth jumps / RSI | 69 |
| Sprinting / speed | 52 |
| Nutrition / body comp / recovery | 37 |
| Volleyball | 24 |
| Mindset / habits | 12 |

### Next (needs Sean's go-ahead)

1. **Shorts** (~1,640 pending): collect, flag music/lyrics (`coaching_content`), then run `scripts/shorts_overlap.py` now that all long videos exist.
2. **Context-dependent cleaning** for the remaining videos (model-assisted override files with `[?]`, plus a spot-check sample).
3. Phase 3+ (chunking, tagging, retrieval).

Scripts: `uv run scripts/stats.py` reproduces the numbers above.

### 2026-10-26: cleaning rules from the chunk review (clean.py v1.2 rerun)

Seven global rules added to `data/corrections.yaml` and all 1,180 files re-cleaned (`.venv` created with `uv sync` for this). **648 fixes in 647 segments / 535 files**; every changed segment reverts exactly to its previous text when those fixes are undone, the other 564,486 segments are byte-identical, and no `has_speech` / `coaching_content` flag changed (83 `coaching_vocab_ratio` values dropped by ~0.001 because "thp strength.com" became one token).

- **Site name → thpstrength.com: 638.** About 120 caption spellings ("teachbstrength", "thbstrength", "tb strength", "tpst strength", "teach me strength", "strength dot com", "thpstrike", "tsprren.com"…); all checked in context as the THP coaching plug. Left alone: ~100 cross-segment splits ("go to THP" | "Strength.com"; rules match within one segment) and short ambiguous forms (tp.com, tm.com, teach.com, tank.com).
- **"centric" → eccentric: 10** ("e centric", "e-centric", "East Centrics", "true tree Centric"). The other ~40 standalone "centric"s are left as-is: most are probably eccentric ("why centric", "heavy Centrics") but concentric can't be ruled out, and "athlete-centric" / "podcast-centric" are real words.
- Chunks in `data/chunks/` were rebuilt (files overwritten); chunk IDs moved only where text length changed (timewindow: 2 of 22,687).

### 2026-10-26 (later): second cleaning pass (clean.py v1.2 rerun)

Three changes to `data/corrections.yaml`, then all 1,180 files re-cleaned. **85 changes, all explained** (every changed segment reverts exactly to its previous text when the change is undone); no `has_speech` / `coaching_content` flag changed; one `coaching_vocab_ratio` rose slightly.

- **Correction to the note above:** 73 of the 638 "site name" fixes were already-correct `THPstrength.com` / `THPStrength.com` that the joined-variant rule rewrote to `Thpstrength.com` (case only). The rule now skips correct spellings, so those 73 are back to their original text. Real site fixes: 565.
- **decentric → eccentric: 7.** The "d" is the end of the previous word ("fast decentric loading", "failed decentric", "concentric and decentric RFDs"), so it is not "the eccentric".
- **isocentric(s) → eccentric(s): 5.** Context shows eccentrics, not isometrics ("overcoming isometrics and supramaximal isocentrics", "overloaded isocentrics through weight releasers").
- "concentric" needed no rules: it is captioned correctly (528 concentric, 173 concentrically). `eccentric`/`concentric` are in `config/coaching_vocab.txt`, but that list only scores coaching content; corrections come from the misheard forms in `corrections.yaml`/`glossary.yaml`.
- Chunks rebuilt (overwritten): timewindow IDs unchanged (81 chunks' text changed); charsplit_350 81 IDs moved, charsplit_matched 8. Indexes in `data/index/` updated in place: changed chunks re-embedded, moved IDs removed.
