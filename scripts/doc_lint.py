"""文档与代码一致性体检：**只读，不改**。发现红灯即退出码 1。

为什么要有这个脚本：熵增最典型的表现不是代码烂，而是"文档写着支持、跑起来不行"。
评委照着 requirements.md 逐条验收，文档里的路径、数量、技术栈只要有一处与代码不符，
扣分的是项目而不是某个人。这类漂移靠人眼盯是盯不住的——本文件每轮交付前必须跑。

刻意不 import backend：doc_lint 要在装不上依赖的机器上也能给出红灯清单，
所以全部事实都从源码文本里数出来，宁可解析粗一点，也不把体检绑在运行时上。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 文档扫描范围：项目自己的说明文档。法条语料（data/law/*.md）不看——
# 那里的"第五条九项"是法条原文而不是本项目的数量声明，拿它报红灯是检查器的错
DOC_GLOBS = ("*.md", "docs/**/*.md", "skills/**/*.md", "frontend/*.md")
DOC_SKIP = ("node_modules", "dist", ".git", "__pycache__", "venv", ".qwen")
# CHANGELOG 是追加式历史记录：里面提到的文件后来被删掉是事实经过，不是文档漂移。
# 拿它报红灯等于逼人改历史，那是把记录修坏。
HISTORY_DOCS = {'CHANGELOG.md'}

# 代码路径：要求带目录前缀且有扩展名，避免把"base.py"这类裸文件名当路径；
# 前面不能紧跟 / 或 ~ —— `~/.hermes/skills/.../SKILL.md` 是家目录路径，不在仓库里查存在性
PATH_RE = re.compile(r'(?<![/~.])(?:backend|frontend|scripts|tests|docs)/[\w./{}\u4e00-\u9fff-]+?'
                     r'\.(?:py|vue|ts|json|md|sql)')
BRACES = re.compile(r"\{([^{}]*)\}")

CN_NUM = {'零': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
          '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}

# 数量口径：文档里出现"N 个工具 / N 条轴"这类说法时，N 必须等于代码里数出来的事实。
# 模式收紧到"数字与量词紧邻"：`3 条假轴漂移`、`第五条九项` 这类行文不是数量声明；
# 单字"一"也跳过——"一个 Agent 只做一类事"里的"一"是量词用法，不是数量声明。
COUNT_CHECKS = (
    (re.compile(r'(\d+|[零二三四五六七八九十]+)\s*个\s*(?:MCP\s*)?工具'), 'mcp_tools', 'MCP 工具数'),
    (re.compile(r'(\d+|[零二三四五六七八九十]+)\s*个\s*(?:业务)?(?:智能体|Agent)'), 'agents', '业务智能体数'),
    (re.compile(r'(\d+|[零二三四五六七八九十]+)\s*个\s*(?:开发)?子\s*Agent'), 'dev_agents', '开发子 Agent 数'),
    (re.compile(r'(\d+|[零二三四五六七八九十]+)\s*条\s*(?:合规)?轴(?!漂移|样本)'), 'axes', '规则轴数'),
    (re.compile(r'(\d+|[零二三四五六七八九十]+)\s*个?\s*检测器'), 'detectors', '检测器类型数'),
)

# 技术栈声明：文档提到就必须代码里真有用到（import 或依赖声明），否则是"名不符实"
TECH_CLAIMS = {
    'langchain': ('backend', ('langchain',)),
    'langgraph': ('backend', ('langgraph',)),
    'chromadb': ('backend', ('chromadb', 'chroma')),
    'fastapi': ('backend', ('fastapi',)),
}


def _num(token: str) -> int:
    """解析 1-99 的阿拉伯或中文数字；解析不了返回 -1（跳过比较，不猜）。"""
    if token.isdigit():
        return int(token)
    total, digit = 0, 0
    for char in token:
        if char not in CN_NUM:
            return -1
        value = CN_NUM[char]
        if char == '十':
            total += (digit or 1) * 10
            digit = 0
        else:
            digit = value
    return total + digit


def _docs() -> list[Path]:
    seen, out = set(), []
    for pattern in DOC_GLOBS:
        for path in sorted(ROOT.glob(pattern)):
            if path.is_file() and path.resolve() not in seen:
                if not any(part in DOC_SKIP for part in path.parts):
                    seen.add(path.resolve())
                    out.append(path)
    return out


def _py_sources(sub: str) -> list[Path]:
    root = ROOT / sub
    return [p for p in root.rglob("*.py") if not any(part in DOC_SKIP for part in p.parts)]


def facts() -> dict[str, int]:
    """从源码文本里数出文档必须遵守的事实基线。"""
    server = ''.join(p.read_text(encoding='utf-8', errors='replace')
                     for p in (ROOT / 'backend/mcp_server').glob('*.py'))
    agents_src = ''.join(p.read_text(encoding='utf-8', errors='replace')
                         for p in (ROOT / 'backend/agents').glob('*.py'))
    base_src = (ROOT / 'backend/agents/base.py').read_text(encoding='utf-8', errors='replace')
    registry = re.search(r'DETECTORS: dict[^\n]*\{(?P<body>.*?)\n\}', base_src, re.S)
    detector_keys = re.findall(r'^\s*"(\w+)":', registry.group('body'), re.M) if registry else []
    seeds = json.loads((ROOT / 'data/seeds/rules.json').read_text(encoding='utf-8'))
    axes = {row['axis'] for row in seeds.get('rules', [])}
    agents_md = (ROOT / 'AGENTS.md').read_text(encoding='utf-8', errors='replace')
    section = agents_md.split('## B.', 1)[0]
    dev_agents = len(re.findall(r'^\|\s*\*\*[^*]+Agent\*\*', section, re.M))
    return {'mcp_tools': len(re.findall(r'@mcp\.tool', server)),
            'agents': len(set(re.findall(r'^class\s+(\w*Agent)\b', agents_src, re.M))),
            'detectors': len(set(detector_keys)),
            'axes': len(axes),
            'dev_agents': dev_agents}


def _label(path: Path) -> str:
    """给报告用的文件名：仓库内取相对路径，仓库外原样输出。

    不写相对路径会直接 ValueError——测试用 tmp_path 喂检查器时就撞过一次，
    工具的健壮性也归体检管。
    """
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def check_paths(docs: list[Path]) -> list[str]:
    """文档里写的代码路径必须真实存在。"""
    red: list[str] = []
    for path in docs:
        if path.name in HISTORY_DOCS:
            continue
        for lineno, line in enumerate(path.read_text(encoding='utf-8', errors='replace').splitlines(), 1):
            # 整行含复盘用词就不查存在性："改成了另一套结构（backend/api/v1/router/__init__.py）"
            # 讲的是已经删掉的东西，不是"这里应该有个文件"
            if any(hint in line for hint in NARRATION_HINTS):
                continue
            for token in PATH_RE.findall(line):
                for candidate in _expand(token):
                    if not (ROOT / candidate).exists():
                        red.append(f'{_label(path)}:{lineno} 路径不存在：{candidate}')
                        break
    return red


def _expand(token: str) -> list[str]:
    """把 `parsers/{documents,media}.py` 展开成两个候选；带通配的片段不当存在性检查。"""
    brace = BRACES.search(token)
    if brace:
        return [token.replace(brace.group(0), part) for part in brace.group(1).split(',') if part]
    return [] if ('*' in token or token.endswith('.')) else [token]


# 复盘句子里出现的数字是"当年那个错说法"，不是当前声明。
# 检查器不理解语义，只能靠词表挡：命中数字前若出现这些词，就跳过比较。
# 这条局限是有意保留的——红灯清单仍然要人看一眼，不能把工具当免检。
NARRATION_HINTS = ('删掉', '删除', '更正', '修正', '旧', '曾', '原来', '误', '不再', '改成', '之前')


def check_counts(docs: list[Path], known: dict[str, int]) -> list[str]:
    """文档里的数量说法必须与代码事实一致。"""
    red: list[str] = []
    for path in docs:
        for lineno, line in enumerate(path.read_text(encoding='utf-8', errors='replace').splitlines(), 1):
            # 与路径检查同一口径：整行含复盘用词就不比数量。
            # 前查窗口试过 24 字，实际挡不住"删掉 5 处说法：……6 个工具"这种长行
            if any(hint in line for hint in NARRATION_HINTS):
                continue
            for pattern, key, label in COUNT_CHECKS:
                for match in pattern.finditer(line):
                    value = _num(match.group(1))
                    # "一个 Agent 只做一类事"里的"一"是量词不是声明；解析不出也跳过，不猜
                    if value <= 1 or value == known[key]:
                        continue
                    red.append(f'{_label(path)}:{lineno} {label}说"是 {value}，'
                               f'实际 {known[key]}：…{line.strip()[:60]}')
    return red


# 明确写着"未使用"的行不是技术栈声明。没有这条护栏，诚实交代"装了但没接进代码"
# 也会被当成声明而报红灯，最后大家只会把说明删掉——信息变少，红灯变多，两败俱伤。
NO_CLAIM_HINTS = ('未使用', '未接入', '没用', '未用', '仅安装', '已安装但', '不宣称')


def check_tech(docs: list[Path]) -> list[str]:
    """文档声称的技术栈必须在代码里真的用着。

    历史记录（CHANGELOG）不看：它写"当时发现 langgraph 0 处 import"是在描述问题，
    不是声明在用；拿它报红灯等于逼人改历史——与路径检查同一取舍。
    """
    red: list[str] = []
    claims: dict[str, str] = {}            # 名字 → 第一处"声称使用"的位置
    for path in docs:
        if path.name in HISTORY_DOCS:
            continue
        for lineno, line in enumerate(path.read_text(encoding='utf-8', errors='replace').splitlines(), 1):
            for name in TECH_CLAIMS:
                if re.search(rf'\b{name}\b', line, re.I) and not any(h in line for h in NO_CLAIM_HINTS):
                    claims.setdefault(name, f'{_label(path)}:{lineno}')
    for name in sorted(claims):
        folder, needles = TECH_CLAIMS[name]
        hits = 0
        # 拼成变量再喂 findall：f-string 里嵌同种引号在 3.12 之前会直接把语法搞崩
        import_re = r'^\s*(?:import|from)\s+(' + '|'.join(needles) + ')'
        for source in _py_sources(folder):
            text = source.read_text(encoding='utf-8', errors='replace')
            hits += len(re.findall(import_re, text, re.M))
        if hits == 0:
            declared = any(needle in (ROOT / 'requirements.txt').read_text(encoding='utf-8', errors='replace')
                           for needle in needles) if (ROOT / 'requirements.txt').exists() else False
            red.append(f'技术栈 {name}：{claims[name]} 声称在用，但 {folder}/**/*.py 里 0 处 import'
                       + ('' if declared else f'，且 requirements.txt 未声明（{"/".join(needles)}）')
                       + '；要么把代码补上，要么把该行改成"已安装、未接入"')
    return red


# 目录文件数上限的**登记式豁免**：
# - tests/ 与 tests/agents/：pytest 的惯例是一个被测模块一个测试文件，按 3 个上限拆包
#   只会让"改哪个模块要动哪个测试"变模糊，收益是负的；
# - scripts/：入口脚本天然互不依赖，硬塞子包会打断 RUNBOOK 里写死的调用路径。
# 豁免写在这里而不是把检查关掉：新增的第四类目录想豁免，必须先在本文档说明理由。
DIR_EXEMPT = ('tests', r'tests[/\\]agents', r'tests[/\\]rag', 'scripts')


def check_dir_limits() -> list[str]:
    """每个目录的真实源文件数必须 ≤3，超了就该分子包而不是继续堆。"""
    red: list[str] = []
    buckets: dict[Path, dict[str, int]] = {}
    for folder in ('backend', 'frontend/src', 'tests', 'scripts', 'docs'):
        base = ROOT / folder
        if not base.is_dir():
            continue
        for source in list(base.rglob('*.py')) + list(base.rglob('*.vue')):
            if any(part in DOC_SKIP for part in source.parts) or 'node_modules' in source.parts:
                continue
            kind = 'vue' if source.suffix == '.vue' else 'py'
            if kind == 'py' and source.name == '__init__.py':
                continue                       # 包声明不算真实源文件
            counters = buckets.setdefault(source.parent, {'py': 0, 'vue': 0})
            counters[kind] += 1
    for directory, counters in sorted(buckets.items()):
        relative = directory.relative_to(ROOT).as_posix()
        if any(re.fullmatch(rule, relative) for rule in DIR_EXEMPT):
            continue
        for kind, count in counters.items():
            if count > 3:
                red.append(f'{relative} 有 {count} 个真实 .{kind}，超过每目录 3 个的上限')
    return red


def run(strict: bool = True) -> list[str]:
    docs = _docs()
    known = facts()
    red = check_paths(docs) + check_counts(docs, known) + check_tech(docs) + check_dir_limits()
    print('事实基线：' + '　'.join(f'{k}={v}' for k, v in sorted(known.items())))
    print(f'扫描文档 {len(docs)} 份。')
    if red:
        print(f'\n红灯 {len(red)} 条（只读体检，未改任何文件）：')
        for line in red:
            print('  ✗ ' + line)
    else:
        print('红灯 0 条：文档与代码一致。')
    if red and strict:
        raise SystemExit(1)
    return red


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='文档与代码一致性体检（只读）')
    parser.add_argument('--lenient', action='store_true',
                        help='打印红灯但退出码 0（用于观察，不作为交付门禁）')
    args = parser.parse_args(argv)
    try:
        run(strict=not args.lenient)
    except SystemExit:
        raise
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
