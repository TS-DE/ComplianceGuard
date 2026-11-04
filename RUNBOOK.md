# RUNBOOK.md — 启动 / 回滚 / 故障排查

> **状态：草案（随环境变化更新）** ｜ 最后更新：2026-11-01 ｜ 维护：统筹方 + Claude
>
> Harness 组件④：**架构约束与可恢复性**。开发/演示出问题时，照本文件操作，不要临场发挥。

---

## 1. 启动顺序（严格按序）

```bash
# 1) MySQL 服务（Windows 服务 MySQL82，通常开机自启）
sc query MySQL82

# 2) 建库建表 + 种子数据
#    init_db 默认只打印 DDL 预览（铁律：结构性变更先预览），加 --apply 才执行
python -m scripts.init_db            # 预览
python -m scripts.init_db --apply    # 建库建表（幂等，可重复跑）
python -m scripts.show_tables        # 核对表结构与索引
python -m scripts.seed_cases

# 2b) 素材溯源迁移（幂等，只加表加列；重复执行会输出"跳过"）
python -m scripts.migrate_sources_provenance --apply --show

# 3) 构建向量库（Chroma）
python -m scripts.build_index

# 4) 后端
python -m uvicorn backend.main:app --reload --port 8000
#    健康检查：curl http://127.0.0.1:8000/health

# 5) MCP 自检（不联网、不花钱）
python -m backend.mcp_server.server --selftest

# 6) 前端
cd frontend && npm run dev
```

## 2. 环境变量（`.env`，不入库）

| 键 | 说明 |
|---|---|
| `DATABASE_URL` | `mysql+pymysql://root:123456@localhost:3306/compliance_guard` |
| `JWT_SECRET` / `JWT_EXPIRE_HOURS` | 鉴权 |
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | 判定/生成模型（OpenAI 兼容） |
| `CHROMA_DIR` | `D:\ComplianceGuard\data\chroma` |
| `NEO4J_*` | **默认不启用**，需要知识图谱时才配 |

## 3. 回滚手段（三级）

| 级别 | 操作 | 适用 |
|---|---|---|
| 代码 | `git revert <commit>` 或切回上一个 tag | 改坏了某次提交 |
| 数据 | 恢复 `scripts/` 下的备份 SQL（**执行前必须先导出**） | 误删数据 |
| 向量库 | 删除 `data/chroma/` 重建 `python -m scripts.build_index` | 索引脏了 |

## 4. 故障排查（按"现象 → 根因 → 处理"）

| 现象 | 根因 | 处理 |
|---|---|---|
| `import chromadb` 抛 `Descriptors cannot be created directly` | opentelemetry-proto 落后于 protobuf 7.x | 升级 opentelemetry-proto（见 `SKILL.md` S0） |
| 连不上 MySQL | 服务未启动 / 库不存在 | `sc query MySQL82`；跑 `scripts.init_db --apply` 自建库 |
| 插入 audits 报 `Check constraint 'ck_audits_score' is violated` | score 不在 -1..2 | 这是护栏生效，检查分数来源；未完成判定用 -1 |
| 模型 429 / 超时 | 限流或网络 | 系统自动降级为**纯规则判定**，结果标 `incomplete`，不许当合规 |
| 前端跨域 | CORS 未开 | 后端已放行 `localhost:5173`，新端口需补 |
| 中文乱码 | GBK 控制台 | 代码不打印 emoji；文件显式 UTF-8 |

## 5. 演示前检查清单
- [ ] `/health` 200
- [ ] MCP `--selftest` 6 个工具
- [ ] 锚点集 30 条已入库、向量库已建
- [ ] 用真实罚单话术跑通一次"审查→命中→改写"
- [ ] `.env` 已填、无明文密钥进 git

---

## 6. 素材摄取（文档 / 海报 / 扫描件 / 录音）

```bash
# 现在到底能吃什么：扩展名、缺哪个引擎、切分模式、上限（前端 accept 也由此生成）
python -X utf8 -c "from backend.parse import capabilities; import json; print(json.dumps(capabilities(), ensure_ascii=False, indent=2))"
# 真实跑一次 OCR（自造中文海报，逐字回查；不花钱不联网）
python -X utf8 -m scripts.verify_parse
# 解析某个具体文件
python -X utf8 -m scripts.verify_parse data/verify/poster.png "D:/某机构话术库.docx"
```

| 现象 | 根因 | 处理 |
|---|---|---|
| 上传录音 422「未安装语音引擎」 | `funasr` 未装（能力探测 `engines.asr=false`） | `python -m pip install --no-cache-dir funasr modelscope soundfile -i https://pypi.tuna.tsinghua.edu.cn/simple`；模型约 500MB 落在 `data/models`，**不写 C 盘** |
| 上传海报 422「图片无法解码」 | 文件损坏或不是真图片（与"不支持"是两回事） | 让商家重新导出；不要用截图工具二次压缩 |
| PDF 报「没有可抽取的文本层」且未降级到 OCR | OCR 引擎缺失，或 `PARSE_OCR_ENABLED=false` 把它关了 | 装 `rapidocr-onnxruntime`，或检查 `.env` |
| 扫描页超过 20 页报错 | 同步接口不能长挂 | 拆分文件分批上传（`OCR_MAX_PAGES`） |
| 解析置信度 40% 且带「请人工核对」 | 图糊/斜拍/花字 | **不要采信该条结论**，让商家重传清晰图；这是刻意的降级而非 bug |
| 首次 ASR 卡住很久 | 正在下载模型；或 C 盘空间不足导致写入失败 | 确认 `MODELSCOPE_CACHE`/`HF_HOME` 已指到项目盘（`core.config.configure_model_cache` 在导入时设置），C 盘剩余空间用 `python -c "import shutil;print(shutil.disk_usage('C:/').free/2**30)"` 核对 |

原始素材落盘在 `data/uploads/YYYYMM/<指纹前16位>.<ext>`（已在 `.gitignore`）。
**预览阶段不写盘**；只有 `commit=true` 才留下文件，所以磁盘体积等于"已入库素材"的体积。

---

## 变更记录
| 日期 | 变更 | 原因 |
|---|---|---|
| 2026-11-04 | 启动顺序加 2b 素材溯源迁移；新增 §6 素材摄取排查表 | 解析层上线后，OCR/ASR 与模型目录成为常见故障点，且模型缓存默认写 C 盘会挤爆磁盘 |
| 2026-11-01 | 建立启动顺序、回滚三级、故障表 | 项目启动 |
| 2026-11-01 | 启动命令改 `init_db --apply`，补 show_tables 与 CHECK 故障项 | D1 建库落地：预览与执行分离 |
