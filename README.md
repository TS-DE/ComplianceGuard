# ComplianceGuard

> 状态：生效 ｜ 最后更新：2026-11-01 ｜ 维护：Claude

面向**强监管行业营销话术**的合规审查与红队压测中台。首个切片：医疗美容 / 口腔。

用户提交一段话术 → 确定性词库 + LLM 语义轴两层判定 → 输出命中的法条、原文引文、
分数与改写建议 → 落库出审计报告；另有红队压测输出漏杀清单。

> 本系统输出为合规风险辅助提示，**不构成法律意见**，也不能替代《医疗广告审查证明》的行政前置审查。

## 技术栈
FastAPI + Pydantic V2 · SQLAlchemy 2.0 + MySQL 8 · Chroma · LangChain/LangGraph · MCP · Vue3

素材摄取：python-docx / pdfplumber / pypdfium2 / openpyxl / xlrd / python-pptx（文档结构层），
RapidOCR + onnxruntime（海报与扫描件），FunASR SenseVoiceSmall（录音，可选引擎）。

## 当前进度
- D1：目录骨架、MySQL 五张表、JWT 注册登录、clients/scripts/audits/rules 四套 CRUD

## 怎么跑（Windows，Python 3.12）
```bash
# 1. 配置
copy .env.example .env          # 填 DATABASE_URL 与 JWT_SECRET
python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 2. 建库建表 + 灌示例案例
python -m scripts.init_db
python -m scripts.seed_cases

# 3. 启动后端（文档：http://localhost:8000/docs）
python -m uvicorn backend.main:app --reload --port 8000

# 4. 测试（使用独立的 *_test 库，事务回滚不留数据）
python -m pytest tests -q
```

## 文档入口
`CLAUDE.md`（规则）→ `.hermes.md`（阶段披露）→ `db_schema.md` / `api_spec.md`（契约）
