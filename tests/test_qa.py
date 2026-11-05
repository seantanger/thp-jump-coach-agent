"""Q&A agent tests: search_library, search cap, citation check, tracing. Mocks only."""

import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.coach.graph import SEARCH_CAP, build_graph
from src.coach.qa import answer_question
from src.tools import RESULT_FIELDS, search_library
from tests.test_graph import ScriptedChatModel

FILLER = " ".join(f"w{i}" for i in range(20))


def record(cid, words=FILLER, title="Knee Pain Fix", start=95):
    video = cid.split("@")[0]
    return {
        "chunk_id": cid, "video_id": video, "channel_handle": "SynthChannel", "channel_name": "Synth Channel",
        "title": title, "upload_date": "2026-01-01", "start": float(start), "end": start + 60.0,
        "url_t": f"https://www.youtube.com/watch?v={video}&t={start}s", "timestamp": f"{start // 60:02d}:{start % 60:02d}",
        "text": words, "word_count": len(words.split()), "promo_candidate": False, "score": 1.0, "rank": 1,
    }


@pytest.fixture
def fake_search(monkeypatch):
    """Replaces the index with two fixed chunks; records every call."""
    calls = []

    def search(query, k, method, mode):
        calls.append({"query": query, "k": k, "method": method, "mode": mode})
        return [record("vidAAAAAAAA@95#0"), record("vidBBBBBBBB@0#1", start=0)][:k]

    monkeypatch.setattr("src.tools.search", search)
    for var in ("RETRIEVAL_METHOD", "RETRIEVAL_MODE", "RETRIEVAL_K"):
        monkeypatch.delenv(var, raising=False)
    return calls


def search_call(query, i):
    return {"name": "search_library", "args": {"query": query}, "id": f"call_{i}"}


# --- search_library ----------------------------------------------------------------


def test_search_library_output_shape(fake_search, monkeypatch):
    monkeypatch.setenv("RETRIEVAL_MODE", "bm25")
    message = search_library.invoke({**search_call("patellar tendon isometrics", 1), "type": "tool_call"})
    assert isinstance(message, ToolMessage) and message.status == "success"
    assert [list(r) for r in message.artifact] == [list(RESULT_FIELDS)] * 2
    assert json.loads(message.content) == message.artifact  # the model sees the same records as JSON
    assert message.artifact[0] == {
        "chunk_id": "vidAAAAAAAA@95#0", "channel": "Synth Channel", "title": "Knee Pain Fix", "timestamp": "01:35",
        "url_t": "https://www.youtube.com/watch?v=vidAAAAAAAA&t=95s", "promo_candidate": False, "text": FILLER,
    }
    assert fake_search == [{"query": "patellar tendon isometrics", "k": 5, "method": "charsplit_matched",
                            "mode": "bm25"}]  # env defaults, mode overridden


def test_search_library_k_from_env_and_clamped(fake_search, monkeypatch):
    monkeypatch.setenv("RETRIEVAL_K", "1")
    assert len(search_library.invoke({"query": "x"})) and fake_search[-1]["k"] == 1
    search_library.invoke({"query": "x", "k": 50})
    assert fake_search[-1]["k"] == 10


def test_search_library_skips_chunks_under_15_words(monkeypatch):
    short = " ".join(["word"] * 14)
    exact = " ".join(["word"] * 15)
    monkeypatch.setattr("src.tools.search", lambda query, k, method, mode: [
        record("vidAAAAAAAA@0#0", short), record("vidAAAAAAAA@30#1", exact, start=30)])
    message = search_library.invoke({**search_call("x", 1), "type": "tool_call"})
    assert [r["chunk_id"] for r in message.artifact] == ["vidAAAAAAAA@30#1"]


# --- search cap ---------------------------------------------------------------------


def test_search_calls_capped_in_code(fake_search):
    model = ScriptedChatModel(responses=[
        AIMessage("", tool_calls=[search_call(f"q{i}", i) for i in range(3)]),
        AIMessage("", tool_calls=[search_call(f"q{i}", i) for i in range(3, 6)]),
        AIMessage("Done [vidAAAAAAAA@95#0]."),
    ])
    state = build_graph(llm=model).invoke({"messages": [HumanMessage("q")], "search_calls": 0})
    tool_messages = [m for m in state["messages"] if isinstance(m, ToolMessage)]
    assert [c["query"] for c in fake_search] == ["q0", "q1", "q2", "q3"]  # only SEARCH_CAP searches ran
    assert state["search_calls"] == SEARCH_CAP == 4
    assert [m.status for m in tool_messages] == ["success"] * 4 + ["error"] * 2
    assert all("Search limit reached" in m.content and m.artifact is None for m in tool_messages[4:])
    assert state["messages"][-1].content == "Done [vidAAAAAAAA@95#0]."  # the model still gets to answer


def as_result(r):
    """A record as search_library returns it."""
    return {**{k: r[k] for k in RESULT_FIELDS if k in r}, "channel": r["channel_name"]}


RETRIEVED = {"vidAAAAAAAA@95#0": as_result(record("vidAAAAAAAA@95#0")),
             "vidBBBBBBBB@0#1": as_result(record("vidBBBBBBBB@0#1", title="Squats [Part 2]", start=0))}


# --- end to end: answer_question + trace ------------------------------------------------


def test_answer_question_checks_against_this_runs_results(fake_search, tmp_path):
    model = ScriptedChatModel(responses=[
        AIMessage("", tool_calls=[search_call("patellar tendinopathy isometrics", 1)]),
        AIMessage(json.dumps(dict(summary="Restatement", points=[
            dict(text="Use long isometric holds.", cites=["vidAAAAAAAA@95#0"]),
            dict(text="Pair with slow loading.", cites=["notRETRIEVE@1#0"])],
            takeaway=None, safety_note=None, not_covered=False))),
    ])
    result = answer_question("My knee tendon aches", llm=model, trace_dir=tmp_path)
    assert result["queries"] == ["patellar tendinopathy isometrics"]
    assert set(result["retrieved"]) == {"vidAAAAAAAA@95#0", "vidBBBBBBBB@0#1"}
    assert not result["check"]["passed"] and result["check"]["fabricated"] == ["notRETRIEVE@1#0"]
    assert result["rendered"].startswith("> ⚠ Citation check failed")
    assert "[Synth Channel – Knee Pain Fix @ 01:35](" in result["rendered"]

    events = [json.loads(line) for line in result["trace"].read_text().splitlines()]
    assert [e["node"] for e in events] == ["start", "coach", "tools", "coach", "end"]
    assert events[2]["chunk_ids"] == ["vidAAAAAAAA@95#0", "vidBBBBBBBB@0#1"]
    assert events[2]["args"] == {"query": "patellar tendinopathy isometrics"}
    assert all("latency_s" in e for e in events[1:])
    assert events[-1]["check"]["fabricated"] == ["notRETRIEVE@1#0"]
