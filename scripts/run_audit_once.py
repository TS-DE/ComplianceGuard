"""读取已存话术，仅运行一次 A1 并原样保存、打印结果。"""
import argparse
import json
from decimal import Decimal
from pathlib import Path

from backend.db.session import SessionLocal
from backend.tools.audit_tool import build_audit_tool


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--script-id', type=int, required=True)
    parser.add_argument('--client-id', type=int, required=True)
    parser.add_argument('--output', default='data/d3_acceptance_once.json')
    args = parser.parse_args()
    output = Path(args.output)
    # 排他创建：失败也保留占位，防止误操作重跑产生额外费用。
    with output.open('x', encoding='utf-8') as evidence:
        with SessionLocal() as session:
            result = build_audit_tool(session).run_audit(args.script_id, args.client_id)
        payload = json.dumps(result, ensure_ascii=False, indent=2,
                             default=lambda value: str(value) if isinstance(value, Decimal) else value)
        evidence.write(payload + '\n')
    print(payload)


if __name__ == '__main__':
    main()
