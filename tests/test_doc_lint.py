"""doc_lint 自身的测试。

两类都要测：
1. 检查器本身别误报——上一版它把"3 条轴漂移""第五条九项""~/.hermes 的家目录路径"
   都当成了数量/路径声明，误报多了人就会开始忽略红灯，那比没有检查更坏；
2. 红灯清单必须**等于已登记的欠债**。欠债清零后还报红灯、或冒出新的红灯，都必须失败，
   否则"红灯不许收工"只是一句口号。
"""

import importlib

import pytest

lint = importlib.import_module('scripts.doc_lint')

# 已登记的技术栈欠债：T-B 把 LangChain 适配层落地后，这条清单应当是空的。
# 将来若确实要带着某条红灯过关，在这里写清"哪条、为什么、什么时候修"——
# 清单是给人看的账，不是让测试让步的口子。
KNOWN_DEBT: tuple[str, ...] = ()


def test_facts_match_code():
    """事实基线是从源码文本数出来的，与代码真实规模必须一致。"""
    known = lint.facts()
    assert known == {'mcp_tools': 8, 'agents': 5, 'axes': 11,
                     'detectors': 3, 'dev_agents': 6}, known


def test_num_parses_both_notations():
    assert lint._num('12') == 12
    assert lint._num('十一') == 11
    assert lint._num('八') == 8
    assert lint._num('甲') == -1          # 解析不了就跳过，不猜


def test_expand_brace_paths_and_skips_glob():
    assert lint._expand('backend/parse/parsers/{documents,media}.py') == [
        'backend/parse/parsers/documents.py', 'backend/parse/parsers/media.py']
    assert lint._expand('backend/api/v1/*') == []          # 通配不当存在性检查
    assert lint._expand('backend/parse/base.py') == ['backend/parse/base.py']


def test_narration_lines_are_not_claims(tmp_path):
    """"删掉了 6 个工具这个说法"是复盘，不是当前声明；"共 6 个工具"才是声明。"""
    doc = tmp_path / 'note.md'
    doc.write_text(
        '2026-11-04 一次真实审校，删掉 5 处与代码不符的说法：总览图里"6 个工具/5 张表"\n'
        '当前共 6 个工具\n', encoding='utf-8')
    red = lint.check_counts([doc], {'mcp_tools': 8, 'agents': 5, 'dev_agents': 6,
                                    'axes': 11, 'detectors': 3})
    assert len(red) == 1, red
    assert '当前共 6 个工具' in red[0]


def test_home_paths_not_checked_as_repo_paths(tmp_path, monkeypatch):
    """`~/.hermes/skills/.../SKILL.md` 不在仓库里，不该报"路径不存在"。"""
    doc = tmp_path / 'skill.md'
    doc.write_text('见 `~/.hermes/skills/software-development/x/SKILL.md`\n', encoding='utf-8')
    monkeypatch.setattr(lint, 'ROOT', tmp_path)
    assert lint.check_paths([doc]) == []


def test_missing_repo_path_is_red(tmp_path, monkeypatch):
    doc = tmp_path / 'api_spec.md'
    doc.write_text('依赖：`backend/core/deps.py :: get_current_user`\n', encoding='utf-8')
    monkeypatch.setattr(lint, 'ROOT', tmp_path)
    red = lint.check_paths([doc])
    assert len(red) == 1 and 'backend/core/deps.py' in red[0]


def test_changelog_history_is_not_a_drift(tmp_path, monkeypatch):
    """CHANGELOG 提到"后来被删掉的文件"是事实经过；改它等于改历史。"""
    doc = tmp_path / 'CHANGELOG.md'
    doc.write_text('删掉了 `backend/api/v1/router/__init__.py` 这套重复结构\n', encoding='utf-8')
    monkeypatch.setattr(lint, 'ROOT', tmp_path)
    assert lint.check_paths([doc]) == []


def test_red_list_equals_registered_debt():
    """全仓体检：红灯必须恰好等于已登记欠债（当前为 0 条）。

    冒出新的漂移、或欠债清单没同步收窄，这条都会失败——这才是"红灯不许收工"。
    """
    red = lint.run(strict=False)
    unregistered = [line for line in red if not line.startswith(KNOWN_DEBT)]
    assert not unregistered, '新的文档漂移：\n' + '\n'.join(unregistered)
    assert len([line for line in red if line.startswith(KNOWN_DEBT)]) == len(KNOWN_DEBT)


def test_disclaimed_stack_is_not_a_claim(tmp_path, monkeypatch):
    """诚实交代"装了但未接入"不该被当成技术栈声明——否则大家只会把说明删掉。"""
    doc = tmp_path / 'README.md'
    doc.write_text('langgraph 1.2.16 已安装但未接入代码\n', encoding='utf-8')
    monkeypatch.setattr(lint, 'ROOT', tmp_path)
    assert lint.check_tech([doc]) == []


def test_claimed_stack_without_import_is_red(tmp_path, monkeypatch):
    """声称在用而代码 0 处 import：红灯要给出位置与两条出路，不能只说"不一致"。"""
    doc = tmp_path / 'CLAUDE.md'
    doc.write_text('| Agent 框架 | LangGraph（多 Agent 编排） |\n', encoding='utf-8')
    (tmp_path / 'requirements.txt').write_text('langgraph==1.2.16\n', encoding='utf-8')
    (tmp_path / 'backend').mkdir()
    monkeypatch.setattr(lint, 'ROOT', tmp_path)
    red = lint.check_tech([doc])
    assert len(red) == 1 and 'LangGraph' not in red[0]        # 报告里用小写包名，不重复文档写法
    assert '声称在用' in red[0] and '0 处 import' in red[0] and 'README' not in red[0]
    assert 'CLAUDE.md:1' in red[0]


def test_history_doc_does_not_claim_a_stack(tmp_path, monkeypatch):
    """CHANGELOG 写"当时发现 langgraph 0 处 import"是描述问题，不是声明在用。"""
    doc = tmp_path / 'CHANGELOG.md'
    doc.write_text('文档声称用了 `langgraph`，现在就是 0 处 import → 红灯\n', encoding='utf-8')
    (tmp_path / 'backend').mkdir()
    monkeypatch.setattr(lint, 'ROOT', tmp_path)
    assert lint.check_tech([doc]) == []


def test_strict_mode_exits_nonzero_on_red(monkeypatch):
    """红灯时退出码必须是 1：门禁要能挡住 CI，而不是只打印一行字。"""
    monkeypatch.setattr(lint, 'check_paths', lambda docs: ['路径不存在：x.py'])
    with pytest.raises(SystemExit) as exc:
        lint.run(strict=True)
    assert exc.value.code == 1
