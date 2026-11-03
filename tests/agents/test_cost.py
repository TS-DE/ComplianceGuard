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
