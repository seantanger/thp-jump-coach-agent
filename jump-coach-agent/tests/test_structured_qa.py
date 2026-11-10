import importlib
import json
from pathlib import Path
from unittest.mock import Mock
import pytest
import yaml
from langchain_core.messages import AIMessage
from src.coach.citations import check_citations, render, render_compact
from src.coach.qa import answer_question
from tests.test_graph import ScriptedChatModel
from tests.test_qa import fake_search, search_call, RETRIEVED


def answer(points=None, not_covered=False):
    return dict(summary='Short answer.', points=points or [], takeaway='Practical takeaway.', safety_note=None, not_covered=not_covered)


def test_structured_points():
    data = answer([dict(text='Brief claim', cites=[])])
    assert not check_citations(data, RETRIEVED)['passed']
    data['points'][0]['cites'] = ['invented']
    assert check_citations(data, RETRIEVED)['fabricated'] == ['invented']
    assert check_citations(answer(not_covered=True), RETRIEVED)['passed']
    data['points'][0]['cites'] = ['vidAAAAAAAA@95#0']
    assert check_citations(data, RETRIEVED)['passed']
    assert '[Synth Channel – Knee Pain Fix @ 01:35](https://www.youtube.com/watch?v=vidAAAAAAAA&t=95s)' in render(data, RETRIEVED)


def test_search_required_before_final(fake_search, tmp_path):
    model = ScriptedChatModel(responses=[AIMessage(json.dumps(answer(not_covered=True))),
                                            AIMessage(json.dumps(answer(not_covered=True)))])
    result = answer_question('Question', llm=model, trace_dir=tmp_path)
    assert result['queries'] == ['Question']


def test_import_ui_with_mocked_graph(monkeypatch):
    monkeypatch.setattr('src.coach.qa.build_graph', Mock())
    module = importlib.import_module('ui.app')
    assert callable(module.main)


def test_ui_renders_mocked_graph(monkeypatch, tmp_path):
    testing = pytest.importorskip('streamlit.testing.v1')
    graph = Mock()
    graph.invoke.return_value = {'messages': [AIMessage(json.dumps(answer(not_covered=True)))]}
    monkeypatch.setattr('src.coach.qa.build_graph', Mock(return_value=graph))
    monkeypatch.setattr('src.coach.qa.traces_dir', lambda: tmp_path)
    monkeypatch.setattr('ui.app.get_llm', Mock())
    monkeypatch.setattr('src.llm.get_llm', Mock())
    app = testing.AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'ui/app.py')).run()
    assert not app.exception
    app.chat_input[0].set_value('A synthetic test question').run()
    assert not app.exception
    assert graph.invoke.called
    assert len(app.chat_message) == 2


def test_compact_render_numbers_sources_once():
    data = answer([dict(text='Hold it', cites=['vidAAAAAAAA@95#0']),
                   dict(text='Squat deep', cites=['vidBBBBBBBB@0#1', 'vidAAAAAAAA@95#0'])])
    out = render_compact(data, RETRIEVED, check_citations(data, RETRIEVED))
    assert '- Hold it [1]' in out and '- Squat deep [2][1]' in out
    assert out.count('](https://') == 2  # each source linked once, in the sources list
    assert out.endswith('2. [Synth Channel – Squats (Part 2) @ 00:00](https://www.youtube.com/watch?v=vidBBBBBBBB&t=0s)')
    data['points'][0]['cites'] = ['invented']
    failed = render_compact(data, RETRIEVED, check_citations(data, RETRIEVED))
    assert failed.startswith('> ⚠') and '- Hold it [⚠]' in failed



def test_athlete_chat_sees_plan_and_history_and_answers_without_search(fake_search, tmp_path, monkeypatch):
    monkeypatch.setattr('src.coach.qa.athlete_context', lambda: 'Today: 2026-11-09\nSaved plan: Mon squat 4x10')
    reply = dict(summary='Monday is squat 4x10.', points=[], takeaway=None, safety_note=None, not_covered=False,
                 for_you='Mon: squat 4x10.')
    model = ScriptedChatModel(responses=[AIMessage(json.dumps(reply))])
    past = [('earlier q', {'answer': answer([dict(text='x', cites=['vidAAAAAAAA@95#0'])])})]
    result = answer_question("what's my plan?", llm=model, trace_dir=tmp_path, history=past, athlete=True)
    sent = [m.content for m in model.seen[0][1:]]
    assert sent[0].startswith('Today: 2026-11-09') and sent[1] == 'earlier q' and sent[-1] == "what's my plan?"
    assert result['check']['passed'] and not result['queries'] and result['plan'] is None
    assert 'propose_plan_change' in model.bound_tools


def test_athlete_chat_can_draft_a_plan_change_for_approval(fake_search, tmp_path, monkeypatch):
    from src.planner.run import RunResult
    monkeypatch.setattr('src.coach.qa.athlete_context', lambda: 'ctx')
    draft = RunResult(thread_id='t9', status='awaiting_approval', proposal={'summary': 'Logged.'}, version=2)
    started = Mock(return_value=draft)
    monkeypatch.setattr('src.planner.run.start', started)
    call = {'name': 'propose_plan_change', 'args': {'action': 'edit', 'request': 'I did 135 today'}, 'id': 'p1'}
    reply = dict(summary='Draft ready to review.', points=[], takeaway=None, safety_note=None, not_covered=False,
                 for_you='Wednesday stays as planned.')
    model = ScriptedChatModel(responses=[AIMessage('', tool_calls=[call]), AIMessage(json.dumps(reply))])
    result = answer_question('I did 135 power cleans today', llm=model, trace_dir=tmp_path, athlete=True)
    assert started.call_args.kwargs == {'request': 'I did 135 today'} and started.call_args.args == ('edit',)
    assert result['plan'] is draft and result['check']['passed']
    assert '**For you:** Wednesday stays as planned.' in result['rendered']
