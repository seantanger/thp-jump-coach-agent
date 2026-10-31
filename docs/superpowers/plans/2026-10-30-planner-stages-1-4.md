# Planner (stages 1–4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Planner agent that writes a cited, periodized plan (macro/meso outline + next 1–2 weeks of sessions) from two reviewed transcript templates, checks it in code and with a fresh-context Verifier, and saves it only after the athlete approves.

**Architecture:** Templates (YAML, private data dir) are loaded into strict pydantic models. A LangGraph graph runs the Planner LLM in a capped tool loop; it returns a `Proposal` JSON that code merges into a candidate `Program`, checks (8 code checks, then the Verifier), retries at most twice, then pauses with `interrupt` for approve / reject / revise; approval writes a new, never-overwritten program version. A code keyword router sends chat messages to the program route or the existing Coach.

**Tech Stack:** Python 3.12 (uv), LangGraph ≥ 1.2.17 with `langgraph-checkpoint-sqlite`, langchain-core tools, pydantic v2 (strict), PyYAML, Streamlit (ui group), pytest with `ScriptedChatModel` mocks.

**Spec:** `docs/superpowers/specs/2026-10-30-planner-design.md`

**Out of scope here (plan 2, after template review):** life changes (`plan change`), training log + `check_gate` + check-in, direct edits with pushback and the direct-edit cases, the evaluation run. Code below leaves the hooks those need (`GateResult`, `Proposal.kind`, `profile_changes`), nothing more.

## Global Constraints

- Transcript-derived data (templates, plans, chunk text, traces) and personal data live only under `$THP_DATA_DIR` (`~/git/thp-ai/data`): templates in `templates/`, athlete data in `athlete/`. Never in this repo; never uploaded or published. No git in thp-ai; never delete files there.
- Tests use mocks only (no Claude, no Ollama, no index). Real-Claude runs only in Task 10, with a cost estimate first.
- No Ollama / embedding / index rebuilds unless the user says the machine is free; real runs use `RETRIEVAL_MODE=bm25`.
- `langgraph-checkpoint-sqlite` may be added to this repo's `.venv`; nothing installed outside the repo.
- Units: loads in **lb**, verticals / reach / height / box heights in **in**. Templates keep the transcript's unit (`{value, unit}`); code converts. Percent intensities stay `%`.
- Citations strict (spec §9): every session, mesocycle, tendon stage has ≥ 1 cite; no cite outside this run's retrieved set.
- Planner caps: 6 `search_library` calls, 12 tool calls per attempt; at most 2 retries after a failed check.
- Athlete view lean (no chunk IDs, no check output except a one-line warning); developer view (`--full`, UI checkbox) shows everything.
- Prompts are versioned files loaded by `src/prompts.py` (AGENTS.md prepended). New: `prompts/planner.v2.md`, `prompts/verifier.v2.md`.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Commit code only, no data.

## Review Focus

1. **Stale approval:** the athlete approves a proposal built on version N after version N+1 was saved (two UI tabs, or CLI + UI) → save must refuse with status `stale`, not overwrite or fork. Test in Task 6.
2. **No profile yet:** `plan new` before any profile exists → status `needs_profile` and a pointer to `plan profile`; no Planner call. Test in Task 6.
3. **Unit rounding in the fidelity check:** a template depth-jump box of `40 cm` written as `16 in` (15.75 in) must pass; `24 in` must fail. Tolerance 0.5 in / 5 lb / 1 percentage point. Test in Task 5.
4. **Rolling forward after a gap:** `plan next` run when the last filled week ended weeks ago → proposal must start at the current week, and the calendar check rejects weeks in the past. Test in Task 5 (calendar) and Task 6 (context passes `today`).
5. **Malformed model output** (markdown fences, prose before JSON, extra keys) → fences/prose stripped like `parse_answer`; extra keys fail the schema check and count as an attempt with the parse error fed back, never a crash. Test in Task 6.

---

### Task 1: Units, data paths, jump height in inches

**Files:**
- Create: `src/units.py`
- Modify: `src/kb/paths.py` (add `templates_dir`, `athlete_dir`), `src/tools.py` (jump_height result), `prompts/coach.v4.md` (jump_height wording), `tests/test_graph.py` (jump_height assertion)
- Test: `tests/test_units.py`

**Interfaces:**
- Produces:
  - `Quantity(BaseModel)`: `value: float`, `unit: Literal["lb", "kg", "in", "cm", "m", "%", "s", "min"]` (strict, `extra="forbid"`)
  - `convert(q: Quantity, unit: str) -> Quantity` — kg↔lb (1 kg = 2.20462 lb), cm/m↔in (1 in = 2.54 cm); same unit returns a copy; incompatible units raise `ValueError`
  - `display(q: Quantity) -> str` — athlete units: kg→lb, cm/m→in, rounded to 1 decimal, trailing `.0` dropped (`"16 in"`, `"225 lb"`, `"80%"`)
  - `templates_dir() -> Path` = `data_dir() / "templates"`; `athlete_dir() -> Path` = `data_dir() / "athlete"`
  - `jump_height` tool returns `{"cm": float, "in": float}` (both 2 decimals)

