"""唯一一轮D4真实压测，排他创建进度文件，逐样本持久化不重跑。"""
import json
from datetime import date, datetime
from pathlib import Path
from time import perf_counter
from backend.db.session import SessionLocal
from backend.db.models import Client
from backend.services.compliance import redteam_operations


def main():
    output=Path('data/d4_live_once.json')
    with output.open('x',encoding='utf-8') as stream:
        stream.write('{}')
    started=perf_counter()
    with SessionLocal() as db:
        client=Client(name='D4唯一内部压测')
        db.add(client);db.commit()
        ops=redteam_operations(db)
        run_id='rt_'+datetime.now().strftime('%Y%m%d_%H%M%S')
        batch=ops['generator'].generate(['双眼皮'],['efficacy_claim','safety_guarantee','absolute_terms','inducement'])
        ids=ops['repository'].save_samples(run_id,client.id,batch['samples'],batch['usage'])
        progress=dict(run_id=run_id,client_id=client.id,generation=batch,script_ids=ids,judged=[])
        failures=0
        for sample in ops['repository'].samples(run_id):
            result=ops['judge'].judge(sample)
            ops['repository'].save_verdict(sample['id'],result)
            progress['judged'].append(dict(script_id=sample['id'],**result))
            output.write_text(json.dumps(progress,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
            print(f"script_id={sample['id']} verdict={result['verdict']} score={result['score']}",flush=True)
            failures=failures+1 if result['verdict']=='unjudged' else 0
            if failures>3:
                progress['stopped']='consecutive_unjudged_gt3'
                break
        progress['daily']=ops['report'].daily(date.today())
        progress['report']=ops['report'].redteam(run_id)
        progress['wall_time_ms']=int((perf_counter()-started)*1000)
        output.write_text(json.dumps(progress,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
        print(json.dumps(progress,ensure_ascii=False,indent=2,default=str))


if __name__=='__main__':
    main()
