"""Check structured Coach points for citation presence and retrieved-ID provenance.

Render valid IDs as timestamp links. Summary, takeaway and policy safety notes
are exempt; this is not an entailment check.
"""

from __future__ import annotations

import json
import re

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
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    return CoachAnswer.model_validate(json.loads(raw)).model_dump()


def link(chunk: dict) -> str:
    """Markdown source link: channel – title @ timestamp."""
    title = chunk["title"].replace("[", "(").replace("]", ")")
    return f"[{chunk['channel']} – {title} @ {chunk['timestamp']}]({chunk['url_t']})"


def check_citations(answer: dict, retrieved_ids, *, referral=False) -> dict:
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


def render(answer: dict, retrieved: dict[str, dict], check: dict | None = None) -> str:
    parts = [answer["summary"]]
    for point in answer["points"]:
        links = " ".join(link(retrieved[c]) if c in retrieved else f"[⚠ unknown source {c}]"
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
        parts.append("**Sources**\n" + "\n".join(f"{n}. {link(retrieved[c])}" for c, n in numbers.items()))
    text = "\n\n".join(p for p in parts if p)
    if check and not check["passed"]:
        text = f"> ⚠ Some of this answer isn't backed by a retrieved source. Treat it with caution.\n\n{text}"
    return text
