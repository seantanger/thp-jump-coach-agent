"""Local independent-question chat, sharing the CLI's answer_question function."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['ANONYMIZED_TELEMETRY'] = 'False'
os.environ['LANGCHAIN_TRACING_V2'] = 'false'
os.environ['LANGSMITH_TRACING'] = 'false'
os.environ['STREAMLIT_SERVER_ADDRESS'] = '127.0.0.1'
os.environ['STREAMLIT_BROWSER_GATHER_USAGE_STATS'] = 'false'

from src.qa import answer_question
from src.llm import model_spec_for, get_llm
from src.tools import retrieval_config


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
        if st.button('Clear chat'):
            st.session_state['chat'] = []
    history = st.session_state.setdefault('chat', [])
    if question := st.chat_input('Ask a jump-training question'):
        if not model.startswith('anthropic:'):
            st.error('This UI uses the Claude API only. Choose an anthropic: model.')
        else:
            try:
                with st.spinner('Searching the library…'):
                    result = answer_question(question, llm=get_llm('coach', model_spec=model),
                                             retrieval=dict(method=method, mode=mode, k=int(k)))
                history.append((question, result))
            except Exception as exc:
                st.error(f'Question failed: {type(exc).__name__}')
    for question, result in history:
        with st.chat_message('user'):
            st.write(question)
        with st.chat_message('assistant'):
            (st.warning if result['referral'] else st.markdown)(result['rendered'])
            check = result['check']
            (st.success if check['passed'] else st.error)('Citation check: ' + ('PASS' if check['passed'] else 'FAIL') +
                                                         (' — ' + '; '.join(check['reasons']) if check['reasons'] else ''))
            with st.expander('Sources'):
                for cid, source in result['retrieved'].items():
                    st.markdown(f"[{source['channel']} – {source['title']} @ {source['timestamp']}]({source['url_t']})")
                    st.write(source['text'][:300])
                    st.caption(f"Cited: {cid in check['cited']} · Promo flag: {source['promo_candidate']}")
            with st.expander('Search queries'):
                for query in result['queries']: st.write(query)
            st.caption(f"{result['latency_s']:.1f}s · Tokens: {result['tokens']}")


if __name__ == '__main__':
    main()
