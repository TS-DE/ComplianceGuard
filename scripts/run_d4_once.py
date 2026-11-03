"""D4单轮分批执行；--resume读取原run_id，数据库有verdict的样本永不重判。"""
import argparse
import json
from datetime import date, datetime
from pathlib import Path
from time import perf_counter
from backend.db.session import SessionLocal
from backend.db.models import Client
from backend.services.compliance import redteam_operations


def execute_batches(repository, judge, run_id, batch_size, checkpoint):
    """只执行尚无verdict样本，逐条落库，每批回调并报告耗时。"""
    if batch_size<1: raise ValueError('batch_size must be positive')
    rows=repository.samples(run_id)
    pending=[row for row in rows if not row['meta'].get('verdict')]
    completed=len(rows)-len(pending)
    batches=[]
    for offset in range(0,len(pending),batch_size):
        started=perf_counter()
        for sample in pending[offset:offset+batch_size]:
            result=judge.judge(sample)
            repository.save_verdict(sample['id'],result)
            completed+=1
            checkpoint(sample,result,None)
            if any(c.get('thinking') is False and c.get('reasoning_chars',0)>0 for c in result.get('llm_calls',[])):
                raise RuntimeError('thinking parameter not applied')
        batch=dict(completed=completed,total=len(rows),latency_ms=(perf_counter()-started)*1000)
        batches.append(batch)
        checkpoint(None,None,batch)
        print(f"已完成 {completed}/{len(rows)}，本批耗时 {batch['latency_ms']/1000:.2f}s",flush=True)
    return batches


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch-size',type=int,default=4)
    parser.add_argument('--resume',action='store_true')
    parser.add_argument('--output',default='data/d4_thinking_off_once.json')
    args=parser.parse_args()
    output=Path(args.output)
    progress=json.loads(output.read_text(encoding='utf-8')) if args.resume else dict(judged=[],batches=[])
    if not args.resume:
        with output.open('x',encoding='utf-8') as stream: stream.write('{}')
    started=perf_counter()
    with SessionLocal() as db:
        ops=redteam_operations(db)
        if not args.resume:
            client=Client(name='D4关闭思考单轮');db.add(client);db.commit()
            run_id='rt_'+datetime.now().strftime('%Y%m%d_%H%M%S')
            batch=ops['generator'].generate(['双眼皮'],['efficacy_claim','safety_guarantee','absolute_terms','inducement'])
            ids=ops['repository'].save_samples(run_id,client.id,batch['samples'],batch['usage'])
            progress.update(run_id=run_id,client_id=client.id,generation=batch,script_ids=ids)
        def checkpoint(sample,result,batch):
            if sample: progress['judged'].append(dict(script_id=sample['id'],**result))
            if batch: progress['batches'].append(batch)
            output.write_text(json.dumps(progress,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
        execute_batches(ops['repository'],ops['judge'],progress['run_id'],args.batch_size,checkpoint)
        progress.update(daily=ops['report'].daily(date.today()),report=ops['report'].redteam(progress['run_id']),
                        wall_time_ms=int((perf_counter()-started)*1000))
        output.write_text(json.dumps(progress,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
        print(json.dumps(progress,ensure_ascii=False,indent=2,default=str))


if __name__=='__main__': main()
