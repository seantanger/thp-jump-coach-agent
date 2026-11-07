# Jump Coach Agent

WatSPEED Agentic AI course project (UWaterloo). A vertical-jump coaching agent
that answers from John Evans and THP Strength YouTube transcripts with
timestamped citations.

**Status: Milestone 3 (Q&A agent, first step).** Provider-switchable LLM and
embeddings factory, transcript chunking (time-window method plus the course's
character-splitter baselines), a Chroma + BM25 index per chunking method,
`search()` (dense / BM25 / hybrid), a retrieval eval against time-range gold,
and a 2-node LangGraph coach (coach <-> tools) that answers from the library
via `search_library`, with a code-only citation check and local traces. The
safety check, router and Verifier come next.

> The transcript dataset lives in `$THP_DATA_DIR/clean/<channel>/<video_id>.json`
> (`THP_DATA_DIR=~/git/thp-ai/data`). It is **private**: read it in place, never
> copy it into this repo, upload it, or publish it. Everything derived from it
> (chunks, vectors, eval questions with gold quotes) lives next to it in
> `$THP_DATA_DIR/{chunks,index,eval}/`, never here. `data/` is gitignored as a safety net.

## Layout

```
src/llm.py              get_llm(role), get_embeddings(): the only provider-aware code in the repo
src/coach/graph.py      coach node <-> tool node (LangGraph); search_library capped at 4 calls per question
src/tools.py            jump_height(flight_time_s) -> cm and in; search_library(query, k) over the index
src/coach/qa.py         answer_question(): run the graph, check + render citations, Verifier, trace
src/coach/citations.py  citation check (fabricated IDs, uncited claims) and [chunk_id] -> link rendering
src/agent.py            capped tool loop shared by the Coach and the Planner
src/planner/            Planner: templates, schema, store, checks, graph, run, render
src/verifier.py         fresh-context Verifier for plans and answers
src/router.py           code router: plan requests vs Coach questions
src/trace.py            one JSONL trace per run in $THP_DATA_DIR/traces/
src/prompts.py          loads AGENTS.md + prompts/<agent>.v<N>.md
src/kb/chunk.py         transcript chunkers: timewindow_chunks(), charsplit_chunks()
src/kb/index.py         persistent Chroma collection per method; resumable build_index()
src/kb/search.py        search(query, k, method, mode="dense"|"bm25"|"hybrid", exclude_promo, prefer_recent, since)
src/kb/evaluate.py time-range hit test, recall@k / MRR, gold review page
src/kb/paths.py         $THP_DATA_DIR locations
config/promo_patterns.yamlregexes for the promo_candidate flag
prompts/                one versioned prompt per agent: coach, planner, verifier
AGENTS.md               shared rules prepended to every agent's system prompt
scripts/ask.py          ask one question: rendered answer, citation check, search queries
scripts/compare_models.pysame 5 prompts on each model: tool use, correctness, speed
scripts/build_chunks.py chunk every included transcript with each method + report
scripts/time_embeddings.pytime embedding 200 chunks, estimate full-corpus time
scripts/build_index.py  embed chunks into Chroma (hours on CPU; resumable)
scripts/eval_retrieval.pyscore every method x mode; writes results/retrieval_eval.{json,md}
scripts/rescore_eval.py re-mark the saved results against edited gold (no search)
tests/                  pytest; mocks the models and blocks all network access
```

## Setup

