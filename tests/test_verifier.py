"""Verifier: fresh-context checks of program changes and Coach answers, wired into both routes. Stubs only."""

import json
from datetime import timedelta

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src.planner import run
from src.planner.merge import diff_programs, merge_proposal
from src.verifier import VerifierResult, verifier_failures, verifier_warnings, verify_answer, verify_program
from tests.planner_fixtures import C, MON, profile, proposal
from tests.test_graph import ScriptedChatModel
from tests.test_planner_graph import TODAY, athlete, good, scripted  # noqa: F401 (fixture)
from tests.test_qa import fake_search, search_call  # noqa: F401 (fixture)


def result(**kw):
    data = dict(verdict="pass", items=[], phase_rule_ok=True, summary_matches_diff=True, addresses_request=None)
    data.update(kw)
    return VerifierResult(**data)


def item(support, path="weeks[2026-11-02]"):
    return {"path": path, "support": support, "reason": f"{support} by the clip"}


def test_verifier_failures_and_warnings():
    r = result(verdict="fail", items=[item("unsupported"), item("partly", "mesocycles[0]"), item("supported")])
    assert verifier_failures(r) == ["weeks[2026-11-02]: unsupported — unsupported by the clip"]
    assert verifier_warnings(r) == ["mesocycles[0]: partly supported — partly by the clip"]
    assert verifier_failures(result(phase_rule_ok=False))[0].startswith("phase rule")
    assert verifier_failures(result(summary_matches_diff=False))[0].startswith("summary")
    assert verifier_failures(result(addresses_request=False))[0].startswith("request")
    assert verifier_failures(result()) == []


def test_verify_program_sends_only_changes_and_evidence():
    v1 = merge_proposal(None, proposal(), profile(), run.now())
    changes = diff_programs(None, v1)
    model = ScriptedChatModel(responses=[AIMessage("```json\n" + result().model_dump_json() + "\n```")])
    r = verify_program(changes, proposal(), {C: "EVIDENCE TEXT"}, llm=model)
    assert r.verdict == "pass"
    sent = model.seen[0]
    assert len(sent) == 2 and isinstance(sent[0], SystemMessage) and isinstance(sent[1], HumanMessage)
    payload = json.loads(sent[1].content)
    assert payload["mode"] == "program" and payload["evidence"] == {C: "EVIDENCE TEXT"}
    assert [c["path"] for c in payload["changes"]][:2] == ["macrocycle", "mesocycles[0]"]
    assert payload["summary"] == "First two weeks."


def test_verify_answer_payload():
    model = ScriptedChatModel(responses=[AIMessage(result(addresses_request=True).model_dump_json())])
    answer = dict(summary="s", points=[dict(text="p", cites=[C])], takeaway=None, safety_note=None, not_covered=False)
    assert verify_answer("q?", answer, {C: "t"}, llm=model).addresses_request is True
    assert json.loads(model.seen[0][1].content)["mode"] == "answer"


def test_planner_retries_on_verifier_failure(athlete):
    verdicts = iter([(["weeks[2026-11-02]: unsupported — no clip says 5x6"], [], {}), ([], ["partly"], {})])
    model = scripted(good(), good(summary="Fixed."))
    out = run.start("new", llm=model, verify=lambda changes, prop: next(verdicts), today=TODAY)
    assert out.status == "awaiting_approval" and out.proposal["summary"] == "Fixed."
    assert out.verifier["warnings"] == ["partly"]
    assert "unsupported" in model.seen[2][-1].content


class Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, changes, prop):
        self.calls.append((changes, prop))
        return [], [], {}


def test_planted_faults_code_catches_two_verifier_sees_two(athlete):
    fabricated = json.loads(good())
    fabricated["replace_weeks"][0]["days"][0]["sessions"][0]["cites"] = ["fakeFAKEfak@9#0"]
    off_template = json.loads(good())
    off_template["replace_weeks"][0]["days"][0]["sessions"][0]["sets"] = 9
    for planted in (fabricated, off_template):
        recorder = Recorder()
        out = run.start("new", llm=scripted(*[json.dumps(planted)] * 3), verify=recorder, today=TODAY)
        assert out.status == "failed" and recorder.calls == []          # code checks caught it first

    rehab = json.loads(good())
    rehab["replace_weeks"][0]["days"][0]["sessions"][0]["notes"] = "isometrics only, no jumping (tendon phase 1)"
    wrong_summary = good(summary="Small tweak to one session.")
    for planted, needle in ((json.dumps(rehab), "isometrics only"), (wrong_summary, "Small tweak")):
        recorder = Recorder()
        run.start("new", llm=scripted(planted), verify=recorder, today=TODAY)
        changes, prop = recorder.calls[0]
        seen = json.dumps([c.model_dump(mode="json") for c in changes]) + prop.summary
        assert needle in seen                                            # it reached the Verifier


def test_answer_question_retries_then_warns(fake_search, tmp_path, monkeypatch):
    from src.coach.qa import answer_question
    answer = json.dumps(dict(summary="Hold isometrics.", points=[dict(text="Hold 45 s.", cites=["vidAAAAAAAA@95#0"])],
                             takeaway=None, safety_note=None, not_covered=False))
    calls = []

    def failing(question, ans, evidence):
        calls.append(evidence)
        return result(verdict="fail", items=[item("unsupported", "points[0]")])

    monkeypatch.setattr("src.coach.qa.answer_verifier", lambda: failing)
    model = ScriptedChatModel(responses=[AIMessage("", tool_calls=[search_call("isometrics", 1)])]
                              + [AIMessage(answer) for _ in range(3)])   # distinct messages, as a real model returns
    out = answer_question("Do isometrics help?", llm=model, trace_dir=tmp_path)
    assert len(calls) == 3 and len(model.seen) == 4
    assert calls[0] == {"vidAAAAAAAA@95#0": " ".join(f"w{i}" for i in range(20))}
    assert not out["check"]["passed"] and out["check"]["verifier"]["verdict"] == "fail"
    assert out["compact"].startswith("> ⚠")


def test_unreadable_verifier_reply_keeps_the_answer(fake_search, tmp_path, monkeypatch):
    from src.coach.qa import answer_question
    from src.verifier import _parse
    answer = json.dumps(dict(summary="Hold isometrics.", points=[dict(text="Hold 45 s.", cites=["vidAAAAAAAA@95#0"])],
                             takeaway=None, safety_note=None, not_covered=False))
    monkeypatch.setattr("src.coach.qa.answer_verifier", lambda: lambda *a: _parse("Looks fine to me."))
    model = ScriptedChatModel(responses=[AIMessage("", tool_calls=[search_call("isometrics", 1)]), AIMessage(answer)])
    out = answer_question("Do isometrics help?", llm=model, trace_dir=tmp_path)
    assert out["check"]["passed"] and out["answer"]["points"]
    assert "not verified" in out["check"]["verifier_warnings"][0]
