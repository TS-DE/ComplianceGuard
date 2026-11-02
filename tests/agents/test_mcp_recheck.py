"""MCP 复核复用 A1，而非返回 D3 占位。"""
def test_mcp_recheck_delegates_to_real_audit_tool(monkeypatch):
    from backend.mcp_server.server import audit_recheck
    from backend.tools import audit_tool
    monkeypatch.setattr(audit_tool, 'recheck', lambda text, client_id: dict(
        score=0, hits=[{'quote': text}], law_refs=[{'code':'广告法第16条'}]))
    result = audit_recheck('保证有效', 1)
    assert result['score'] == 0
    assert result['law_refs'][0]['code'] == '广告法第16条'
    assert 'pending_d3' not in str(result)