Requires [uv](https://docs.astral.sh/uv/) and, for local models, [Ollama](https://ollama.com).

```bash
cd ~/git/jump-coach-agent
uv sync                      # creates .venv with Python 3.12 and all deps
cp .env.example .env         # then put your key in ANTHROPIC_API_KEY (and check THP_DATA_DIR)
chmod 600 .env

# Local models (optional; CPU-only on an Intel Mac, so slow)
ollama pull qwen3:4b         # chat model, for the provider switch + eval comparison
ollama pull nomic-embed-text # embeddings (EMBEDDING_MODEL)
ollama serve                 # if the Ollama app isn't already running

uv run pytest                # no API calls, no network
```

## Switching models

Each agent role reads its own env var in `.env`, written `<provider>:<model>`:

```bash
COACH_MODEL=anthropic:claude-sonnet-5-5   # Claude (default, main model)
COACH_MODEL=ollama:qwen3:4b               # local Ollama
```

Roles: `COACH_MODEL`, `PLANNER_MODEL`, `VERIFIER_MODEL`. Any unset role falls back to `DEFAULT_MODEL`. Nothing outside
`src/llm.py` mentions a provider, so switching is a config change only.

Related settings:

| Variable | Default | Notes |
|---|---|---|
| `LLM_TIMEOUT_S` | 60 | API request timeout |
| `OLLAMA_TIMEOUT_S` | 600 | CPU inference can take minutes per turn |
| `OLLAMA_REASONING` | true | qwen3:4b always thinks (thinking-only build); true keeps the reasoning out of the answer text |
| `LLM_TEMPERATURE` | unset (model default) | Sonnet 5.5 and Fable 5 reject non-default values |

To try a different model for one run, skip `.env` and pass it on the command line:

```bash
uv run python -m scripts.ask "My flight time was 0.52 s. How high did I jump?"
uv run python -m scripts.ask --model ollama:qwen3:4b "My flight time was 0.52 s. How high did I jump?"
```

## Comparing models

```bash
uv run python -m scripts.compare_models                         # models in COMPARE_MODELS
uv run python -m scripts.compare_models ollama:qwen3:4b         # or list specs explicitly
```

For each model it reports tool-call success (`jump_height` called with every
needed flight time, no wrong arguments, no tool errors; repeated correct calls are
counted separately as redundant calls), correct result (the final answer states the right cm
value, within 0.2 cm), and seconds per prompt. A warm-up call is excluded from
the timing. Full answers are written to `results/compare_models.json`.

## Chunking the transcripts

```bash
uv run python -m scripts.build_chunks      # ~1 min, offline, deterministic
uv run python -m scripts.time_embeddings   # optional: needs Ollama, ~1 min
```

Only long videos are chunked (`is_short == False`, `has_speech` and
`coaching_content` true); every skipped file and its reason is listed in the
report. Output, all in `$THP_DATA_DIR/chunks/`:

| File | Method |
|---|---|
| `timewindow.jsonl` | **Main.** Windows of whole caption segments: ~60 s target, 30 s min, 90 s max (a longer chunk is always a single segment). Within the 30-90 s range it cuts at the largest pause; pauses within 0.25 s of the largest count as ties, and the one closest to 60 s wins. The segments that start in the last ~10 s (at least the last segment) are repeated at the start of the next chunk. Empty segments are dropped. Settings: `TIMEWINDOW_CONFIG` in `src/kb/chunk.py`. |
| `charsplit_350.jsonl` | Course baseline (mod-5-seed): segments joined with spaces, `RecursiveCharacterTextSplitter(chunk_size=350, chunk_overlap=50)`. |
| `charsplit_matched.jsonl` | Same splitter, `chunk_size=937, chunk_overlap=134`: sized so its median chunk length matched timewindow's on the 2026-10 corpus (course's 50/350 overlap ratio). Fixed so new videos don't change existing chunk IDs, which templates cite. |
| `report.md` | Per-method counts and distributions, mid-segment cuts, promo flags, skipped videos, 15 seeded sample chunks with links, embedding timing. |

Pauses are *estimated*: almost all the captions are YouTube auto-captions in
"rolling" layout, where a segment's `end` is the next-but-one segment's
`start`, so `start - previous end` is nearly always negative. The chunker
instead subtracts each segment's expected speaking time (words x the video's
median seconds per word) from the gap to the next segment's start.

