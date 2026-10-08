#!/usr/bin/env python
"""Repeatable Persian evaluation on synthetic fixtures only.

Default: deterministic gold-tool checks (no network).
Opt-in live: --live --base-url ... --model ... [--case count_all]
AI_EVAL_API_KEY supplies the key; never printed or persisted. Each provider's
report must be manually reviewed against rubrics; keyword matches are NOT a
semantic accuracy score. Run once per model to compare latency and transcripts.
"""
import argparse
import json
import os
from pathlib import Path
import time
from unittest.mock import patch
import ai_agent_test as fixture
from flask import session, g
from school_app import ai_workspace as memory


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--base-url')
    parser.add_argument('--model')
    parser.add_argument('--case')
    parser.add_argument('--output')
    args=parser.parse_args()
    cases=json.loads(Path(__file__).with_name('ai_agent_eval_cases.json').read_text(encoding='utf-8'))
    if args.case: cases=[case for case in cases if case['id']==args.case]
    if not cases: parser.error('Unknown case')
    if args.live and not (args.base_url and args.model): parser.error('--live requires --base-url and --model')
    results=[]
    for case in cases:
        role=case.get('role','admin')
        with fixture.app.test_request_context():
            session.update(role=role,user_id=901,personnel_number='T-7')
            g.ai_workspace=memory.new_workspace()
            try:
                raw=fixture.execute_tool(case['tool'],case['args'],role)
                data=json.loads(raw['content']); check=case.get('check',{})
                ok=not case.get('error')
                if 'key' in check: ok=ok and data[check['key']]==check['equals']
                if 'length' in check: ok=ok and len(data)==check['length']
                if 'first_key' in check: ok=ok and data[0][check['first_key']]==check['first_equals']
                if 'meta_key' in check: ok=ok and raw['meta'][check['meta_key']]==check['meta_equals']
            except Exception as exc:
                ok=type(exc).__name__==case.get('error')
            result={'id':case['id'],'gold_tool_pass':bool(ok),'rubric':case['rubric']}
            if args.live:
                # This fixture database is disposable; explicit --live consents to synthetic evaluation only.
                from school_app import ai_control as control
                from school_app.database import get_db
                with get_db() as conn:
                    policy_state=control.read(conn);policy_state['policy']['agent_remote']=True;control.write(conn,policy_state)
                g.ai_external_consent=True
                config={'configured':True,'provider':'openai','base_url':args.base_url,'model':args.model,'api_key':os.environ.get('AI_EVAL_API_KEY','')}
                start=time.perf_counter()
                try:
                    with patch.object(fixture.AGENT,'_load_provider_config',return_value=config):
                        _,answer,calls=fixture.run_agent(case['query'])
                        result.update(answer=answer,tools=[c['function'] for c in calls])
                        if case.get('followup'):
                            _,follow,calls=fixture.run_agent(case['followup'],[{'role':'user','content':case['query']},{'role':'assistant','content':answer}])
                            result.update(followup_answer=follow,followup_tools=[c['function'] for c in calls])
                    result['requires_human_review']=True
                except Exception as exc:
                    result['provider_error']=str(exc)
                result['seconds']=round(time.perf_counter()-start,3)
            results.append(result)
    output={'mode':'live transcripts: manual rubric review required' if args.live else 'offline deterministic gold tools',
            'model':args.model if args.live else None,'passed':sum(r['gold_tool_pass'] for r in results),
            'total':len(results),'cases':results}
    text=json.dumps(output,ensure_ascii=False,indent=2)
    if args.output: Path(args.output).write_text(text,encoding='utf-8')
    print(text)
    return 0 if all(r['gold_tool_pass'] for r in results) else 1

if __name__=='__main__': raise SystemExit(main())
