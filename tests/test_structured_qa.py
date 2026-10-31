import importlib
import json
from pathlib import Path
from unittest.mock import Mock
import pytest
import yaml
from langchain_core.messages import AIMessage
from src.coach.citations import check_citations, render, render_compact
from src.coach.qa import answer_question
from src.red_flags import SAFETY_NOTE
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


CASES = yaml.safe_load((Path(__file__).parent/'safety_cases.yaml').read_text())['cases']
@pytest.mark.parametrize('case', CASES, ids=[c['prompt'] for c in CASES])
def test_safety_routes(case, fake_search, tmp_path):
    model = ScriptedChatModel(responses=[
        AIMessage('', tool_calls=[search_call('tendon load', 1)]),
        AIMessage(json.dumps(answer([dict(text='Supported point', cites=['vidAAAAAAAA@95#0'])])))])
    result = answer_question(case['prompt'], llm=model, trace_dir=tmp_path)
    if case['route'] == 'coach':
        assert not result['referral'] and result['queries']
        assert result['check']['passed']
    else:
        assert result['referral'] == case['route']
        assert not model.seen and not result['queries'] and not result['answer']['points']


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


@pytest.mark.parametrize('question, expected', [
    ('Why would getting stronger in the lowering phase make me jump higher?', False),
    ('How long should a jump session last? My coach says an hour.', False),
    ('My Achilles has been sore for months.', True),
    ('The tendon under my kneecap aches after jumping.', True),
    ('My ankles are stiff when I squat deep.', True),
    ('I injured my hamstring last week, can I still jump?', True),
])
def test_physio_line_only_for_pain_or_injury(question, expected, fake_search, tmp_path):
    model_answer = answer([dict(text='Supported point', cites=['vidAAAAAAAA@95#0'])])
    model_answer['safety_note'] = 'See a physio if anything hurts.'  # the model's own note is always replaced
    model = ScriptedChatModel(responses=[AIMessage('', tool_calls=[search_call('q', 1)]),
                                         AIMessage(json.dumps(model_answer))])
    result = answer_question(question, llm=model, trace_dir=tmp_path)
    assert result['answer']['safety_note'] == (SAFETY_NOTE if expected else None)