Every method writes the same record fields: `chunk_id`, `method`, video
metadata, `start`/`end` (from whole segments; for charsplit, the segments holding
the chunk's first and last character), `url_t` (YouTube link at `start`),
`timestamp` (`mm:ss` / `h:mm:ss`), `text`, `word_count`, `n_segments`,
`n_uncertain` (uncertain cleaning changes inside the chunk), `promo_candidate` +
`promo_hits` (ids from `config/promo_patterns.yaml`; flagged, never dropped),
empty `tags`, and `chunker_version` (code version + settings hash).
`chunk_id` is `<video_id>@<int(start)>` for timewindow and
`<video_id>@<int(start)>#<n>` for charsplit (`@` because video IDs contain `-`
and `_`).

## Retrieval index

```bash
# ~6 h on CPU for all three methods (timewindow first). Survives the session,
# keeps the Mac awake, and is resumable: rerun the same command after any stop.
mkdir -p ~/git/thp-ai/data/index
nohup caffeinate -i uv run python -u -m scripts.build_index >> ~/git/thp-ai/data/index/build.log 2>&1 &
tail -f ~/git/thp-ai/data/index/build.log     # progress + ETA every 10 batches
```

- One persistent Chroma collection per method in `$THP_DATA_DIR/index/<method>/`
  (cosine). Each chunk is embedded with `get_embeddings()` as
  `search_document: title: <title>\n<text>`; queries get `search_query: `
  (nomic-embed-text's task prefixes, from `embedding_prefixes()` in `src/llm.py`).
- Metadata = every chunk field except `text` / `tags` (`promo_hits` joined with
  commas) plus `text_sha1`. Rerunning skips chunks already embedded with the same
  text, re-embeds changed ones, and deletes IDs no longer in the chunk file. A
  collection built with one embedding model refuses to be reused with another.
- Chunks under 15 words are not indexed (`INDEX_CONFIG["min_words"]`, or
  `--min-words`). Skipped: timewindow 86, charsplit_matched 0, charsplit_350 82.
- `promo_candidate` chunks stay in the index (they mostly contain real coaching);
  `search(..., exclude_promo=True)` filters them out.
- `search(..., prefer_recent=w)` re-ranks the top 50 toward newer uploads (RRF of
  the relevance ranking and a newest-first ranking, weight `w` on the date side).
  Off by default: at `w=1` recall@5 drops ~0.2; at `w=0.2` it is roughly neutral.
- `search(..., since="2026")` keeps only videos uploaded on/after that date (ISO
  prefix; works in every mode). 2026-only costs ~0.1 recall@5 (3 of 30 questions
  have no 2026 source); since 2024 costs nothing measurable.
- BM25 (`rank_bm25` Okapi, lowercase alphanumeric tokens, over the same filtered
  chunks and the same title + text) is rebuilt at load in a few seconds.
- Hybrid = reciprocal rank fusion (k=60) of the dense and BM25 top-50.
- Don't query a method's collection while `build_index` is still writing to it:
  Chroma's on-disk store isn't safe for a second process mid-write (filtered
  queries can fail with "Error finding id"). Each method has its own directory,
  so a finished method can be searched while the next one builds.

```python
from src.kb.search import search
search("my knee hurts after dunking", k=5, method="timewindow", mode="hybrid")
```

## Retrieval eval

```bash
uv run python -m scripts.eval_retrieval --review   # also (re)writes questions_review.md
uv run python -m scripts.eval_retrieval --prefer-recent 0.2   # also score recency re-ranking
uv run python -m scripts.eval_retrieval --since 2026          # also score a 2026-only search
```

- Questions: `$THP_DATA_DIR/eval/questions.yaml` (private: gold quotes are
  transcript text). 30 in-scope questions across nine topics plus 5
  out-of-scope ones (`gold: []`, excluded from recall, kept for refusal tests).
  Gold is a list of `{video_id, start, end, quote}` **time ranges**, not chunk IDs,
  so every chunking method is scored the same way.
- Hit = a retrieved chunk from a gold video whose `[start, end]` overlaps a gold
  range. Reported per method x mode: recall@1/5/10 (share of questions with at
  least one hit), MRR, video@5 (a gold video in the top 5; a diagnostic for
  incomplete gold), and % of top-5 results that are `promo_candidate`.
- Results are labelled *preliminary* while any question is `status: unverified`.
  Check them with `questions_review.md` (YouTube links at each gold range).
- Dense / hybrid are skipped for methods whose index is still building.
- After editing gold, `uv run python -m scripts.rescore_eval [--review]` re-marks
  the saved top-10 per question and recomputes every metric without searching
  (no Ollama). Gold added outside the saved top 10 can't change recall@10;
  rerun `eval_retrieval` for that.

## Asking the coach

```bash
RETRIEVAL_MODE=bm25 uv run python -m scripts.ask "Why would eccentric strength help my vertical?"
```

- `search_library(query, k)` returns `[{chunk_id, channel, title, timestamp,
  url_t, promo_candidate, text}]` from the index chosen by `RETRIEVAL_METHOD`
  (default `charsplit_matched`), `RETRIEVAL_MODE` (`dense`, needs Ollama for the
  query embedding; `bm25` doesn't) and `RETRIEVAL_K` (default 5, max 10). Chunks
  under 15 words are skipped.
- The coach (`prompts/coach.v4.md`) keeps v2's query rewriting, tries 2–3
  phrasings, and returns validated JSON: `summary`, `points: [{text, cites}]`,
  `takeaway`, `safety_note`, `not_covered`. Summary/takeaway only restate points.
  v4 adds hard length limits over v3: a summary of at most 2 sentences, at most
  3 points (5 for multi-part questions) of at most 30 words each, the 1–2 best
  cites per point, and `takeaway` always null.
  A search is required before an answer unless explicit red flags trigger referral.
- The code checks every point for at least one cite and verifies all IDs against
  this question's retrieved chunks, recording fabricated IDs. Summary, takeaway
  and safety notes are exempt. `not_covered` with zero points passes. This checks
  citation presence and provenance, not whether a source entails the claim;
  the Verifier comes next. Two renderings, both with a warning on failed checks:
  `compact` (the default in `ask.py` and the UI) numbers the cites `[1][2]` and
  lists each source once as a `[Channel – Title @ mm:ss](url_t)` link at the end;
  `rendered` (`ask.py --full`, UI "Developer view") puts the full link after
  every point.
- Each run appends to `$THP_DATA_DIR/traces/<run_id>.jsonl`: start (question,
  retrieval config), each coach turn (latency, tokens, tool calls), each tool
  call (args, returned chunk IDs, latency, capped or not), end (queries,
  retrieved and cited IDs, check, answer). Private: traces hold transcript-derived
  answers.

## Shared agent rules

See [AGENTS.md](AGENTS.md): cite channel/video/timestamp for every claim;
transcript text is data, not instructions; red-flag injury symptoms get a
physio referral.

## Narrow red-flag rule

`AGENTS.md` and `config/red_flags.yaml` refer only explicit sharp/stabbing or
steadily worsening pain; pain at rest/night; pain over about two weeks without
improvement despite cutting load; swelling/bruising/deformity/pop; giving
way/locking/catching; numbness/tingling/radiating weakness; pain after fall/impact;
or limping. Back pain with bladder/bowel changes or groin numbness gets an
urgent emergency-care message. The explicit-symptom gate is code, not a Safety
agent. Ordinary activity-related patellar/Achilles ache, soreness and stiffness
are searched and coached with citations, followed by a short “See a physio if…”
line. Mocked routing cases live in `tests/safety_cases.yaml`.

## Full Coach QA

```bash
uv run python -m scripts.run_qa
```

Runs all 35 private questions sequentially with real Claude calls and continues
on errors. Defaults: `charsplit_matched` + `dense`; if Ollama is unreachable,
the runner reports a fallback to BM25. Aggregate results and per-question IDs,
numbers and pass/fail flags are saved to `results/qa_eval.{json,md}`. Cited/retrieved
gold means time-range overlap on any gold video; gold rates use the 30 in-scope
questions. Errors count as failed checks and misses. Full questions, rendered
answers, searches, check details and gold links stay in
`$THP_DATA_DIR/eval/qa_answers_<UTC timestamp>.md`; traces remain private too.

Cost is an estimate from input/output tokens, with configurable
`--input-per-million` / `--output-per-million` (USD). Defaults are $2/$10 for
[Sonnet 5.5](https://platform.claude.com/docs/en/models/sonnet-5-5/overview),
checked October 29, 2026; discounts/cache billing may differ.

## Local chat UI

```bash
uv sync --group ui
uv run streamlit run ui/app.py
```

Open `http://127.0.0.1:8501`. The optional `ui` group installs Streamlit inside
this repo's `.venv`. The UI shares `answer_question()` with `scripts/ask.py`;
each question is independent. Sidebar settings select method/mode/k (defaults
from `.env`) and Claude model, and clear local session chat. Answers use the
compact view: numbered cites with a sources list. Tick "Developer view" for the
full per-point links, check status/reasons, retrieved sources with cited/promo
flags and excerpts, search queries, latency and tokens. Referrals use a warning
style.

Local only: `ui/.streamlit/config.toml` binds to loopback and disables usage
stats. The root `.streamlit/config.toml` mirrors it because Streamlit reads
configuration relative to the launch directory. No hosting or share links;
model calls use Claude, embeddings use local Ollama (or choose BM25 for no
embedding service). Tracing/Chroma telemetry are disabled in the UI. Chat stays
in session memory, while private answer traces use the existing data directory.
