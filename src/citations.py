"""Check structured Coach points for citation presence and retrieved-ID provenance.

Render valid IDs as timestamp links. Summary, takeaway and policy safety notes
are exempt; this is not an entailment check. Legacy text helpers remain for
historical callers and tests; live Q&A validates CoachAnswer before checking.
"""

from __future__ import annotations

import re

MIN_CLAIM_WORDS = 8

# [ ... ] not followed by "(" (that would be a markdown link)
_MARKER_RE = re.compile(r"\[([^\[\]\n]+)\](?!\()")
_ID_RE = re.compile(r"[\w-]+@[\w.#-]+")
_SPLIT_RE = re.compile(r"\s*[,;]\s*")
_NOT_COVERED_RE = re.compile(
    r"\b(library|chunks?|passages?|sources?|videos?|transcripts?)\b.{0,60}?"
    r"\b(doesn't|don't|does not|do not|didn't|did not)\s+(cover|answer|address|mention|say|discuss)",
    re.IGNORECASE,
)


def _marker_ids(inner: str) -> list[str] | None:
    """IDs in one [ ... ] marker, or None if it isn't a citation marker."""
    parts = [p for p in _SPLIT_RE.split(inner.strip()) if p]
    return parts if parts and all(_ID_RE.fullmatch(p) for p in parts) else None


def cited_ids(answer: str) -> list[str]:
    """Every chunk ID cited in the answer, in first-seen order."""
    seen: dict[str, None] = {}
    for m in _MARKER_RE.finditer(answer):
        for cid in _marker_ids(m[1]) or []:
            seen.setdefault(cid)
    return list(seen)


def _claims(answer: str) -> list[str]:
    """Paragraphs / list items that state something and so need a citation."""
    claims = []
    for line in answer.splitlines():
        text = line.strip()
        if not text or text.startswith("#") or text.endswith((":", "?")):
            continue
        if len(text.split()) < MIN_CLAIM_WORDS or _NOT_COVERED_RE.search(text):
            continue
        claims.append(text)
    return claims


def _legacy_check(answer: str, retrieved_ids) -> dict:
    retrieved = set(retrieved_ids)
    cited = cited_ids(answer)
    fabricated = [cid for cid in cited if cid not in retrieved]
    uncited = [c for c in _claims(answer) if not any(_marker_ids(m) for m in _MARKER_RE.findall(c))]
    not_covered = bool(_NOT_COVERED_RE.search(answer)) and not cited
    reasons = []
    if fabricated:
        reasons.append(f"cites {len(fabricated)} chunk ID(s) not retrieved in this run: {', '.join(fabricated)}")
    if uncited:
        reasons.append(f"{len(uncited)} claim(s) with no citation")
    if not cited and not not_covered and not uncited:
        reasons.append("no citations")
    return {
        "passed": not reasons,
        "cited": cited,
        "fabricated": fabricated,
        "uncited_claims": uncited,
        "not_covered": not_covered,
        "reasons": reasons,
    }


def _link(chunk: dict) -> str:
    title = chunk["title"].replace("[", "(").replace("]", ")")
    return f"[{chunk['channel']} – {title} @ {chunk['timestamp']}]({chunk['url_t']})"


def _legacy_render(answer: str, retrieved: dict[str, dict], check: dict | None = None) -> str:
    """Answer with [chunk_id] markers replaced by source links, plus a warning if the check failed."""

    def replace(m: re.Match) -> str:
        ids = _marker_ids(m[1])
        if ids is None:
            return m[0]
        return " ".join(_link(retrieved[cid]) if cid in retrieved else f"[⚠ unknown source {cid}]" for cid in ids)

    text = _MARKER_RE.sub(replace, answer)
    if check and not check["passed"]:
        text = f"> ⚠ Citation check failed: {'; '.join(check['reasons'])}. Treat this answer with caution.\n\n{text}"
    return text


from pydantic import BaseModel, ConfigDict

class Point(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    text: str
    cites: list[str]

class CoachAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    summary: str
    points: list[Point]
    takeaway: str | None
    safety_note: str | None
    not_covered: bool


def parse_answer(raw: str) -> dict:
    import json
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    return CoachAnswer.model_validate(json.loads(raw)).model_dump()


def check_citations(answer, retrieved_ids, *, referral=False) -> dict:
    # Legacy helper retained for historical traces; live Coach always uses dicts.
    if isinstance(answer, str):
        return _legacy_check(answer, retrieved_ids)
    answer = CoachAnswer.model_validate(answer).model_dump()
    cited = list(dict.fromkeys(cid for p in answer["points"] for cid in p["cites"]))
    fabricated = [cid for cid in cited if cid not in retrieved_ids]
    uncited = [p["text"] for p in answer["points"] if not p["cites"]]
    reasons = []
    if fabricated:
        reasons.append(f"cites {len(fabricated)} chunk ID(s) not retrieved in this run: {', '.join(fabricated)}")
    if uncited:
        reasons.append(f"{len(uncited)} point(s) with no citation")
    if not answer["points"] and not answer["not_covered"] and not referral:
        reasons.append("no points without not_covered or referral")
    return dict(passed=not reasons, cited=cited, fabricated=fabricated,
                uncited_claims=uncited, not_covered=answer["not_covered"], reasons=reasons)


def render(answer, retrieved, check=None) -> str:
    if isinstance(answer, str):
        return _legacy_render(answer, retrieved, check)
    parts = [answer["summary"]]
    for point in answer["points"]:
        links = " ".join(_link(retrieved[c]) if c in retrieved else f"[⚠ unknown source {c}]"
                         for c in point["cites"])
        parts.append(f"- {point['text']} {links}".rstrip())
    if answer.get("takeaway"):
        parts.append(answer["takeaway"])
    if answer.get("safety_note"):
        parts.append(answer["safety_note"])
    text = "\n\n".join(p for p in parts if p)
    if check and not check["passed"]:
        text = f"> ⚠ Citation check failed: {'; '.join(check['reasons'])}. Treat this answer with caution.\n\n{text}"
    return text


def render_compact(answer: dict, retrieved: dict[str, dict], check: dict | None = None) -> str:
    """Athlete view: numbered citations and one sources line per video moment, not a link per claim."""
    numbers: dict[str, int] = {}
    bullets = []
    for point in answer["points"]:
        marks = "".join(f"[{numbers.setdefault(c, len(numbers) + 1)}]" if c in retrieved else "[⚠]"
                        for c in point["cites"])
        bullets.append(f"- {point['text']} {marks}".rstrip())
    parts = [answer["summary"], "\n".join(bullets)]
    if answer.get("takeaway"):
        parts.append(answer["takeaway"])
    if answer.get("safety_note"):
        parts.append(f"*{answer['safety_note']}*")
    if numbers:
        parts.append("**Sources**\n" + "\n".join(f"{n}. {_link(retrieved[c])}" for c, n in numbers.items()))
    text = "\n\n".join(p for p in parts if p)
    if check and not check["passed"]:
        text = f"> ⚠ Some of this answer isn't backed by a retrieved source. Treat it with caution.\n\n{text}"
    return text
