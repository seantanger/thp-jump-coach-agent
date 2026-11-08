"""Code checks on a candidate program before anyone sees it (spec §7, checks 2–8).

Checks that concern what a proposal changed (provenance, past dates, fidelity, equipment, spacing)
look only at items that differ from the previous version, so rolling forward never fails on
last week's dates or last run's citations.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel

from src.planner.merge import diff_programs
from src.planner.schema import WEEKDAYS, Day, GateResult, Profile, Program, Week, cites_in
from src.planner.templates import Cycle, Range, Scheduling, Template, find_option, find_prescription
from src.units import ATHLETE_UNIT, Quantity, convert

FIDELITY_TOLERANCE = {"in": 0.5, "lb": 5.0, "%": 1.0}
MAX_SWAPS_PER_WEEK = 2  # distinct exercises per week that are not in the template (the variety knob)


class CheckFailure(BaseModel):
    check: Literal["schema", "provenance", "coverage", "fidelity", "calendar", "week_kinds", "gates", "equipment"]
    path: str
    reason: str


def _fail(check: str, path: str, reason: str) -> CheckFailure:
    return CheckFailure(check=check, path=path, reason=reason)


def _changed_weeks(candidate: Program, previous: Program | None) -> list[Week]:
    if previous is None:
        return list(candidate.weeks)
    old = {w.start: w.model_dump(mode="json") for w in previous.weeks}
    return [w for w in candidate.weeks if old.get(w.start) != w.model_dump(mode="json")]


class _Context:
    """Which template and cycle a day belongs to: the tendon stage if it defines the day type, else the mesocycle."""

    def __init__(self, candidate: Program, templates: dict[str, Template]):
        self.macro = templates[candidate.macrocycle.template_id]
        self.tendon = templates.get(candidate.tendon_track.template_id) if candidate.tendon_track else None
        self.stage = next((c for c in self.tendon.cycles if c.id == candidate.tendon_track.stage_id), None) \
            if self.tendon else None
        self.candidate = candidate

    def for_day(self, week: Week, day: Day) -> tuple[Template, Cycle | None]:
        if self.stage and any(d.id == day.day_type for d in self.stage.day_types):
            return self.tendon, self.stage
        meso = self.candidate.mesocycles[week.mesocycle_index] if week.mesocycle_index < len(
            self.candidate.mesocycles) else None
        cycle = next((c for c in self.macro.cycles if meso and c.id == meso.cycle_id), None)
        return self.macro, cycle

    def scheduling(self, week: Week, day: Day) -> Scheduling:
        return self.for_day(week, day)[0].scheduling


def _session_paths(weeks: list[Week]):
    for w in weeks:
        for d in w.days:
            for i, s in enumerate(d.sessions):
                yield w, d, s, f"weeks[{w.start}].days[{d.date}].sessions[{i}]"


def _provenance(candidate, previous, retrieved_ids) -> list[CheckFailure]:
    failures = []
    for change in diff_programs(previous, candidate):
        unknown = sorted(cites_in(change.after) - retrieved_ids)
        if unknown:
            failures.append(_fail("provenance", change.path, f"cites not retrieved this run: {', '.join(unknown)}"))
    return failures


def _coverage(candidate, weeks) -> list[CheckFailure]:
    failures = []
    parts = [("macrocycle", candidate.macrocycle)] + [(f"mesocycles[{i}]", m) for i, m in enumerate(candidate.mesocycles)]
    if candidate.tendon_track:
        parts.append(("tendon_track", candidate.tendon_track))
    failures += [_fail("coverage", path, "no citation") for path, obj in parts if not obj.cites]
    for _, _, s, path in _session_paths(weeks):
        if not s.cites:
            failures.append(_fail("coverage", path, f"{s.exercise}: no citation"))
        dev = s.deviation
        if dev and (not dev.reason.strip() or not (dev.cites or dev.requested_by_user)):
            failures.append(_fail("coverage", path, f"{s.exercise}: a deviation needs a reason and a cite"))
    return failures


def _in_athlete_units(r: Range, unit: str | None) -> tuple[float, float, str | None]:
    if r.unit is None:
        return r.min, r.max, None
    target = ATHLETE_UNIT.get(r.unit, r.unit)
    return (convert(Quantity(value=r.min, unit=r.unit), target).value,
            convert(Quantity(value=r.max, unit=r.unit), target).value, target)


def _outside(value: float, low: float, high: float, tolerance: float) -> bool:
    return value < low - tolerance or value > high + tolerance


def _fidelity(ctx: _Context, weeks) -> list[CheckFailure]:
    failures, swaps = [], {}
    for w, d, s, path in _session_paths(weeks):
        template, cycle = ctx.for_day(w, d)
        if s.deviation:
            if not s.deviation.requested_by_user and (find_prescription(
                    template, cycle.id, d.day_type, s.exercise) if cycle else None) is None:
                swaps.setdefault(w.start, set()).add(" ".join(s.exercise.lower().split()))
            continue
        p = find_prescription(template, cycle.id, d.day_type, s.exercise) if cycle else None
        if p is None:
            failures.append(_fail("fidelity", path, f"{s.exercise} is not in {template.id} "
                                  f"{cycle.id if cycle else '?'} / {d.day_type}; add a deviation"))
            continue
        problems = []
        for name, value, r in (("sets", s.sets, p.sets), ("reps", s.reps, p.reps)):
            if value is not None and r is not None and _outside(value, r.min, r.max, 0):
                problems.append(f"{name} {value} outside {r.min:g}-{r.max:g}")
        if s.intensity is not None and p.intensity is not None:
            low, high, unit = _in_athlete_units(p.intensity, s.intensity.unit)
            mine = convert(s.intensity, ATHLETE_UNIT.get(s.intensity.unit, s.intensity.unit))
            if unit is not None and unit != mine.unit:
                problems.append(f"intensity in {mine.unit}, template in {p.intensity.unit}")
            elif _outside(mine.value, low, high, FIDELITY_TOLERANCE.get(mine.unit, 0)):
                problems.append(f"intensity {mine.value:g} {mine.unit} outside {low:.1f}-{high:.1f}")
        if problems:
            failures.append(_fail("fidelity", path, f"{s.exercise}: {'; '.join(problems)}; add a deviation"))
    failures += [_fail("fidelity", f"weeks[{start}]", f"{len(names)} swapped exercises ({', '.join(sorted(names))}); "
                       f"at most {MAX_SWAPS_PER_WEEK} per week") for start, names in swaps.items()
                 if len(names) > MAX_SWAPS_PER_WEEK]
    return failures


def _calendar(ctx: _Context, candidate, weeks, profile: Profile, today: date) -> list[CheckFailure]:
    failures = []
    mesos = candidate.mesocycles
    for a, b in zip(mesos, mesos[1:]):
        if b.start != a.end + timedelta(days=1):
            failures.append(_fail("calendar", f"mesocycles[{b.index}]",
                                  f"starts {b.start}, but mesocycle {a.index} ends {a.end} (gap or overlap)"))
    changed = {w.start for w in weeks}
    for w in candidate.weeks:
        path = f"weeks[{w.start}]"
        meso = mesos[w.mesocycle_index] if w.mesocycle_index < len(mesos) else None
        # Tendon days with no hard work (isometrics, rest) run daily by design; they aren't training days.
        light = {d.date for d in w.days if ctx.for_day(w, d)[0] is ctx.tendon
                 and d.day_type not in ctx.tendon.scheduling.hard_day_types}
        training = len(w.days) - len(light)
        if w.start in changed and training > profile.days_per_week:
            failures.append(_fail("calendar", path, f"{training} training days > {profile.days_per_week} per week"))
        for d in w.days:
            dpath = f"{path}.days[{d.date}]"
            if not w.start <= d.date <= w.start + timedelta(days=6):
                failures.append(_fail("calendar", dpath, "day outside its week"))
            if meso is None or not meso.start <= d.date <= meso.end:
                failures.append(_fail("calendar", dpath, "day outside its mesocycle"))
            if w.start in changed and d.date < today:
                failures.append(_fail("calendar", dpath, f"scheduled in the past (today is {today})"))
            if w.start in changed and d.date not in light and WEEKDAYS[d.date.weekday()] not in profile.available_days:
                failures.append(_fail("calendar", dpath, f"{WEEKDAYS[d.date.weekday()]} is not an available day"))
    failures += _spacing(ctx, candidate, changed)
    failures += _event(ctx, candidate)
    return failures


def _spacing(ctx: _Context, candidate, changed: set[date]) -> list[CheckFailure]:
    failures, previous = [], None
    days = sorted(((w, d) for w in candidate.weeks for d in w.days), key=lambda wd: wd[1].date)
    for w, d in days:
        sched = ctx.scheduling(w, d)
        if d.day_type not in sched.hard_day_types:
            continue
        if previous is not None:
            pw, pd = previous
            gap = (d.date - pd.date).days
            allowed = [pd.day_type, d.day_type] in sched.allowed_back_to_back
            if gap < sched.min_days_between_hard and not allowed and (w.start in changed or pw.start in changed):
                failures.append(_fail("calendar", f"weeks[{w.start}].days[{d.date}]",
                                      f"hard days {pd.date} ({pd.day_type}) and {d.date} ({d.day_type}) are "
                                      f"{gap} day(s) apart; min_days_between_hard is {sched.min_days_between_hard}"))
        previous = (w, d)
    return failures


def _event(ctx: _Context, candidate) -> list[CheckFailure]:
    event, end = candidate.macrocycle.event_date, ctx.macro.end
    if event is None or end is None:
        return []
    failures = []
    if candidate.mesocycles and candidate.mesocycles[-1].end != event:
        failures.append(_fail("calendar", "mesocycles", f"the last mesocycle ends {candidate.mesocycles[-1].end}, "
                              f"not on the event ({event})"))
    loading_days = (event - timedelta(days=int(end.days.min)) - candidate.macrocycle.start).days
    if loading_days < end.min_loading_weeks * 7:
        failures.append(_fail("calendar", "macrocycle", f"only {loading_days // 7} loading weeks before the "
                              f"{end.kind}; the template needs {end.min_loading_weeks}"))
    taper_from = event - timedelta(days=int(end.days.max))
    for w in candidate.weeks:
        if w.start >= taper_from and w.start <= event and w.kind != end.kind:
            failures.append(_fail("calendar", f"weeks[{w.start}]", f"inside the {int(end.days.max)}-day "
                                  f"{end.kind} before {event} but kind is {w.kind}"))
    return failures


def _week_kinds(ctx: _Context, weeks) -> list[CheckFailure]:
    failures = []
    for w in weeks:
        kind = ctx.macro.week_kinds.get(w.kind)
        if kind is None:
            failures.append(_fail("week_kinds", f"weeks[{w.start}]", f"template has no {w.kind} week"))
        elif _outside(w.volume_modifier, kind.volume.min, kind.volume.max, 0):
            failures.append(_fail("week_kinds", f"weeks[{w.start}]", f"{w.kind} volume {w.volume_modifier:g} outside "
                                  f"{kind.volume.min:g}-{kind.volume.max:g}"))
    return failures


def _gates(ctx: _Context, candidate, weeks, gates: list[GateResult]) -> list[CheckFailure]:
    failures = []
    track = candidate.tendon_track
    if track is None:
        return failures
    if ctx.tendon is None:
        return [_fail("gates", "tendon_track.template_id", f"{track.template_id} is not a reviewed template")]
    if ctx.stage is None:
        return [_fail("gates", "tendon_track.stage_id", f"{track.stage_id} is not a stage of {track.template_id}")]
    order = [c.id for c in ctx.tendon.cycles]
    stage = candidate.tendon_track.stage_id
    for g in gates:
        current = g.inputs.get("stage_id")
        if g.track != "tendon" or current not in order:
            continue
        i = order.index(current)
        allowed = {"hold": {current}, "step_back": {order[max(i - 1, 0)]},
                   "progress": {current, *order[i + 1:i + 2]}, "unload": {current}}.get(g.decision, set(order))
        if stage not in allowed:
            failures.append(_fail("gates", "tendon_track.stage_id", f"gate {g.rule_id} said {g.decision} from "
                                  f"{current}; the plan moves to {stage}"))
    if ctx.stage.allowed_jumping is None:  # the template sets no limit for this stage
        return failures
    # The reviewed template's list, never the Planner's own tendon_track.allowed_jumping.
    elastic = {e.lower() for e in ctx.tendon.elastic_exercises}
    allowed_jumps = {e.lower() for e in ctx.stage.allowed_jumping}
    for _, _, s, path in _session_paths(weeks):
        name = " ".join(s.exercise.lower().split())
        if name in elastic and name not in allowed_jumps:
            failures.append(_fail("gates", path, f"{s.exercise} is not allowed in tendon stage {stage}"))
    return failures


def _equipment(ctx: _Context, weeks, profile: Profile) -> list[CheckFailure]:
    failures, have = [], {e.lower() for e in profile.equipment}
    for w, d, s, path in _session_paths(weeks):
        template, cycle = ctx.for_day(w, d)
        p = find_prescription(template, cycle.id, d.day_type, s.exercise) if cycle else None
        option = find_option(p, s.exercise) if p else None
        needed = option.equipment if option else p.equipment if p else (s.deviation.equipment if s.deviation else [])
        missing = sorted(e for e in needed if e.lower() not in have)
        if missing:
            failures.append(_fail("equipment", path, f"{s.exercise} needs {', '.join(missing)}"))
    return failures


def run_checks(candidate: Program, *, profile: Profile, templates: dict[str, Template], retrieved_ids: set[str],
               gates: list[GateResult], today: date, previous: Program | None = None) -> list[CheckFailure]:
    """All failures of checks 2–8, in order; [] means the candidate passes."""
    ctx = _Context(candidate, templates)
    weeks = _changed_weeks(candidate, previous)
    return (_provenance(candidate, previous, retrieved_ids) + _coverage(candidate, weeks)
            + _fidelity(ctx, weeks) + _calendar(ctx, candidate, weeks, profile, today)
            + _week_kinds(ctx, weeks) + _gates(ctx, candidate, weeks, gates) + _equipment(ctx, weeks, profile))
