# What's left — as of 2026-11-05

Where things stand, and everything still to do on the Planner (M4) and around it, in a sensible order.

## Where things stand

- **Branch `m4-planner`**: plan 1 (stages 1–4) Tasks 1–9 done and committed, plus the audit fixes
  below; **203 tests pass**. The last 13 commits are not pushed yet (`origin/m4-planner` is behind).
- **Nothing is merged.** `main` is still at Phase 3 (`7c56592`); `m2-retrieval`, `m3-qa` and
  `m4-planner` are stacked on top of each other.
- **Built:** templates schema + loader, profile / program / proposal formats, versioned program store
  (never overwrites), 8 code checks, Planner graph (caps, ≤ 2 retries, approve / reject / revise
  pause), `plan` CLI, UI Plan tab, Verifier for plans and Coach answers, shorter Coach answers (v4 +
  compact view), physio line only for pain questions, Coach moved to `src/coach/`.
- **Drafted, waiting for your review:** the two templates in `~/git/thp-ai/data/templates/`.

Key files: spec `docs/superpowers/specs/2026-10-30-planner-design.md`, plan
`docs/superpowers/plans/2026-10-30-planner-stages-1-4.md`, progress ledger with every decision I made
`.superpowers/sdd/2026-10-30-planner-stages-1-4/progress.md` (git-ignored, local only).

## Fixed on 2026-11-05 (repo audit)

A whole-repo audit found 14 problems; all are fixed, in three commits:

- **`d206463` Safety**
  - Red-flag messages now reach the referral even when they contain plan words ("pop in my knee
    this week", back pain + bladder changes with a game date). Before, the router sent them to the Plan tab.
  - The tendon gate check reads the allowed jumps from the reviewed template's stage, not from the
    list the Planner writes itself; an unknown tendon template or stage now fails instead of
    skipping the check.
- **`fea2a2d` Planner review step**
  - Retries and revisions keep what was read earlier in the run (they used to fail provenance on
    every citation unless the model re-read the template).
  - `decision: "decline"` ends as **declined** and shows "Nothing changed: <reason>" instead of failing
    three times.
  - A wrong `template_id` is retried as a schema error instead of crashing the run.
  - Approved `profile_changes` are now written to `profile.json` (the spec said so; nothing did it).
  - The Planner, its Verifier and plan source links always read `TEMPLATE_METHOD`
    (`charsplit_matched`): chunk IDs are only unique within one chunking method. The UI sidebar's
    method now only affects Chat.
- **`ee28025` Cleanup** (−161 lines net)
  - The Coach keeps its answer with a "not verified" warning when the Verifier's reply can't be read
    (it used to crash).
  - Deleted the old free-text citation checker, the stub safety / router prompts and their model
    roles, and duplicate helpers (`link`, `now`, `WEEKDAYS`, the second streamlit dependency).

Left over from the fixes:

- [ ] Delete `SAFETY_MODEL` / `ROUTER_MODEL` from your `.env` (unused now, harmless).
- [ ] Optional: show the Coach's "not verified" warning in the UI developer view (it's only in the
      result and the trace today; ~2 lines).

---

## 1. Review the templates (only you can do this)

Read `~/git/thp-ai/data/templates/REVIEW.md` (≈ 20–30 min). Check a value against its source with
`uv run python -m scripts.template_sources <video_id> --grep "<words>"`.

Decisions waiting on you:

- [ ] **Training days:** month 1 says "train about 3 days a week" but also lift Mon/Wed/Fri + general
      Tue/Thu. Read as 3 lift days plus general days on top — right?
- [ ] **Months 4–6 length:** the video says "month four/five/six" without weeks. Set 4 weeks each?
- [ ] **Unload weeks:** volume × 0.4 (≈ 60% drop, *28 Rules*), not the proposal's × 0.7. OK?
- [ ] **Event < 6 months away:** transcripts don't say which months to drop, so the Planner shortens
      only down to 12 loading weeks + taper and says so. OK?
- [ ] **Reactive flare-up stage** added before the knee video's four phases. Keep?
- [ ] Anything else in REVIEW.md that looks wrong.
- [ ] When happy: set `review.reviewed_by_user: true` in both YAML files (or tell Claude to).

## 2. Try things out (Task 10, first real runs)

