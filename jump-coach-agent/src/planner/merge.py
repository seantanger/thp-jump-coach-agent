"""Turn a Planner proposal into the next program version, and describe what changed."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from src.planner.schema import Profile, Program, Proposal


class Change(BaseModel):
    path: str
    before: Any
    after: Any


def merge_proposal(current: Program | None, proposal: Proposal, profile: Profile, now: datetime) -> Program:
    """Candidate next version. Nothing is saved here; the stored profile is not touched."""
    if proposal.kind == "new" and proposal.replace_outline is None:
        raise ValueError("a new plan needs an outline (replace_outline)")
    if proposal.kind != "new" and current is None:
        raise ValueError("no current program to change; make a new plan first")
    snapshot = profile.model_copy(deep=True)
    if proposal.profile_changes:
        snapshot = Profile.model_validate({**snapshot.model_dump(), **proposal.profile_changes}, strict=False)

    base = None if proposal.kind == "new" else current.model_copy(deep=True)
    outline = proposal.replace_outline
    weeks = {} if base is None else {w.start: w for w in base.weeks}
    for w in proposal.replace_weeks or []:
        weeks[w.start] = w.model_copy(deep=True)
    return Program(
        version=(current.version if current else 0) + 1,
        based_on=current.version if current else None,
        created_at=now,
        change_summary=proposal.summary,
        profile_snapshot=snapshot,
        macrocycle=(outline.macrocycle if outline else base.macrocycle).model_copy(deep=True),
        mesocycles=[m.model_copy(deep=True) for m in (outline.mesocycles if outline else base.mesocycles)],
        tendon_track=(outline.tendon_track if outline else base.tendon_track),
        weeks=[weeks[k] for k in sorted(weeks)],
    )


def _fields(path: str, old: BaseModel, new: BaseModel, skip: set[str] = frozenset()) -> list[Change]:
    a, b = old.model_dump(mode="json"), new.model_dump(mode="json")
    return [Change(path=f"{path}.{k}", before=a[k], after=b[k]) for k in b if k not in skip and a[k] != b[k]]


def diff_programs(old: Program | None, new: Program) -> list[Change]:
    """Changes from old to new: outline fields, then weeks, days and whole sessions."""
    def dump(x):
        return x.model_dump(mode="json") if x is not None else None

    if old is None:
        changes = [Change(path="macrocycle", before=None, after=dump(new.macrocycle))]
        changes += [Change(path=f"mesocycles[{i}]", before=None, after=dump(m)) for i, m in enumerate(new.mesocycles)]
        if new.tendon_track:
            changes.append(Change(path="tendon_track", before=None, after=dump(new.tendon_track)))
        return changes + [Change(path=f"weeks[{w.start}]", before=None, after=dump(w)) for w in new.weeks]

    changes = _fields("macrocycle", old.macrocycle, new.macrocycle)
    for i in range(max(len(old.mesocycles), len(new.mesocycles))):
        a = old.mesocycles[i] if i < len(old.mesocycles) else None
        b = new.mesocycles[i] if i < len(new.mesocycles) else None
        if a is None or b is None:
            changes.append(Change(path=f"mesocycles[{i}]", before=dump(a), after=dump(b)))
        else:
            changes += _fields(f"mesocycles[{i}]", a, b)
    if dump(old.tendon_track) != dump(new.tendon_track):
        changes.append(Change(path="tendon_track", before=dump(old.tendon_track), after=dump(new.tendon_track)))

    old_weeks, new_weeks = {w.start: w for w in old.weeks}, {w.start: w for w in new.weeks}
    for start in sorted(old_weeks.keys() | new_weeks.keys()):
        a, b, path = old_weeks.get(start), new_weeks.get(start), f"weeks[{start}]"
        if a is None or b is None:
            changes.append(Change(path=path, before=dump(a), after=dump(b)))
            continue
        changes += _fields(path, a, b, skip={"days"})
        old_days, new_days = {d.date: d for d in a.days}, {d.date: d for d in b.days}
        for on in sorted(old_days.keys() | new_days.keys()):
            da, db, dpath = old_days.get(on), new_days.get(on), f"{path}.days[{on}]"
            if da is None or db is None:
                changes.append(Change(path=dpath, before=dump(da), after=dump(db)))
                continue
            changes += _fields(dpath, da, db, skip={"sessions", "date"})
            for i in range(max(len(da.sessions), len(db.sessions))):
                sa = da.sessions[i] if i < len(da.sessions) else None
                sb = db.sessions[i] if i < len(db.sessions) else None
                if dump(sa) != dump(sb):
                    changes.append(Change(path=f"{dpath}.sessions[{i}]", before=dump(sa), after=dump(sb)))
    return changes
