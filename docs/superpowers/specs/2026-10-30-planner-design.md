# Planner agent: design

Date: 2026-10-30 · Status: draft for review · Milestone: M4 (program route)

## 1. Goal

The Planner is the main point of the project for the athlete: it writes a
periodized jump-training plan (macrocycle → mesocycles → weeks → sessions)
grounded only in the John Evans / THP Strength transcripts, and adjusts it as
the athlete gives more input. Answering one-off questions (the Coach) is
secondary.

Success means:

- An athlete gets a full plan outline and the next 1–2 weeks of sessions,
  every prescription traceable to a transcript clip.
- The plan changes, with the athlete's approval, in response to four kinds of
  input: a request for a new plan / the next weeks, life changes, logged
  numbers, and direct edits.
- No unsupported prescription reaches the athlete unflagged, gates decided by
  code are never overridden, and red flags still end in a referral.

## 2. Decisions so far

| Decision | Choice |
|---|---|
| Inputs that adjust the plan | All four, built in order: (1) generate / roll forward, (2) life changes, (3) logged numbers + gates, (4) direct edits |
| Template source | Transcripts only. The proposal's four-phase tendon track came from Google Drive and is **not** reused; it is rebuilt from the transcripts |
| Template authoring | Claude drafts from the transcripts with chunk IDs per field; the user reviews each template |
| Templates in v1 | The 6-month macrocycle (John Evans, *How to Get a 40" Vertical (Full Blueprint)*, `Icml891MLHA`, 2026-03-22) and the tendon track (*How To Get Rid Of Knee Pain (Full Blueprint)*, `9X_j-oF2ZDg`, 2026-10-16, plus supporting videos). Linear, block and bicyclic templates later |
| Level of detail | Rolling: the whole macro/meso outline up front; day-by-day sessions only 1–2 weeks ahead, rolled forward |
| Who writes the plan | The Planner LLM writes program JSON directly (option 2). Templates are its reference and the yardstick code checks against |
| Gates | Decided in code (`check_gate`) from logged numbers; the Planner must follow them |
| Approval | LangGraph `interrupt` before any program change is saved; SQLite checkpointer |
| Citation strictness | Strict in v1, loosened later one knob at a time with eval evidence (§9) |
| Display | Lean athlete view by default; full detail only in developer mode |
| Units | Loads in pounds (lb); verticals, reach, height and box heights in inches (in) |
| Where data lives | Everything transcript-derived or personal under `$THP_DATA_DIR` (`~/git/thp-ai/data`); the repo holds schemas, code, prompts, tests |

## 3. Storage

| Store | Path under `$THP_DATA_DIR` | Writer |
|---|---|---|
| Templates | `templates/<template_id>.yaml` | Drafted by Claude, approved by the user |
| Athlete profile | `athlete/profile.json` | Profile form / CLI, or a `profile_changes` block inside an approved proposal |
| Training log | `athlete/log.sqlite` | `log_session` (form / CLI, chat later); no approval needed |
| Program versions | `athlete/program/v0001.json`, `v0002.json`, … | Code, only after approval. Never overwritten or deleted |
| Checkpoints | `athlete/checkpoints.sqlite` | LangGraph `SqliteSaver` |
| Traces | `traces/<run_id>.jsonl` (existing) | Tracer |

`src/kb/paths.py` gains `templates_dir()` and `athlete_dir()`.

## 4. Data model (pydantic, strict, `extra="forbid"`)

### Template

```
Template
  id, name, kind (macrocycle | tendon_track), model (long_conjugate | ...)
  sources: [video_id]                     # videos the template was built from
  defaults: {lift_days, general_days, jump_session_minutes, ...}, cites[]
  cycles[]:                               # mesocycles, or tendon stages
    id, name, emphasis, goal, weeks {min, max}
    entry_criteria, exit_criteria, primes_next, cites[]
    day_types[]: id, label, cites[]
    prescriptions[]:
      day_type, exercise, equipment[]
      sets {min, max}, reps {min, max}, intensity {min, max, unit}, rest?, notes
      cites[]
    allowed_jumping?                      # tendon stages: what elastic work is allowed
  week_kinds: {normal: {volume: 1.0}, unload: {volume: {min, max}}, taper: {...}}, cites[]
  end: {kind: taper | unload, days {min, max}, min_loading_weeks}, cites[]
  gates[]:                                # rules check_gate evaluates
    id, track, signal (morning_pain | next_day_pain | jump_result | ...),
    condition, decision (hold | progress | unload | step_back), cites[]
  review: {drafted, reviewed_by_user: bool, notes}
```

Every field that carries a number, rule or criterion has `cites` (chunk IDs).
A template is loadable by the Planner only once `review.reviewed_by_user` is
true.

### Profile

```
Profile
  training_age_years, lifts {back_squat_lb?, power_clean_lb?, ...}
  standing_vertical_in?, approach_vertical_in?, standing_reach_in?, height_in?
  days_per_week, available_days[], session_minutes
  equipment[], event {date, name}?, goal
  knee_pain {status: none | ache | in_tendon_track, notes}?
  injury_notes
```

### Training log (SQLite tables)

- `sessions(date, program_version, planned_ref, exercise, sets, reps, load, feel, notes)`
- `daily(date, morning_pain, test_movement)`
- `next_day_pain(date, after_session_date, score)`
- `jump_results(date, kind, height_in, flight_time_s)`

What was actually done is logged; the program is not changed by logging.

### Program (one file per version)

```
Program
  version, based_on, created_at, change_summary, profile_snapshot
  macrocycle: model, template_id, start, event_date?, end (taper | unload), cites[]
  mesocycles[]: index, cycle_id, name, emphasis, start, end, goal,
                entry_criteria, exit_criteria, primes_next, cites[]
  tendon_track?: template_id, stage_id, entered_on, gate_to_next, allowed_jumping, cites[]
  weeks[]:                                # only the next 1–2 are filled
    start, mesocycle_index, kind (normal | unload | taper), volume_modifier
    days[]: date, day_type
      sessions[]: exercise, sets, reps, intensity, rest?, notes?, cites[],
                  deviation? {reason, cites[], requested_by_user: bool}
```

### Proposal (what the Planner returns)

```
Proposal
  kind: new | roll_forward | life_change | checkin | edit
  request                                 # the athlete's words, if any
  decision: accept | adjust | decline     # for edits; accept otherwise
  summary                                 # ≤ 3 sentences, restates the diff
  reasons[]: text, cites[]
  profile_changes?: {field: value}
  replace_outline?: {macrocycle, mesocycles, tendon_track}
  replace_weeks?: [Week]
```

Code merges a proposal into a candidate `Program` (next version number), runs
the checks, then shows the diff for approval.

### Gate result

```
GateResult: track, decision (hold | progress | unload | step_back | undecided),
            rule_id, inputs (the logged values used), cites[]
```

`undecided` (not enough data, or no rule matches) is handed to the Planner;
its choice is then checked by the Verifier against the cited rule.

### Units

Athlete-facing values use pounds for loads and inches for verticals, reach,
height and box heights. Templates keep a number in the unit the transcript
used (`{value, unit}`, e.g. `40 cm` from the 40" Blueprint's depth jumps) so
the citation stays exact; code converts to lb / in for the program and the
views, and the fidelity check (§7 check 4) compares after conversion.
Percent-of-max intensities stay as percentages. `jump_height` gains an inches
result next to cm.

## 5. Tools (all read-only for the Planner)

| Tool | Returns | Stage |
|---|---|---|
| `search_library(query, k)` | Existing | 3 |
| `get_cycle(template_id, cycle_id?)` | A reviewed template, or one cycle/stage of it, with cites | 1 |
| `get_profile()` | Profile | 2 |
| `get_program(version?)` | Current (or given) program version | 2 |
| `get_log(days)` | Summary of recent logged sessions, pain, jump results, feel notes | 6 |
| `check_gate(track)` | `GateResult`s computed in code from the log and the template's `gates` | 6 |
| `jump_height(flight_time_s)` | Existing | — |

Caps, enforced in code like the Coach's search cap: 6 `search_library` calls
and 12 tool calls per proposal attempt. Chunk IDs returned by
`search_library` and template cites returned by `get_cycle` together form the
"retrieved this run" set for the provenance check.

## 6. Flow

```
message / action
  → safety (existing red-flag code; red flag → referral, stop)
  → router (code)
      question → Coach route (existing answer_question)
      program  → load context (profile, program, log summary, gate results)
               → Planner agent (tool loop, caps) → Proposal
               → merge → code checks → Verifier
                   fail → back to Planner with reasons (max 2 retries,
                          then stop and show what failed)
               → show diff (athlete or developer view)
               → interrupt: approve | reject | revise "<comment>"
                   revise → comment back to Planner (new attempt)
               → approve → code saves program v000N+1
```

Entry points:

| Action | CLI (`scripts/plan.py`) | UI (Plan tab) | Stage |
|---|---|---|---|
| New plan | `plan new` | button | 3 |
| Roll forward (runs check-in first once stage 6 exists) | `plan next` | button | 3 |
| Show plan | `plan show [--full]` | tab | 3 |
| Profile | `plan profile` | form | 2 |
| Log | `plan log ...` | form | 6 |
| Life change / direct edit | `plan change "<text>"` | text box | 5, 7 |

Chat routing (UI chat, `ask.py`): a keyword router in code sends plan/program
requests ("plan", "program", "this week", "only N days", an event date, …)
to the program route and everything else to the Coach. An LLM router only if
the keyword router misroutes in practice.

Pushback rules for direct edits (stage 7): the Planner cannot override a
`check_gate` decision, the tendon track's allowed jumping, a red-flag
referral, or an unload/taper unless it finds a supporting cite. On conflict it
returns `decision: decline` (or `adjust` with the nearest allowed change) and
cites the rule. The athlete may still approve a user-requested deviation
(`requested_by_user: true`); it is marked as such and the Verifier's warning
stays visible.

## 7. Checks

### Code checks (deterministic; run on the merged candidate)

1. **Schema**: strict pydantic parse of the Proposal and the merged Program.
2. **Provenance**: every cite was returned this run by `search_library` or `get_cycle`.
3. **Coverage**: every session, mesocycle and tendon stage has ≥ 1 cite; every `deviation` has a reason and ≥ 1 cite (or `requested_by_user`).
4. **Template fidelity**: sets / reps / intensity within the template range for that cycle and day type, and the exercise is in the template — otherwise a `deviation` is required.
5. **Calendar**: mesocycles contiguous with no overlap; weeks inside their mesocycle; nothing scheduled before today; training days match the profile; with an event date, the taper ends on it and loading meets the template's `min_loading_weeks`.
6. **Week kinds**: unload / taper volume modifiers within the template range.
7. **Gates**: no progression where `check_gate` said hold or step_back; elastic work within the tendon stage's `allowed_jumping`.
8. **Equipment**: no exercise whose `equipment` is missing from the profile.

Failures go back to the Planner as exact reasons.

### Verifier (LLM, fresh context, `VERIFIER_MODEL`, `prompts/verifier.v2.md`)

Input: only the changed items, the text of the chunks they cite, the template
fields they cite, and (for edits) the athlete's request. No Planner
conversation. Output JSON:

```
{verdict: pass | fail,
 items: [{path, support: supported | partly | unsupported, reason}],
 phase_rule_ok: bool, summary_matches_diff: bool, addresses_request: bool | null}
```

Any `unsupported` item, a phase-rule violation (rehab advice in a healthy
cycle or the reverse), a summary that misdescribes the diff, or an edit
proposal that doesn't address the request → fail. `partly` passes with a
warning shown in the diff.

A second mode checks Coach answers (closes the M3 Verifier item): same output
shape, items are answer points, `addresses_request` checks the direct answer
is present (the q02 / q09 / q22 gap).

## 8. Views

- **Athlete view (default)**: current position ("Month 2 of 6 · Absolute
  strength · Week 2 of 4"), the week as a compact day-by-day list, sources
  behind a single "sources" toggle. Proposals as "What changes / Why" in 2–4
  lines with Approve / Reject / Revise. Verifier output only as a one-line
  warning when there is one. No chunk IDs.
- **Developer view** (UI "Developer view" checkbox, CLI `--full`): source links
  per item, the full diff, code-check results, Verifier verdict per item,
  Planner tool calls and searches, tokens, trace path.

## 9. Citation strictness (v1 strict; future knobs)

Citation rules live in one module so they can be loosened by configuration.
Possible later steps, each only after the eval shows a low unsupported rate,
and each the user's call (AGENTS.md rule 1 is their policy): coarser cites
(per session / day), a labelled "general guidance" field kept away from
numbers and medical content, uncited reasoning that explains a choice. Never
loosened: numbers, gates and the tendon track, red-flag referrals, fabricated
chunk IDs.

## 10. Testing (pytest, mocks only)

- Proposal → candidate merge; approve writes the next version, reject writes
  nothing, nothing is overwritten.
- Each of the 8 code checks: one passing and one failing fixture.
- `check_gate`: hand-worked cases derived from the reviewed template rules.
- Template loader: unreviewed templates are refused; every numeric field has cites.
- Planner graph with `ScriptedChatModel`: tool caps; max 2 retries; interrupt
  and resume through the checkpointer for approve, reject and revise.
- Router keyword cases.
- Verifier with scripted outputs, and planted-fault fixtures: fabricated ID,
  off-template number, rehab rule in a healthy cycle, misdescribing summary.
- Rendering: athlete and developer views.

## 11. Evaluation (real Claude; cost estimate approved before each run)

- About 10 planning questions with gold clips (e.g. month-3 emphasis, taper
  length, when to progress from slow squats to drops) → retrieval recall for
  planning; decides whether chunk labels are needed (§13).
- 3–5 simulated athletes: standard 6-month, event in 10 weeks, knee pain in
  the tendon track, 3 days a week, no gym. Metrics from the proposal: cycle
  placement, gate compliance, taper before the event, code-check pass rate,
  Verifier planted-fault catch rate, tokens and cost.
- **Direct-edit cases** (stage 7), about 10 athlete requests run against a
  fixed starting program, to see what the Planner does and whether it agrees
  with what THP and John Evans say. Each case is written like the Q&A gold:
  the request, the starting point (mesocycle, week, day type), the expected
  decision (accept / adjust / decline) and the key points, all taken from the
  transcripts with gold clips, then reviewed by the user. Stored in
  `$THP_DATA_DIR/eval/plan_edits.yaml`. The expected decision is whatever the
  transcripts support, not assumed in advance. Starting cases (the library
  has dedicated videos for the first three):
  - "I want to add some upper body on general days"
  - "I want to add some core at the end"
  - "Can I add bodybuilding / hypertrophy work so I look better?"
  - "I want to jump every day" / "more plyos"
  - "I play pickup basketball 3 times a week" (does it count as jump volume?)
  - "Squats 4×3 instead of 5×4 for the rest of this month"
  - "Swap back squats for trap-bar deadlifts"
  - "Skip the deload this week, I feel great"
  - "Let me jump through the knee pain" while in a tendon stage (gate must hold)
  - "Add conditioning / running on general days"

  Scored per case: decision matches; key points covered (Verifier
  `addresses_request` plus the athlete-view text read against the gold);
  cites a gold clip or an equivalent clip; code checks pass; gates never
  overridden. The report also shows, per case, the Planner's athlete-view
  reply next to a short note of what the gold clips say, so the user can read
  "what it thinks" directly (private, under `$THP_DATA_DIR/eval/`).
  Scripted pytest fixtures cover the accept, adjust and decline paths
  mechanically; the real-Claude run judges the content.
- Results with IDs and numbers only go in `results/`; plans and answers stay
  under `$THP_DATA_DIR`.

## 12. Build order (each stage ends runnable and committed)

| # | Stage | Done when |
|---|---|---|
| 0 | Commit current `m3-qa` work; branch `m4-planner` | Clean tree |
| 1 | Templates: draft macrocycle and tendon track from transcripts; user review; schema, loader, `get_cycle` | `get_cycle` returns a reviewed, cited template |
| 2 | Profile, program and version stores; profile form / CLI; the 8 code checks | Hand-built programs pass / fail the checks as expected |
| 3 | Planner agent (`prompts/planner.v2.md`), router, interrupt approval, `plan new`, `plan next`, `plan show`, both views | A real plan approved and saved (input type 1) |
| 4 | Verifier (program and Q&A modes), planted-fault tests | Every planted fault caught |
| 5 | `plan change` for life changes | Input type 2 |
| 6 | Log, `check_gate`, check-in | Input type 3; `check_gate` matches every hand-worked case |
| 7 | Direct edits with pushback; write and review the direct-edit cases (§11) | Input type 4; edit cases run end to end |
| 8 | Evaluation run and report | Metrics in `results/` |

## 13. Deferred

- **Chunk labels** (prescription vs talk; rehab vs performance context):
  measure first with the planning questions; add a regex prescription flag as
  a ranking boost if recall is weak; LLM / hand tagging of context only if the
  Verifier shows phase-rule mix-ups.
- **More templates**: linear (beginner), block, bicyclic / two-peak.
- **LLM router**, **LLM safety check** (M3 items), chat-based logging.
- **Citation loosening** (§9).

## 14. Constraints carried over

- Transcripts and anything derived from them (templates, plans, chunk text)
  never enter this repo, are never uploaded or published. Claude API calls
  with chunk text are approved; Ollama, embedding and index rebuilds only
  when the machine is free.
- Approved writes in `~/git/thp-ai/data`: `templates/`, `athlete/` (plus the
  earlier chunks, index, eval, traces). No git in thp-ai; never delete there.
- `langgraph-checkpoint-sqlite` approved for this repo's `.venv`.
- AGENTS.md rules apply to the Planner and Verifier (prepended by `src/prompts.py`).

## 15. Open questions (resolved during stage 1)

- How the knee-pain blueprint actually divides its stages (it does not use
  "phase one/two" wording) and what its gates are.
- What the transcripts say about shortening the macrocycle for an event less
  than 6 months away; if nothing, the Planner says so instead of inventing a
  compression.
- How the tendon track and the macrocycle interact week to week (e.g. which
  macrocycle sessions are replaced while in a tendon stage).