Cost estimate: one `plan new` ≈ $0.25 (up to ≈ $0.75 with retries); Verifier planted-fault check
≈ $0.10. Use BM25 (no Ollama).

- [ ] Make your profile: `uv run python -m scripts.plan profile` (or the UI Plan tab form).
      Lifts in lb, verticals in in, available days, equipment, event date if any.
- [ ] First plan: `RETRIEVAL_MODE=bm25 uv run python -m scripts.plan new` → approve / reject / revise.
- [ ] Look at it: `uv run python -m scripts.plan show` and `... show --full` (developer view).
- [ ] Roll forward: `RETRIEVAL_MODE=bm25 uv run python -m scripts.plan next`.
- [ ] Try the UI: `uv run streamlit run ui/app.py` → Plan tab; tick **Developer view** to see checks,
      sources and the Verifier.
- [ ] Ask the Coach a few questions (`scripts.ask`); answers now include a Verifier call
      (`--no-verify` skips it). Check they're short in the normal view.
- [ ] If the Planner declines (e.g. a missing fact), you'll see "Nothing changed: <reason>" — fix the
      profile and run it again.
- [ ] Open the trace of your first plan (`~/git/thp-ai/data/traces/plan-<id>.jsonl`) — useful for §3.
- [ ] Claude runs `scripts/verifier_faults.py` (to be written in Task 10): does the Verifier catch a rehab
      rule in a healthy cycle and a misleading summary? If not, tune `prompts/verifier.v2.md`.
- [ ] Claude updates the README Planner section and commits Task 10.

## 3. Understand the code (before merging)

About 1,500 lines for the Planner. Reading `graph.py` next to your first plan's trace covers most of it.

| # | File | What to get from it |
|---|---|---|
| 1 | `src/planner/schema.py` | What a profile, a plan and a proposal look like |
| 2 | `src/planner/templates.py` | How templates load; why everything must be cited |
| 3 | `src/planner/graph.py` | **The core:** context → Planner → checks → approval → save |
| 4 | `src/planner/checks.py` | The 8 checks, one function each |
| 5 | `src/verifier.py` + `prompts/verifier.v2.md` | The second opinion and how it feeds retries |
| 6 | `src/planner/merge.py`, `store.py`, `run.py` | Versions, never overwriting, pause / resume |
| 7 | `src/agent.py`, `src/coach/` | The shared tool loop; how the Coach now uses the Verifier |
| 8 | `src/planner/render.py`, `scripts/plan.py`, `ui/app.py` | Display details (optional) |

- [ ] Optional: ask Claude for a guided walkthrough page of `graph.py` + your trace (handy for the
      progress update).

## 4. Testing still to do

- [ ] Manual checks: `plan show` with no plan; `plan new` with no profile (should say make a profile);
      revise loop; approving in two places at once (second should say the plan changed); chat in the UI
      with "make me a plan" (should point to the Plan tab); chat with "I felt a pop in my knee this week"
      (should give the physio referral, not the Plan tab).
- [ ] **Re-run the Coach QA eval** — `results/qa_eval.md` is from coach v3 (10 physio lines, longer
      answers). Now v4 + physio fix + Verifier. ≈ $1.30 + Verifier calls; dense mode needs Ollama,
      so BM25 if the machine is busy.
