"""Citation check and rendering for coach answers (plain code, no LLM).

The coach cites retrieved chunks inline as [chunk_id] (several as [id1, id2]).
check_citations() fails an answer that cites an ID not retrieved in this run
(fabricated) or makes a claim with no citation at all. A "claim" is any
paragraph or list item of MIN_CLAIM_WORDS+ words, except headings, lead-ins
ending in ":", questions back to the user, and "the library doesn't cover
this" statements. render() turns the markers into
[Channel – Title @ mm:ss](url_t) links for display.
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


def check_citations(answer: str, retrieved_ids) -> dict:
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


def render(answer: str, retrieved: dict[str, dict], check: dict | None = None) -> str:
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
