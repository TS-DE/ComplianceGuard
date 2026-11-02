"""D3 真实模型、真实法规检索和真实 MySQL 验收，不输出配置值。"""
import json
from pathlib import Path
from sqlalchemy import select
from backend.db.session import SessionLocal
from backend.db.models import Client, Script, Audit
from backend.tools.audit_tool import build_audit_tool
from backend.mcp_server.server import audit_recheck


def main():
    case = json.loads(Path('data/cases/case_002.json').read_text(encoding='utf-8'))
    with SessionLocal() as db:
        institution = Client(name='D3真实验收机构', contact='D3 acceptance evidence')
        db.add(institution)
        db.flush()
        script = Script(client_id=institution.id, scene='口腔美白', content=case['violation_quote'])
        db.add(script)
        db.commit()
        tool = build_audit_tool(db)
        result = tool.run_audit(script.id, institution.id)
        payload = dict(case_id=case['case_id'], original=case['violation_quote'], audit=result)
        Path('tests/agents/d3_live.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
        assert not result['incomplete'], result['traces']
        assert {'efficacy_claim','safety_guarantee'} <= {h['axis'] for h in result['hits']}, result
        assert all(case['violation_quote'][h['start']:h['end']] == h['original_quote'] for h in result['hits'])
        rewrite = tool.rewrite_audit(result['audit_id'])
        payload['rewrite'] = rewrite
        payload['mcp_recheck'] = audit_recheck('我们提供口腔咨询服务，请结合个人情况咨询执业医师。', institution.id)
        saved = db.scalar(select(Audit).where(Audit.id == result['audit_id']))
        db.refresh(saved)
        payload['persisted'] = {column.name:getattr(saved,column.name) for column in Audit.__table__.columns}
        Path('tests/agents/d3_live.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
        __import__('sys').stdout.write(json.dumps(payload, ensure_ascii=False, indent=2, default=str)+'\n')


if __name__ == '__main__':
    main()
