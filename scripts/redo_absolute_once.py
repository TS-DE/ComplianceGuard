"""只重做absolute_terms四条，旧样本/审计不删，组合视图保留其余十二条。"""
import json
from pathlib import Path
from datetime import datetime
from time import perf_counter
from sqlalchemy import select
from backend.db.session import SessionLocal
from backend.db.models import Script
from backend.services.compliance import redteam_operations
from backend.tools.db_tool import RedteamRepository
from scripts.run_d4_once import execute_batches


def main():
    output=Path('data/d4_deterministic_once.json')
    with output.open('x',encoding='utf-8') as stream: stream.write('{}')
    started=perf_counter()
    with SessionLocal() as db:
        ops=redteam_operations(db)
        run_id='rt_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'_absolute_terms'
        batch=ops['generator'].generate(['双眼皮'],['absolute_terms'])
        progress=dict(run_id=run_id,generation=batch,judged=[],batches=[])
        output.write_text(json.dumps(progress,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
        if batch['invalid_samples']:
            raise RuntimeError('invalid_axis_ref; stopping before judgments')
        ids=ops['repository'].save_samples(run_id,9,batch['samples'],batch['usage'])
        progress['script_ids']=ids
        def checkpoint(sample,result,timing):
            if sample: progress['judged'].append(dict(script_id=sample['id'],**result))
            if timing: progress['batches'].append(timing)
            output.write_text(json.dumps(progress,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
        execute_batches(ops['repository'],ops['judge'],run_id,4,checkpoint)
        all_rows=[row for row in ops['repository'].samples('rt_20261103_151028') if row['id'] in range(22,30)]
        all_rows+=ops['repository'].samples('rt_20261103_152505_inducement')+ops['repository'].samples(run_id)
        progress.update(main_view=RedteamRepository.summarize(all_rows),all_samples=all_rows,
                        new_costs=ops['repository'].run_costs(run_id),wall_time_ms=int((perf_counter()-started)*1000))
        output.write_text(json.dumps(progress,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
        print(json.dumps(progress,ensure_ascii=False,indent=2,default=str))


if __name__=='__main__': main()
