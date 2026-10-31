"""Local app: Chat (independent questions, shared with ask.py) and Plan (the Planner, shared with plan.py)."""
import os
import sys
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['ANONYMIZED_TELEMETRY'] = 'False'
os.environ['LANGCHAIN_TRACING_V2'] = 'false'
os.environ['LANGSMITH_TRACING'] = 'false'
os.environ['STREAMLIT_SERVER_ADDRESS'] = '127.0.0.1'
os.environ['STREAMLIT_BROWSER_GATHER_USAGE_STATS'] = 'false'

from src.coach import qa
from src.llm import model_spec_for, get_llm
from src.planner import run, store
from src.planner.render import render_outline, render_proposal, render_week
from src.planner.schema import Profile
from src.router import route
from src.tools import retrieval_config, retrieval_settings

WEEKDAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
PLAN_HINT = 'This looks like a plan request — use the Plan tab to make or change your plan.'


def chat_tab(st, developer, model, retrieval):
    history = st.session_state.setdefault('chat', [])
    if question := st.chat_input('Ask a jump-training question'):
        if route(question) == 'program':
            history.append((question, {'routed': 'program'}))
        elif not model.startswith('anthropic:'):
            st.error('This UI uses the Claude API only. Choose an anthropic: model.')
        else:
            try:
                with st.spinner('Searching the library…'):
                    result = qa.answer_question(question, llm=get_llm('coach', model_spec=model), retrieval=retrieval)
                history.append((question, result))
            except Exception as exc:
                st.error(f'Question failed: {type(exc).__name__}')
    for question, result in history:
        with st.chat_message('user'):
            st.write(question)
        with st.chat_message('assistant'):
            if result.get('routed') == 'program':
                st.info(PLAN_HINT)
                continue
            body = result['rendered'] if developer else result.get('compact', result['rendered'])
            (st.warning if result['referral'] else st.markdown)(body)
            check = result['check']
            if not developer:
                continue
            (st.success if check['passed'] else st.error)('Citation check: ' + ('PASS' if check['passed'] else 'FAIL') +
                                                         (' — ' + '; '.join(check['reasons']) if check['reasons'] else ''))
            if check.get('verifier'):
                st.caption('Verifier: ' + check['verifier']['verdict'] +
                           ''.join(f" · {w}" for w in check.get('verifier_warnings', [])))
            with st.expander('Sources'):
                for cid, source in result['retrieved'].items():
                    st.markdown(f"[{source['channel']} – {source['title']} @ {source['timestamp']}]({source['url_t']})")
                    st.write(source['text'][:300])
                    st.caption(f"Cited: {cid in check['cited']} · Promo flag: {source['promo_candidate']}")
            with st.expander('Search queries'):
                for query in result['queries']: st.write(query)
            st.caption(f"{result['latency_s']:.1f}s · Tokens: {result['tokens']}")


def profile_form(st):
    p = store.load_profile()
    d = p.model_dump(mode='json') if p else {}
    with st.expander('Profile', expanded=p is None), st.form('profile'):
        lifts = d.get('lifts', {})
        squat = st.number_input('Back squat max (lb)', 0.0, 1000.0, float(lifts.get('back_squat_lb', 0.0)))
        clean = st.number_input('Power clean max (lb)', 0.0, 600.0, float(lifts.get('power_clean_lb', 0.0)))
        standing = st.number_input('Standing vertical (in)', 0.0, 60.0, float(d.get('standing_vertical_in') or 0.0))
        approach = st.number_input('Approach vertical (in)', 0.0, 60.0, float(d.get('approach_vertical_in') or 0.0))
        days = st.multiselect('Available days', WEEKDAYS, d.get('available_days', ['mon', 'wed', 'fri']))
        per_week = st.number_input('Training days per week', 1, 7, int(d.get('days_per_week', 3)))
        minutes = st.number_input('Minutes per session', 20, 240, int(d.get('session_minutes', 90)))
        equipment = st.text_input('Equipment (comma separated)', ', '.join(d.get('equipment', ['barbell', 'rack', 'box'])))
        years = st.number_input('Years of serious training', 0.0, 30.0, float(d.get('training_age_years', 1.0)))
        event = d.get('event') or {}
        has_event = st.checkbox('I have an event date', bool(event))
        event_date = st.date_input('Event date', date.fromisoformat(event['date']) if event else date.today())
        goal = st.text_input('Goal', d.get('goal', 'jump higher'))
        if st.form_submit_button('Save profile'):
            store.save_profile(Profile.model_validate({
                'training_age_years': years,
                'lifts': {k: v for k, v in (('back_squat_lb', squat), ('power_clean_lb', clean)) if v},
                'standing_vertical_in': standing or None, 'approach_vertical_in': approach or None,
                'standing_reach_in': d.get('standing_reach_in'), 'height_in': d.get('height_in'),
                'days_per_week': int(per_week), 'available_days': days, 'session_minutes': int(minutes),
                'equipment': [e.strip() for e in equipment.split(',') if e.strip()],
                'event': {'date': event_date.isoformat(), 'name': event.get('name', 'event')} if has_event else None,
                'goal': goal, 'knee_pain': d.get('knee_pain'), 'injury_notes': d.get('injury_notes', ''),
            }, strict=False))
            st.success('Profile saved.')


