"""Fresh-context Verifier (spec §7): does each changed item / answer point follow from its cited evidence?

One LLM call, no tools, no access to the Planner's or Coach's conversation: it sees only the changes or the
answer, the athlete's request, and the cited chunk text.
"""

from __future__ import annotations

import json
import re
from typing import Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict

from src.llm import get_llm
from src.planner.merge import Change
from src.planner.schema import Proposal, cites_in
from src.prompts import load_prompt


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class VerifierItem(_Strict):
    path: str
    support: Literal["supported", "partly", "unsupported"]
    reason: str


class VerifierResult(_Strict):
    verdict: Literal["pass", "fail"]
    items: list[VerifierItem]
    phase_rule_ok: bool
    summary_matches_diff: bool
    addresses_request: bool | None


def _parse(raw: str) -> VerifierResult:
    text = re.sub(r"```(?:json)?", "", raw)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise ValueError("no JSON object in the Verifier output")
    return VerifierResult.model_validate_json(text[start:end + 1])


def _ask(payload: dict, llm: BaseChatModel | None) -> VerifierResult:
    llm = llm or get_llm("verifier")
    response = llm.invoke([SystemMessage(load_prompt("verifier")), HumanMessage(json.dumps(payload, default=str))])
    return _parse(response.text)


def verify_program(changes: list[Change], proposal: Proposal, evidence: dict[str, str],
                   llm: BaseChatModel | None = None) -> VerifierResult:
    payload = {"mode": "program", "request": proposal.request, "summary": proposal.summary,
               "reasons": [r.model_dump() for r in proposal.reasons],
               "changes": [{"path": c.path, "before": c.before, "after": c.after,
                            "cites": sorted(cites_in(c.after))} for c in changes],
               "evidence": evidence}
    return _ask(payload, llm)


def verify_answer(question: str, answer: dict, evidence: dict[str, str],
                  llm: BaseChatModel | None = None) -> VerifierResult:
    return _ask({"mode": "answer", "question": question, "answer": answer, "evidence": evidence}, llm)


def verifier_failures(r: VerifierResult) -> list[str]:
    failures = [f"{i.path}: unsupported — {i.reason}" for i in r.items if i.support == "unsupported"]
    if not r.phase_rule_ok:
        failures.append("phase rule: rehab and healthy-cycle advice are mixed")
    if not r.summary_matches_diff:
        failures.append("summary: does not describe the actual changes")
    if r.addresses_request is False:
        failures.append("request: the direct answer to the athlete's request is missing")
    return failures


def verifier_warnings(r: VerifierResult) -> list[str]:
    return [f"{i.path}: partly supported — {i.reason}" for i in r.items if i.support == "partly"]


def make_program_verifier(llm: BaseChatModel | None = None):
    """The Planner graph's `verify` callable: (changes, proposal) -> (failures, warnings, raw result)."""
    from src.kb.evidence import chunk_texts

    def verify(changes: list[Change], proposal: Proposal):
        cites = set().union(*(cites_in(c.after) for c in changes), *(set(r.cites) for r in proposal.reasons))
        try:
            r = verify_program(changes, proposal, chunk_texts(cites), llm=llm)
        except (ValueError, TypeError) as exc:
            return [], [f"Verifier output could not be read ({type(exc).__name__}); not verified"], None
        return verifier_failures(r), verifier_warnings(r), r.model_dump()

    return verify