- [ ] **Independent review of the whole branch** by a fresh reviewer (the plan's final step), after
      your read-through and before merging.

## 5. Before merging

- [ ] Template review done (§1), Task 10 done (§2), code read (§3), final review fixes applied (§4).
- [ ] Decide merge order into `main`: `m2-retrieval` → `m3-qa` → `m4-planner` (they're stacked).
- [ ] Push the branch.
- [ ] Tick the finished boxes in the Build plan / write Progress report 2 in the project doc.

## 6. Plan 2 (stages 5–8) — to be written after the template review

Coordination first, then the remaining input types. Today the Coach and Planner never talk to each
other; they share only the tool loop, the rules and the Verifier.

- [ ] **Chat plan requests go to the Planner.** When `route()` says "program", call
      `run.start(..., request=message)` and show the proposal for approval instead of the "use the Plan
      tab" hint (`start()` already takes `request`; nothing passes it yet). Red-flag check stays first.
      Pairs with "Life changes" below. Update the §4 manual check when this lands.
- [ ] **Safety on the Planner route** (red-flag check on any free-text plan request, including the
      Revise comment, which still skips it). Needed as soon as chat requests reach the Planner.
- [ ] **Coach reads your plan and profile** (read-only `get_program`, `get_profile`) so answers fit
      your current month and week. Small.
- [ ] **Thin parent graph:** safety → router → Coach / Planner subgraphs, one trace per message (the
      standard LangGraph multi-agent shape; your "Multi-agent coordination" row). Keep it thin: it
      mostly does what `route()` does now.
- [ ] *Optional, decide after the eval:* one model-driven **handoff** Coach → Planner for mixed messages
      ("add that to my plan"), capped at one per message, approval still required. Only if mixed
      messages come up often enough to matter.
- [ ] *Optional experiment, after the eval set exists:* **single-agent baseline** — one agent with both
      tool sets and one merged prompt, still wrapped in the same code checks, approval and Verifier.
      Compare with the two-agent setup on the same QA + planning questions: citation pass rate,
      Verifier failures, safety cases, plan check failures, tokens and cost. Answers "is the Coach
      redundant?" with numbers (fits next to the no-retrieval baseline in M5).
- [ ] **Small LangChain / LangGraph swaps** (cleanup, ≈ −20 lines, no new deps):
      Planner `after_planner` → `tools_condition` with `{END: "review"}`; Verifier → 
      `with_structured_output(VerifierResult)` (check Ollama too); `parse_answer` / `parse_proposal`
      fences → `langchain_core.utils.json.parse_json_markdown`; `qa.py` token sum →
      `get_usage_metadata_callback()` (also counts Verifier tokens); `require_search` → force the first
      turn with `tool_choice="search_library"` instead of discarding an answer. Not worth it:
      `ToolNode` (parallel calls break the search-cap order and the retrieval `ContextVar`), or
      `create_agent` + `ToolCallLimitMiddleware` (only if the parent graph rewrite happens anyway).
- [ ] **Life changes:** `plan change "only 3 days a week now"`, event dates, equipment, "this week only
      Tue/Thu/Sat".
- [ ] **Training log + gates:** `log_session` (done / modified / missed), morning pain, next-day pain,
      jump results; `check_gate` from the tendon template's gate rules, with hand-worked test cases;
      check-in on roll-forward. Missed sessions are skipped, never made up.
- [ ] **Direct edits with pushback** (accept / adjust / decline, cited; gates and referrals never
      overridden).
- [ ] **Direct-edit test cases** (you review them), e.g. upper body on general days, core at the end,
      bodybuilding, jumping every day, pickup basketball, 4×3 instead of 5×4, trap-bar swap, skipping
      the deload, jumping through knee pain in a tendon stage, running on general days.
- [ ] **Evaluation:** ~10 planning questions with gold clips; 3–5 simulated athletes (standard,
      event in 10 weeks, knee pain, 3 days/week, no gym); edit cases; tokens and cost.

## 7. Open questions and later items

- **Missing a week or more:** the "skip, don't catch up" rule comes from a beginner video about single
  workouts; check what the transcripts say about longer gaps.
- **Macrocycle gates** (jump-session barometer: when bad sessions mean unload) — need transcript sources.
- **Physio line** is the longest part of pain answers (~60 words); AGENTS.md asks for a "short" line.
  Shorten the wording? (your call — it's your safety rule)
- **Chunk labels** (prescription vs talk, rehab vs healthy context): measure first with the planning
  questions; add only if recall is weak or the Verifier finds phase mix-ups.
- **Cited-gold undercount:** fine for now; q02 / q09 / q22 missed the direct answer, which the Verifier's
  "addresses the request" check is meant to catch.
- **Retrieval misses** q16 and q27 (vocabulary gap) — the Coach still answered them well.
- **More templates:** linear (beginner), block, bicyclic / two-peak.
- **Loosen citations later**, one knob at a time, only with eval numbers (numbers, gates, referrals and
  fake IDs stay strict).
- **M5 / M6:** red-team cases, no-retrieval baseline, MAST labelling, eval report, MCP server, demo.

## Rules that still apply

- Transcripts and anything derived from them (templates, plans, chunk text, traces) stay in
  `~/git/thp-ai/data`; never in this repo, never uploaded. Claude may write there only in chunks, index,
  eval, traces, templates and athlete.
- No Ollama / embedding / index rebuilds while the Mac is busy; Claude API calls with a cost estimate first.
- Commit code only, no data.