- [ ] **Step 1: Write failing tests** in `tests/test_units.py`:

```python
def test_convert_and_display():
    assert convert(Quantity(value=40, unit="cm"), "in").value == pytest.approx(15.748, abs=1e-3)
    assert convert(Quantity(value=100, unit="kg"), "lb").value == pytest.approx(220.462, abs=1e-3)
    assert display(Quantity(value=40, unit="cm")) == "15.7 in"
    assert display(Quantity(value=225, unit="lb")) == "225 lb"
    assert display(Quantity(value=80, unit="%")) == "80%"
    with pytest.raises(ValueError):
        convert(Quantity(value=1, unit="lb"), "in")

def test_jump_height_reports_inches():
    out = jump_height.invoke({"flight_time_s": 0.52})
    assert out == {"cm": 33.16, "in": 13.06}
```

- [ ] **Step 2: Run** `uv run pytest tests/test_units.py -v` — expect FAIL (module not found).
- [ ] **Step 3: Implement** `src/units.py`, the two path helpers, and change `jump_height` to return the dict (keep `jump_height_cm`). Update `tests/test_graph.py::test_agent_calls_tool_and_uses_result` to assert `json.loads(messages[2].content) == {"cm": 33.16, "in": 13.06}` (and the `second_call` check accordingly), and the `jump_height` line in `prompts/coach.v4.md` to "returns height in cm and inches; quote inches to the athlete".
- [ ] **Step 4: Run** `uv run pytest -q` — expect all pass.
- [ ] **Step 5: Commit** `git commit -m "Units (lb/in) module, template and athlete data paths, jump_height in inches"`.

---

### Task 2: Template schema, loader and `get_cycle`

**Files:**
- Create: `src/planner/__init__.py`, `src/planner/templates.py`
- Test: `tests/test_templates.py` (synthetic YAML in `tmp_path`; no real template content)

**Interfaces:**
- Consumes: `Quantity` (Task 1), `templates_dir()` (Task 1)
- Produces (all pydantic, strict, `extra="forbid"`; field names exactly as spec §4 "Template"):
  - `Range(min: float, max: float, unit: str | None = None)` with `min <= max` validated
  - `Prescription`, `DayType`, `Cycle`, `WeekKind`, `TemplateEnd`, `Gate`, `Review`, `Template`
    - `Prescription.exercise: str`, `equipment: list[str]`, `sets: Range`, `reps: Range`, `intensity: Range | None`, `rest: str | None`, `notes: str | None`, `day_type: str`, `cites: list[str]`
    - `Cycle.id, name, emphasis, goal: str`, `weeks: Range`, `entry_criteria, exit_criteria: str`, `primes_next: str | None`, `day_types: list[DayType]`, `prescriptions: list[Prescription]`, `allowed_jumping: list[str] | None` (exercise names allowed in a tendon stage; `None` = no restriction), `cites: list[str]`
    - `Template.week_kinds: dict[str, WeekKind]` where `WeekKind.volume: Range` (normal = `{min: 1, max: 1}`)
    - `Template.elastic_exercises: list[str]` — exercise names that count as jumping / elastic loading (used by the gate check)
    - `Template.scheduling: Scheduling(pattern: list[str], hard_day_types: list[str], min_days_between_hard: int, allowed_back_to_back: list[list[str]], missed_sessions: Literal["skip"], cites)` — day types must exist in the template's cycles (added after the user asked for flexible days)
    - `TemplateEnd.kind: Literal["taper", "unload"]`, `days: Range`, `min_loading_weeks: int`
    - `Gate.id, track, signal, condition: str`, `decision: Literal["hold","progress","unload","step_back"]`, `cites`
    - `Review.drafted: date`, `reviewed_by_user: bool`, `notes: str`
  - A model validator on `Template`: every `Cycle`, `Prescription`, `Gate`, `TemplateEnd` and the `defaults` block has `len(cites) >= 1`, else `ValueError` naming the path (e.g. `cycles[2].prescriptions[0]`).
  - `load_template(template_id: str, directory: Path | None = None, require_reviewed: bool = True) -> Template` — reads `<dir>/<id>.yaml`; raises `PermissionError("template <id> is not reviewed yet")` when `require_reviewed` and not `review.reviewed_by_user`.
  - `list_templates(directory: Path | None = None) -> list[str]` — reviewed template IDs only.
  - `template_cites(t: Template) -> set[str]`
  - `find_prescription(t: Template, cycle_id: str, day_type: str, exercise: str) -> Prescription | None` — exercise matched case- and whitespace-insensitively.
  - `get_cycle` tool, `@tool(response_format="content_and_artifact")`, args `template_id: str, cycle_id: str | None = None`; artifact `{"template_id": str, "data": <template or cycle dict>, "cites": sorted list}`; content is the artifact as JSON. Unknown / unreviewed template → raises (graph turns it into an error ToolMessage).