def plan_tab(st, developer, retrieval):
    profile_form(st)
    left, right = st.columns(2)
    action = None
    if left.button('New plan', key='plan_new'):
        action = 'new'
    if right.button('Next weeks', key='plan_next'):
        action = 'roll_forward'
    if action:
        with st.spinner('Planning…'), retrieval_settings(retrieval):
            st.session_state['plan_pending'] = run.start(action)

    result = st.session_state.get('plan_pending')
    if result is not None and result.status == 'awaiting_approval':
        st.text(render_proposal(result, full=developer))
        a, r = st.columns(2)
        decision, comment = None, None
        if a.button('Approve', key='plan_approve'):
            decision = 'approve'
        if r.button('Reject', key='plan_reject'):
            decision = 'reject'
        revise = st.text_input('Ask for changes', key='plan_revise_text')
        if st.button('Revise', key='plan_revise') and revise:
            decision, comment = 'revise', revise
        if decision:
            with st.spinner('Working…'), retrieval_settings(retrieval):
                result = run.resume(result.thread_id, decision, comment=comment)
            st.session_state['plan_pending'] = result
            if result.status == 'awaiting_approval':
                st.rerun()
    if result is not None and result.status != 'awaiting_approval':
        (st.success if result.status == 'saved' else st.warning)(render_proposal(result, full=developer))

    program = store.load_program()
    if program is not None:
        st.subheader('Your plan')
        sources = None
        if developer:
            from src.kb.evidence import chunk_meta
            sources = chunk_meta({c for w in program.weeks for d in w.days for s in d.sessions for c in s.cites})
        st.text(render_outline(program, full=developer))
        st.text(render_week(program, date.today(), full=developer, sources=sources))


def main():
    import streamlit as st
    st.set_page_config(page_title='Jump Coach', page_icon='🏀')
    st.title('Jump Coach')
    defaults = retrieval_config()
    with st.sidebar:
        method = st.selectbox('Retrieval method', ['charsplit_matched', 'timewindow', 'charsplit_350'],
                              index=['charsplit_matched', 'timewindow', 'charsplit_350'].index(defaults['method']))
        mode = st.selectbox('Retrieval mode', ['dense', 'bm25', 'hybrid'], index=['dense','bm25','hybrid'].index(defaults['mode']))
        k = st.number_input('k', 1, 10, min(10, max(1, defaults['k'])))
        model = st.text_input('Coach model', model_spec_for('coach'))
        developer = st.checkbox('Developer view', help='Full source links, checks, queries and tokens')
        if st.button('Clear chat'):
            st.session_state['chat'] = []
    retrieval = dict(method=method, mode=mode, k=int(k))
    chat, plan = st.tabs(['Chat', 'Plan'])
    with chat:
        chat_tab(st, developer, model, retrieval)
    with plan:
        plan_tab(st, developer, retrieval)


if __name__ == '__main__':
    main()
