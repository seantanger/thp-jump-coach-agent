"""Sequential real-Claude QA. Only numeric/ID results enter the repository."""
from __future__ import annotations
import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

from src.kb.paths import eval_dir, load_chunks
from src.kb.evaluate import load_questions, is_hit
from src.llm import model_spec_for, provider_of
from src.qa import answer_question
from src.tools import retrieval_config


def select_retrieval():
    config = retrieval_config()
    if config['mode'] in ('dense', 'hybrid'):
        try:
            with urlopen(os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434') + '/api/tags', timeout=3) as response:
                response.read()
        except OSError:
            os.environ['RETRIEVAL_MODE'] = 'bm25'
            print('Ollama unreachable: falling back to bm25.', flush=True)
            return True
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input-per-million', type=float, default=2.0, help='USD estimate; override for configured model')
    parser.add_argument('--output-per-million', type=float, default=10.0)
    args = parser.parse_args()
    if provider_of(model_spec_for('coach')) != 'anthropic':
        raise SystemExit('Full QA requires a configured real Claude model.')
    fallback = select_retrieval()
    questions = load_questions(eval_dir() / 'questions.yaml')
    chunks = {c['chunk_id']: c for c in load_chunks(retrieval_config()['method'])}
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    private = eval_dir() / f'qa_answers_{stamp}.md'
    rows = []
    private.write_text('# Private Coach QA answers\n\n')
    output = Path('results'); output.mkdir(exist_ok=True)
    for question in questions:
        t0 = time.perf_counter()
        row = dict(id=question['id'], in_scope=bool(question['gold']))
        try:
            result = answer_question(question['question'])
            check = result['check']
            cited = [chunks[c] for c in check['cited'] if c in chunks]
            retrieved = [chunks[c] for c in result['retrieved'] if c in chunks]
            row.update(error=False, citation_pass=check['passed'], fabricated_count=len(check['fabricated']),
                       cited_gold=any(is_hit(c, question['gold']) for c in cited),
                       retrieved_gold=any(is_hit(c, question['gold']) for c in retrieved),
                       not_covered=check['not_covered'], referral=bool(result['referral']),
                       searches=len(result['queries']), latency_s=result['latency_s'], **result['tokens'])
            gold_links = '\n'.join(f"- https://www.youtube.com/watch?v={g['video_id']}&t={int(g['start'])}s" for g in question['gold'])
            with private.open('a') as f:
                f.write(f"## {question['id']}: {question['question']}\n\n{result['rendered']}\n\n"
                        f"Queries: {json.dumps(result['queries'])}\n\nCheck: {json.dumps(check)}\n\nGold:\n{gold_links}\n\n")
        except Exception as exc:
            row.update(error=True, citation_pass=False, fabricated_count=0, cited_gold=False,
                       retrieved_gold=False, not_covered=False, referral=False, searches=0,
                       latency_s=time.perf_counter()-t0)
            with private.open('a') as f:
                f.write(f"## {question['id']}: {question['question']}\n\nError: {type(exc).__name__}: {exc}\n\n")
        rows.append(row)
        print(f"{row['id']} check={row['citation_pass']} cited_gold={row['cited_gold']} error={row['error']}", flush=True)
        write_results(output, rows, fallback, args)
    print(f'Private answers: {private}', flush=True)


def write_results(output, rows, fallback, args):
    n = len(rows); inside = [r for r in rows if r['in_scope']]; outside = [r for r in rows if not r['in_scope']]
    total_in = sum(r.get('input_tokens', 0) for r in rows)
    total_out = sum(r.get('output_tokens', 0) for r in rows)
    metrics = dict(questions=n, errors=sum(r['error'] for r in rows),
        citation_pass_rate=sum(r['citation_pass'] for r in rows)/n,
        fabricated_id_count=sum(r['fabricated_count'] for r in rows),
        cited_gold_rate=sum(r['cited_gold'] for r in inside)/max(1,len(inside)),
        retrieved_gold_rate=sum(r['retrieved_gold'] for r in inside)/max(1,len(inside)),
        out_of_scope_not_covered=sum(r['not_covered'] for r in outside), out_of_scope_count=len(outside),
        in_scope_not_covered=sum(r['not_covered'] for r in inside), in_scope_count=len(inside),
        referral_count=sum(r['referral'] for r in rows),
        mean_searches=sum(r['searches'] for r in rows)/n, mean_latency_s=sum(r['latency_s'] for r in rows)/n,
        input_tokens=total_in, output_tokens=total_out, total_tokens=total_in+total_out,
        estimated_cost_usd=(total_in*args.input_per_million+total_out*args.output_per_million)/1e6,
        estimate_input_usd_per_million=args.input_per_million, estimate_output_usd_per_million=args.output_per_million,
        bm25_fallback=fallback)
    # IDs, numbers and booleans only: no questions, answer text, queries, or chunk text.
    (output/'qa_eval.json').write_text(json.dumps(dict(metrics=metrics, questions=rows), indent=2)+'\n')
    lines = ['# Coach QA evaluation', '', '| Metric | Value |', '|---|---:|']
    lines += [f'| {key} | {value:.4f} |' if isinstance(value, float) else f'| {key} | {value} |' for key,value in metrics.items()]
    lines += ['', '| ID | Citation pass | Cited gold | Retrieved gold | Not covered | Error |', '|---|---|---|---|---|---|']
    lines += [f"| {r['id']} | {r['citation_pass']} | {r['cited_gold']} | {r['retrieved_gold']} | {r['not_covered']} | {r['error']} |" for r in rows]
    (output/'qa_eval.md').write_text('\n'.join(lines)+'\n')


if __name__ == '__main__':
    main()