- [ ] **Step 1: Write failing tests**: `test_load_reviewed_template_round_trips`, `test_unreviewed_template_refused` (`PermissionError`), `test_uncited_prescription_rejected` (message contains `cycles[0].prescriptions[0]`), `test_range_min_le_max`, `test_find_prescription_case_insensitive` (`"Back Squat "` finds `"back squat"`), `test_get_cycle_artifact_lists_cites` (artifact `cites` equals the union of that cycle's cites), `test_list_templates_skips_unreviewed`. Use a `tmp_path` fixture writing one small YAML (2 cycles, 2 prescriptions, 1 gate) and monkeypatch `src.planner.templates.templates_dir` to it.
- [ ] **Step 2: Run** `uv run pytest tests/test_templates.py -v` — expect FAIL.
- [ ] **Step 3: Implement** `src/planner/templates.py` as above.
- [ ] **Step 4: Run** `uv run pytest -q` — expect all pass.
- [ ] **Step 5: Commit** `"Template schema, loader and get_cycle tool"`.

---

### Task 3: Draft the two templates from the transcripts; user review (content task, gate)

No TDD; this task produces private data and a small helper script. **Stop at the end for the user's review.**

**Files:**
- Create: `scripts/template_sources.py` (repo; prints chunks, writes nothing)
- Create (private, not committed): `$THP_DATA_DIR/templates/long_conjugate_6mo.yaml`, `$THP_DATA_DIR/templates/tendon_track.yaml`, `$THP_DATA_DIR/templates/REVIEW.md`

**Interfaces:**
- Consumes: `load_chunks(method)`, `load_template(..., require_reviewed=False)` (Task 2)
- Produces: two templates that load with `require_reviewed=False`; template IDs `long_conjugate_6mo` and `tendon_track`.

- [ ] **Step 1:** Write `scripts/template_sources.py`: `uv run python -m scripts.template_sources <video_id> [--grep REGEX]` prints that video's `charsplit_matched` chunks in time order as `chunk_id  mm:ss  text`, optionally only chunks matching the regex. Local read only.
- [ ] **Step 2:** Read the 40" Blueprint (`Icml891MLHA`) in full; draft `long_conjugate_6mo.yaml`: six mesocycles in order with emphasis, weeks, day types (lift Mon/Wed/Fri, general Tue/Thu, jump session), prescriptions with ranges, deload rule, the jump-session minutes progression, the taper (`end`), every field cited with chunk IDs from this video or other transcripts found by `--grep` on related videos (e.g. "5 Athletes To A 50\" Vertical", "Base Athleticism"). Numbers keep the transcript's unit.
- [ ] **Step 3:** Read the knee-pain blueprint (`9X_j-oF2ZDg`) in full plus supporting transcripts (`ZN8wh4FFZuA`, `VMSF8C25mxY`, `72YX7nkYmYE`, `TEQsK1qSKhg`, `U9UECfyq3uI` and others found by `--grep`); draft `tendon_track.yaml` with the stages **as the transcript divides them** (not the proposal's four phases), each stage's allowed jumping, entry/exit criteria and gate rules (`gates[]`), all cited. Nothing from the Google Drive sheets.
- [ ] **Step 4:** Validate: `load_template(id, require_reviewed=False)` succeeds for both (all fields cited, ranges valid).
- [ ] **Step 5:** Write `REVIEW.md`: per template, a field-by-field table (field, value, cites, a one-line paraphrase of what the clip says — no quotes), plus answers to spec §15 open questions (stage division, shortening for an event < 6 months, how a tendon stage restricts macrocycle sessions). Flag anything uncertain.
- [ ] **Step 6:** Commit the script only: `"Helper to read a video's chunks for template drafting"`.
- [ ] **Step 7: STOP — user reviews.** Apply their corrections; they (or Claude on their say-so) set `review.reviewed_by_user: true`. Plan 2 is written after this review.

---

### Task 4: Profile, program and proposal schema; version store; merge and diff

**Files:**
- Create: `src/planner/schema.py`, `src/planner/store.py`, `src/planner/merge.py`
- Test: `tests/test_planner_store.py`

**Interfaces:**
- Consumes: `Quantity` (Task 1), `athlete_dir()` (Task 1)
- Produces (pydantic, strict, `extra="forbid"`; fields exactly as spec §4 Profile / Program / Proposal / GateResult, with these concrete types):
  - `Profile`: `training_age_years: float`, `lifts: dict[str, float]` (keys end in `_lb`), `standing_vertical_in`, `approach_vertical_in`, `standing_reach_in`, `height_in: float | None`, `days_per_week: int` (1–7), `available_days: list[Literal["mon",...,"sun"]]`, `session_minutes: int`, `equipment: list[str]`, `event: Event | None` (`date: date, name: str`), `goal: str`, `knee_pain: KneePain | None`, `injury_notes: str = ""`
  - `Session`: `exercise: str`, `sets: int`, `reps: int`, `intensity: Quantity | None`, `rest: str | None`, `notes: str | None`, `cites: list[str]`, `deviation: Deviation | None` (`reason: str`, `cites: list[str]`, `requested_by_user: bool = False`)
  - `Day(date: date, day_type: str, sessions: list[Session])`, `Week(start: date, mesocycle_index: int, kind: Literal["normal","unload","taper"], volume_modifier: float, days: list[Day])`
  - `Mesocycle(index, cycle_id, name, emphasis, start: date, end: date, goal, entry_criteria, exit_criteria, primes_next, cites)`, `Macrocycle(model, template_id, start: date, event_date: date | None, end: Literal["taper","unload"], cites)`, `TendonTrack(template_id, stage_id, entered_on: date, gate_to_next: str, allowed_jumping: list[str], cites)`
  - `Program(version: int, based_on: int | None, created_at: datetime, change_summary: str, profile_snapshot: Profile, macrocycle, mesocycles: list[Mesocycle], tendon_track: TendonTrack | None, weeks: list[Week])`
  - `Proposal(kind: Literal["new","roll_forward","life_change","checkin","edit"], request: str | None, decision: Literal["accept","adjust","decline"], summary: str, reasons: list[Reason], profile_changes: dict | None, replace_outline: Outline | None, replace_weeks: list[Week] | None)`; `Outline(macrocycle, mesocycles, tendon_track)`; `Reason(text, cites)`
  - `GateResult(track, decision: Literal["hold","progress","unload","step_back","undecided"], rule_id: str | None, inputs: dict, cites)`
  - `parse_proposal(raw: str) -> Proposal` — strips ``` fences and any text before the first `{` / after the last `}`, then `model_validate_json`.
  - store: `load_profile(d: Path | None = None) -> Profile | None`, `save_profile(p: Profile, d=None) -> Path` (`athlete/profile.json`), `latest_version(d=None) -> int` (0 when none), `load_program(version: int | None = None, d=None) -> Program | None`, `save_program(p: Program, d=None) -> Path` — writes `athlete/program/v{version:04d}.json`; raises `FileExistsError` if the file exists and `StaleProgramError` if `p.version != latest_version() + 1`.
  - `merge_proposal(current: Program | None, proposal: Proposal, profile: Profile, now: datetime) -> Program` — version `= (current.version if current else 0) + 1`, `based_on = current.version if current else None`; `profile_snapshot` = profile with `profile_changes` applied; `kind == "new"` requires `replace_outline` and replaces everything; otherwise outline replaced only if given, and each week in `replace_weeks` replaces the week with the same `start` or is appended; weeks kept in start order. Raises `ValueError` for a `new` proposal without an outline or a non-`new` proposal with no current program.
  - `Change(path: str, before: Any, after: Any)`; `diff_programs(old: Program | None, new: Program) -> list[Change]` — paths like `mesocycles[1].emphasis`, `weeks[2026-11-02].days[2026-11-04].sessions[0]`; whole sessions / mesocycles compared as units.

- [ ] **Step 1: Write failing tests**: `test_save_program_never_overwrites` (`FileExistsError`), `test_save_program_rejects_stale_version` (`StaleProgramError` when saving v2 while v2 exists or v1 is missing), `test_merge_new_then_roll_forward` (v1 from a `new` proposal; a `roll_forward` with one replaced + one appended week gives v2 with `based_on == 1` and weeks sorted), `test_merge_applies_profile_changes` (`{"days_per_week": 3}` lands in `profile_snapshot`, the stored profile file is unchanged), `test_merge_rejects_new_without_outline`, `test_diff_reports_changed_session_and_mesocycle` (exact paths), `test_parse_proposal_strips_fences_and_prose`, `test_parse_proposal_rejects_extra_keys` (`ValidationError`), `test_profile_rejects_kg_lift_key` (a `lifts` key not ending `_lb` fails).
- [ ] **Step 2: Run** `uv run pytest tests/test_planner_store.py -v` — expect FAIL.
- [ ] **Step 3: Implement** the three modules.
- [ ] **Step 4: Run** `uv run pytest -q` — expect all pass.
- [ ] **Step 5: Commit** `"Planner schema, versioned program store, proposal merge and diff"`.

---

### Task 5: The 8 code checks

**Files:**
- Create: `src/planner/checks.py`
- Test: `tests/test_planner_checks.py`

**Interfaces:**
- Consumes: `Template`, `find_prescription` (Task 2); `Program`, `Profile`, `GateResult` (Task 4); `convert` (Task 1)
- Produces:
  - `CheckFailure(check: Literal["schema","provenance","coverage","fidelity","calendar","week_kinds","gates","equipment"], path: str, reason: str)` (pydantic)
  - `run_checks(candidate: Program, *, profile: Profile, templates: dict[str, Template], retrieved_ids: set[str], gates: list[GateResult], today: date) -> list[CheckFailure]` — runs checks 2–8 of spec §7 in order and returns all failures (schema failures come from parsing, Task 6).
  - Tolerances: `FIDELITY_TOLERANCE = {"in": 0.5, "lb": 5.0, "%": 1.0}` applied after converting the template range to athlete units.
  - Calendar rules (spec §7 check 5): mesocycles contiguous (`next.start == prev.end + 1 day`), each week's 7 days inside its mesocycle, every `Day.date >= today`, training days per week `<= profile.days_per_week` and weekdays within `profile.available_days`; days whose `day_type` is in `scheduling.hard_day_types` are at least `scheduling.min_days_between_hard` days apart unless the (earlier, later) pair is in `allowed_back_to_back`; no fixed weekdays are required; with `macrocycle.event_date`: the last mesocycle ends on it, its final `template.end.days.min..max` days are `taper` weeks, and loading weeks before the taper `>= template.end.min_loading_weeks`.
  - Gates (check 7): for a `GateResult` on track `tendon` with `inputs["stage_id"]` = the current stage, `hold` requires `candidate.tendon_track.stage_id` to equal it, `step_back` requires the stage before it in the template's cycle order, `progress` allows the next one; never more than one stage forward. When `candidate.tendon_track` is set, every session whose exercise is in the tendon template's `elastic_exercises` must be in `tendon_track.allowed_jumping`. Plan 2 adds the logged-signal gates.

- [ ] **Step 1: Write failing tests**, one pass + one fail per check, built from a small in-test template and program factory:
  - `test_provenance_flags_unretrieved_cite`
  - `test_coverage_requires_cites_and_deviation_reason`
  - `test_fidelity_passes_within_range_and_unit_tolerance` — template box `{min: 40, max: 40, unit: cm}`, session `16 in` passes
  - `test_fidelity_fails_out_of_range_without_deviation` — `24 in` fails; same session with `deviation` (reason + cite) passes
  - `test_fidelity_unknown_exercise_needs_deviation`
  - `test_calendar_rejects_gap_overlap_and_past_days` — Review Focus 4: a week starting before `today` fails
  - `test_calendar_event_needs_taper_and_min_loading`
  - `test_calendar_follows_available_days_not_fixed_weekdays` — lifts on Tue/Thu/Sat with `available_days` = those pass; two lift days on consecutive dates fail with reason naming `min_days_between_hard`; an `allowed_back_to_back` pair (elastic → hsr) passes
  - `test_week_kinds_volume_range`
  - `test_gates_block_progress_on_hold`
  - `test_equipment_missing_fails`
  - `test_clean_program_has_no_failures`
- [ ] **Step 2: Run** `uv run pytest tests/test_planner_checks.py -v` — expect FAIL.
- [ ] **Step 3: Implement** `src/planner/checks.py` (one private function per check; `run_checks` concatenates).
- [ ] **Step 4: Run** `uv run pytest -q` — expect all pass.
- [ ] **Step 5: Commit** `"Planner code checks (provenance, coverage, fidelity, calendar, week kinds, gates, equipment)"`.

---

### Task 6: Planner graph with caps, retries, interrupt approval and versioned save

**Files:**
- Modify: `src/graph.py` (extract the capped tool runner), `pyproject.toml` / `uv.lock` (`uv add langgraph-checkpoint-sqlite`)
- Create: `src/planner/tools.py`, `src/planner/graph.py`, `src/planner/run.py`, `prompts/planner.v2.md`
- Test: `tests/test_planner_graph.py`

**Interfaces:**
- Consumes: Tasks 2, 4, 5; `search_library`, `jump_height`, `run_tool`, `Tracer`, `load_prompt`, `get_llm`
- Produces:
  - In `src/graph.py`: `run_capped(calls: list[dict], tools: dict, used: dict[str, int], caps: dict[str, int], total_cap: int | None, tracer: Tracer) -> tuple[list[ToolMessage], dict[str, int]]` — `used` counts per tool name plus `"_total"`; over-cap calls get the existing "limit reached" error message (generalised to name the cap). The Coach's `run_tools` calls it with `caps={"search_library": SEARCH_CAP}`, `total_cap=None`; existing Coach tests stay green unchanged.
  - `src/planner/tools.py`: `get_profile()` and `get_program(version: int | None = None)` tools (JSON content, dict artifact); `PLAN_TOOLS = [get_cycle, get_profile, get_program, search_library, jump_height]`; `PLAN_CAPS = {"search_library": 6}`, `PLAN_TOTAL_CAP = 12`, `MAX_RETRIES = 2`.
  - `src/planner/graph.py`: `PlanState(MessagesState)` with `action: str`, `request: str | None`, `today: date`, `used: dict[str, int]`, `attempts: int`, `proposal: dict | None`, `candidate: dict | None`, `failures: list[dict]`, `verifier: dict | None`, `status: str`, `saved_version: int | None`.
    `build_plan_graph(llm: BaseChatModel | None = None, verify: Callable[[list[Change], Proposal], tuple[list[str], list[str], dict | None]] | None = None, tracer: Tracer | None = None, checkpointer=None)` → compiled graph. `verify` returns `(failures, warnings, raw_result)`; failures feed the retry path, warnings and `raw_result` are kept in state `verifier`. Nodes: `context` (no profile → `status="needs_profile"`, END; otherwise a HumanMessage with action, request, today, profile, current program summary, and the reviewed template IDs), `planner` (LLM bound to `PLAN_TOOLS`, system prompt `load_prompt("planner")`), `tools` (`run_capped` with `PLAN_CAPS`/`PLAN_TOTAL_CAP`; resets `used` per attempt), `review` (parse → merge → `run_checks` → `verify(...)` if given and no code failures; on failure append a HumanMessage listing the failures, `attempts += 1`; after `MAX_RETRIES` retries `status="failed"`, END), `approve` (`interrupt({"summary", "changes", "warnings", "version"})`; resume value `{"decision": "approve" | "reject" | "revise", "comment": str | None}`; `revise` appends the comment as a HumanMessage, resets `attempts` to 0, goes to `planner`), `save` (`save_program`; `StaleProgramError` → `status="stale"`; success → `status="saved"`, `saved_version`).
    Retrieved IDs for provenance = `chunk_id`s from `search_library` artifacts ∪ `cites` from `get_cycle` artifacts in the current attempt's messages.
  - `src/planner/run.py`: `RunResult` (dataclass: `thread_id`, `status: Literal["awaiting_approval","saved","rejected","failed","stale","needs_profile"]`, `proposal`, `changes: list[Change]`, `failures`, `verifier`, `version`, `trace`); `start(action: Literal["new","roll_forward"], request: str | None = None, llm=None, verify=None, thread_id: str | None = None, today: date | None = None) -> RunResult`; `resume(thread_id: str, decision: str, comment: str | None = None, llm=None, verify=None) -> RunResult`. Default checkpointer `SqliteSaver` at `athlete_dir() / "checkpoints.sqlite"`; tests inject `InMemorySaver` via a module-level `checkpointer()` factory they monkeypatch.
  - `prompts/planner.v2.md` (replaces the v1 stub as latest): role, the two templates as the only source of structure (`get_cycle` first), rolling detail (outline + next 1–2 weeks only), scheduling (place day types on the athlete's available days following the template's pattern and spacing; weekdays in labels are examples; missed sessions are never made up), units (lb / in, keep `%`), citation rules (every session/mesocycle/stage cites; deviations need reason + cite), the exact `Proposal` JSON shape with a short example, "return only JSON", caps, and "if the profile lacks something you need, say so in `summary` with `decision: decline` rather than guessing".

- [ ] **Step 1: Write failing tests** (ScriptedChatModel from `tests/test_graph.py`, synthetic template via the Task 2 fixture, `tmp_path` athlete dir, `InMemorySaver`):
  - `test_new_plan_pauses_for_approval_then_saves_v1` — script: `get_cycle` call, then a valid `new` Proposal; `start("new")` → `awaiting_approval` with non-empty `changes`; `resume(..., "approve")` → `saved`, `version == 1`, file `program/v0001.json` exists
  - `test_reject_saves_nothing`
  - `test_revise_sends_comment_back_to_planner` — the planner's next call contains the comment text; a second proposal is shown
  - `test_check_failure_retries_at_most_twice` — three proposals each citing an unretrieved ID → planner called 3 times, `status == "failed"`, failures reported, no file written
  - `test_malformed_output_counts_as_attempt` — Review Focus 5: fenced JSON with prose parses; a proposal with an extra key yields a `schema` failure fed back, not an exception
  - `test_plan_tool_caps` — 8 searches requested → 6 run, rest error; 13 total calls → 12 run
  - `test_needs_profile_without_calling_model` — Review Focus 2: no profile → `needs_profile`, `model.seen == []`
  - `test_stale_approval_refused` — Review Focus 1: start a proposal on v1, save a v2 out of band, approve → `stale`, no v3
  - `test_context_passes_today` — Review Focus 4: the context message contains `today` and the program's last filled week
  - existing `tests/test_qa.py::test_search_calls_capped_in_code` unchanged and green
- [ ] **Step 2: Run** `uv run pytest tests/test_planner_graph.py -v` — expect FAIL.
- [ ] **Step 3:** `uv add langgraph-checkpoint-sqlite`; extract `run_capped`; implement tools, graph, run API and the prompt.
- [ ] **Step 4: Run** `uv run pytest -q` — expect all pass (Coach tests included).
- [ ] **Step 5: Commit** `"Planner graph: capped tool loop, checks with two retries, interrupt approval, versioned save"`.

---

### Task 7: Router, athlete/developer rendering and the `plan` CLI

**Files:**
- Create: `src/router.py`, `src/planner/render.py`, `scripts/plan.py`
- Modify: `scripts/ask.py` (route program messages to a hint: "use `plan …`")
- Test: `tests/test_router.py`, `tests/test_planner_render.py`

**Interfaces:**
- Consumes: `Program`, `Change`, `RunResult`, `display` (Tasks 1, 4, 6)
- Produces:
  - `route(message: str) -> Literal["program", "coach"]` — whole-word, case-insensitive regex on: `plan`, `program`, `programme`, `schedule`, `this week`, `next week`, `mesocycle`, `macrocycle`, `deload`, `taper` (as a request verb: "taper me", "when should I taper" stays coach — keep the list conservative), `only \d+ days`, `\d+ days a week`, month-name + day dates ("March 1"), `my (dunk )?(contest|event|competition|game) is`.
  - `render_week(program: Program, today: date, full: bool = False) -> str` — header `Month {i} of {n} · {emphasis} · Week {w} of {k}`, one line per training day `Mon  Exercise S×R @ intensity · …` in athlete units; athlete view ends with one `ⓘ sources` line (no IDs); `full=True` adds per-session source links via the chunk metadata (`channel – title @ mm:ss (url)`) and deviations.
  - `render_outline(program: Program, full: bool = False) -> str` — one line per mesocycle (dates, emphasis, goal); tendon stage if any.
  - `render_proposal(result: RunResult, full: bool = False) -> str` — athlete: `What changes:` (≤ 4 lines from `changes`), `Why:` (proposal summary), a single `⚠` line if verifier warnings; full: every change with before/after, failures, verifier items, tokens, trace path.
  - `scripts/plan.py` subcommands: `new`, `next`, `show [--full]`, `profile` (interactive prompts for every `Profile` field in lb / in; `--from-json PATH` alternative), and after `new` / `next` an approve / reject / revise prompt loop calling `resume`. `--full` on any subcommand switches to the developer view.

- [ ] **Step 1: Write failing tests**: `test_route_program_examples` (e.g. "make me a plan", "I can only train 3 days a week now", "my dunk contest is March 1", "what's on this week" → program), `test_route_coach_examples` ("why do eccentrics help", "is static stretching bad", "how long should a taper be?" → coach); `test_render_week_athlete_view_has_no_chunk_ids`, `test_render_week_uses_lb_and_in` (a `kg` intensity shows lb; a `cm` box shows in), `test_render_week_full_has_links`, `test_render_proposal_athlete_is_short` (≤ 8 lines for a 3-change proposal), `test_render_proposal_full_lists_failures`.
- [ ] **Step 2: Run** `uv run pytest tests/test_router.py tests/test_planner_render.py -v` — expect FAIL.
- [ ] **Step 3: Implement** router, render and the CLI.
- [ ] **Step 4: Run** `uv run pytest -q` — expect all pass. Manual: `uv run python -m scripts.plan show` with no program prints "No plan yet — run `plan profile`, then `plan new`."
- [ ] **Step 5: Commit** `"Router, athlete/developer plan views and the plan CLI"`.

---

### Task 8: UI Plan tab and chat routing

**Files:**
- Modify: `ui/app.py`
- Test: `tests/test_structured_qa.py` (extend the AppTest UI test) or new `tests/test_ui_plan.py`

**Interfaces:**
- Consumes: `route`, `start`, `resume`, `render_*`, `load_profile`, `save_profile`, `load_program`
- Produces: two tabs, **Chat** and **Plan**. Plan tab: profile form (fields in lb / in) with Save; buttons **New plan** and **Next weeks**; current plan via `render_outline` + `render_week` (developer checkbox → `full=True`); a pending proposal (thread ID in `st.session_state`) shows `render_proposal` with **Approve / Reject** buttons and a **Revise** text box. Chat tab: messages routed to `program` show "This looks like a plan request — use the Plan tab" plus the Planner action buttons (no silent plan writes from chat).

- [ ] **Step 1: Write failing test** `test_ui_plan_tab_new_plan_flow` with `AppTest`: monkeypatch `src.planner.run.start` / `resume` to return fixed `RunResult`s; click New plan → proposal text shown; click Approve → "Saved as version 1".
- [ ] **Step 2: Run** — expect FAIL.
- [ ] **Step 3: Implement** the tabs.
- [ ] **Step 4: Run** `uv run pytest -q` — expect all pass.
- [ ] **Step 5: Commit** `"UI: Plan tab with profile form, approval buttons and chat routing"`.

---

### Task 9: Verifier (program and answer modes), wired into both routes

**Files:**
- Create: `src/verifier.py`, `prompts/verifier.v2.md`, `src/kb/evidence.py`
- Modify: `src/planner/run.py` (default `verify`), `src/qa.py` (answer check + retries), `scripts/ask.py` (`--no-verify`), `ui/app.py` (show verifier output in developer view)
- Test: `tests/test_verifier.py`

**Interfaces:**
- Consumes: `Change`, `Proposal` (Task 4); `load_chunks`, `retrieval_config`; `get_llm("verifier")`; `load_prompt("verifier")`
- Produces:
  - `chunk_texts(ids: Iterable[str], method: str | None = None) -> dict[str, str]` in `src/kb/evidence.py` (cached load of the configured chunk file).
  - `VerifierItem(path: str, support: Literal["supported","partly","unsupported"], reason: str)`; `VerifierResult(verdict: Literal["pass","fail"], items: list[VerifierItem], phase_rule_ok: bool, summary_matches_diff: bool, addresses_request: bool | None)` (strict).
  - `verify_program(changes: list[Change], proposal: Proposal, evidence: dict[str, str], llm=None) -> VerifierResult` — one LLM call, no tools, fresh context: system = `load_prompt("verifier")`, user = JSON of `{mode: "program", request, summary, changes (with their cites), evidence}`.
  - `verify_answer(question: str, answer: dict, evidence: dict[str, str], llm=None) -> VerifierResult` — same shape, `mode: "answer"`, items are answer points.
  - `verifier_failures(r: VerifierResult) -> list[str]` — reasons for: any `unsupported` item, `phase_rule_ok` false, `summary_matches_diff` false, `addresses_request is False`; `partly` items are returned separately by `verifier_warnings(r) -> list[str]`.
  - Planner: `run.start/resume` default `verify` = `make_program_verifier(llm=None)` returning the Task 6 callable: it collects all cites in the changes, builds evidence with `chunk_texts`, calls `verify_program`, and returns `(verifier_failures(r), verifier_warnings(r), r.model_dump())`.
  - Coach: `answer_question(..., verify: bool = True)`; on verifier failure, rerun the coach graph with the failure reasons appended (at most 2 retries), then return the last answer with `check["verifier"]` and a warning if still failing. `ask.py --no-verify` and the planner/coach tests pass `verify=False` / a stub where they don't test the Verifier.
  - `prompts/verifier.v2.md`: checks support per item using only the evidence, the phase rule (rehab vs healthy-cycle advice), summary vs diff, request addressed (edits / answers); output only the JSON shape above.

- [ ] **Step 1: Write failing tests** (scripted verifier model returning fixed JSON):
  - `test_verifier_failures_and_warnings` — `unsupported` → failure; `partly` → warning only
  - `test_verify_program_sends_only_changes_and_evidence` — the model's input contains the change paths and evidence text but none of the planner's messages
  - `test_planner_retries_on_verifier_failure` — verifier fails once then passes → proposal shown with attempt 2
  - `test_answer_question_retries_then_warns` — verifier fails 3 times → answer returned with a visible warning, coach called 3 times
  - **Planted faults (plumbing):** fixtures for a fabricated ID, an off-template number, a rehab rule in a healthy cycle, and a misdescribing summary — the first two must be caught by **code checks without calling the verifier**; the last two must reach the verifier (assert it was called with them). The real catch rate is measured in Task 10.
- [ ] **Step 2: Run** `uv run pytest tests/test_verifier.py -v` — expect FAIL.
- [ ] **Step 3: Implement** evidence helper, verifier, prompt and the wiring.
- [ ] **Step 4: Run** `uv run pytest -q` — expect all pass.
- [ ] **Step 5: Commit** `"Verifier: fresh-context program and answer checks with retries"`.

---

### Task 10: First real run, planted-fault check with Claude, docs

**Files:**
- Create: `scripts/verifier_faults.py` (builds the 4 planted-fault proposals from a real reviewed template and runs `verify_program`; prints IDs and verdicts only)
- Modify: `README.md` (Planner section: commands, views, data locations, caps, approval), the build plan doc is updated by the user if they want
- Private outputs: program `v0001.json`, traces, `$THP_DATA_DIR/eval/verifier_faults_<date>.json`

- [ ] **Step 1:** Estimate cost (≈ tokens of one `plan new` with 2 templates + searches, plus 4 verifier calls) and **ask the user to approve** before any Claude call.
- [ ] **Step 2:** With the user's real profile (`plan profile`), run `RETRIEVAL_MODE=bm25 uv run python -m scripts.plan new`; show the athlete view to the user; approve or revise per the user.
- [ ] **Step 3:** Run `scripts/verifier_faults.py`; report which of the two verifier-level faults (rehab rule in healthy cycle, misdescribing summary) were caught. If one is missed, adjust `prompts/verifier.v2.md` → `verifier.v3.md` and rerun once.
- [ ] **Step 4:** Update README; run `uv run pytest -q`.
- [ ] **Step 5: Commit** `"First Planner run, verifier planted-fault script, README"` (code and docs only).
- [ ] **Step 6:** Write plan 2 (stages 5–8) from the reviewed templates' gate rules and the user's feedback on the first plan.
