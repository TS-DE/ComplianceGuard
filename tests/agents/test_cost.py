"""成本与迁移契约；所有模型边界均为本地 stub。"""
from decimal import Decimal
import pytest


def test_migration_preview_apply_skip():
    from scripts.migrate_audits_cost_nullable import migrate
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, statement): self.sql.append(str(statement))
        sql = []
    class Engine:
        def begin(self): return Connection()
    class Inspector:
        nullable = False
        def get_columns(self, table): return [dict(name='cost', nullable=self.nullable)]
    inspector = Inspector()
    output = []
    assert migrate(Engine(), inspector, emit=output.append) == 'preview'
    assert Connection.sql == []
    assert migrate(Engine(), inspector, apply=True, emit=output.append) == 'applied'
    assert 'DECIMAL(10,6) NULL DEFAULT NULL' in Connection.sql[0]
    inspector.nullable = True
    assert migrate(Engine(), inspector, apply=True, emit=output.append) == 'skipped'
    assert len(Connection.sql) == 1


def test_exact_cost():
    from backend.core.constants import compute_cost
    assert compute_cost(1000, 2000, '0.8', '2.7') == Decimal('0.006200')


@pytest.mark.parametrize('price_in,price_out', [(None,'2.7'),('0.8',None),(None,None)])
def test_missing_price_unknown(price_in, price_out):
    from backend.core.constants import compute_cost
    assert compute_cost(1000, 2000, price_in, price_out) is None


@pytest.mark.parametrize('value', ['-1','NaN','Infinity'])
def test_invalid_prices(value):
    from backend.core.constants import compute_cost
    with pytest.raises(ValueError): compute_cost(1, 1, value, '1')


def test_null_cost_persisted(db):
    from backend.db.models import Client, Script, Audit
    from backend.crud.audit import AuditRepository
    client = Client(name='NULL计价')
    db.add(client)
    db.flush()
    script = Script(client_id=client.id, content='介绍服务')
    db.add(script)
    db.commit()
    result = dict(score=2, incomplete=False, hits=[], hit_count=0, law_refs=[],
                  model=None, prompt_tokens=0, completion_tokens=0, cost=None, latency_ms=1)
    audit_id = AuditRepository(db).save(script.id, result)
    db.expire_all()
    assert db.get(Audit, audit_id).cost is None



def test_price_precedence_and_unknown_propagation(monkeypatch):
    from backend.tools import audit_tool
    monkeypatch.setattr(audit_tool, 'MODEL_PRICES', {'stub': {'in': '1', 'out': '2'}})
    response = lambda *a: dict(choices=[dict(message=dict(content='{"hits":[]}'))],
                               usage=dict(prompt_tokens=1000, completion_tokens=1000))
    monkeypatch.setattr(audit_tool, 'llm_config', lambda: {'JUDGE_MODEL':'stub', 'JUDGE_INPUT_PRICE_PER_M':'3'})
    assert audit_tool.UrllibChatModel(response).complete([])['cost'] == Decimal('0.005000')
    monkeypatch.setattr(audit_tool, 'llm_config', lambda: {'JUDGE_MODEL':'unknown'})
    assert audit_tool.UrllibChatModel(response).complete([])['cost'] is None



def test_known_docs_injected_from_local_index(monkeypatch):
    from backend.tools import audit_tool
    monkeypatch.setattr(audit_tool, 'indexed_docs', lambda: {'广告法'})
    class Repo:
        def load_rules(self): return []
    tool = audit_tool.AuditTool(Repo(), model=object())
    assert tool.auditor.known_docs == {'广告法'}


def test_pipeline_uses_normalize_with_map(monkeypatch):
    from backend.agents import compliance
    calls = []
    original = compliance.normalize_with_map
    def tracked(text):
        calls.append(text)
        return original(text)
    monkeypatch.setattr(compliance, 'normalize_with_map', tracked)
    compliance.ComplianceAuditAgent(lambda: [], lambda q: [], None).review('Ａ；Ｂ')
    assert calls == ['Ａ；Ｂ']



def test_latency_includes_save_and_is_persisted(monkeypatch):
    from backend.tools import audit_tool
    clock = [0.0]
    monkeypatch.setattr(audit_tool, 'perf_counter', lambda: clock[0])
    class Repo:
        latency = None
        def load_rules(self): return []
        def client(self, client_id): return True
        def script(self, script_id): return dict(client_id=1, content='介绍')
        def save(self, script_id, result):
            clock[0] = 0.05
            return 1
        def update_latency(self, audit_id, latency_ms): self.latency = latency_ms
    repo = Repo()
    tool = audit_tool.AuditTool(repo, model=object(), search_law=lambda q: [])
    result = tool.run_audit(1, 1)
    assert result['latency_ms'] == repo.latency == 50
    assert result['timings_ms']['persist'] == 50
