"""D4本地边界测试，不调用付费模型。"""
import pytest


def test_redteam_migration_preview_partial_skip():
    from scripts.migrate_scripts_redteam import plan
    class Inspector:
        columns = []
        def get_columns(self, table): return self.columns
    inspector = Inspector()
    assert len(plan(inspector)) == 2
    inspector.columns = [dict(name='source')]
    assert len(plan(inspector)) == 1
    inspector.columns.append(dict(name='redteam_meta'))
    assert plan(inspector) == []
