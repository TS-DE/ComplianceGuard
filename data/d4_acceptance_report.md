# D4真实单轮：生成失败，未完成验收

## 已验证实现
迁移前后scripts均3行，来源manual；完整DDL见d4_migration_before/after.json。
本地mock/数据库测试216 passed in 10.86s；MCP工具恰好6个。16条矩阵含12违规与4对照；TP/FN/FP/TN/unjudged；SQL日报和元数据聚合；全链路响应token计量，embedding单价空则费用null。

## 唯一真实执行
python -m scripts.run_d4_once 退出1，在A3 model.complete中抛EmbeddingError：聊天服务请求失败或响应非法。现有适配器内建有限重试后仍失败；没有人工重跑。不知道供应商是否计费，失败无usage不能虚构token/cost。
红队脚本0，A4执行0，D4新增审计0。无法给出16条原文、FN/FP清单、分轴率和压测JSON；不以mock数据冒充。
D4新建标记机构保留（生成前已建），未破坏性清理。

## 失败只读证据
```json
{
  "status": "generation_failed",
  "exception": "EmbeddingError",
  "message": "聊天服务请求失败或响应非法",
  "retry_policy": "existing adapter max 3 attempts; no manual rerun",
  "database": {
    "scripts": 3,
    "redteam_scripts": 0,
    "audits": 7
  }
}
```
## 实际日报（既有D3记录，不是D4样本）
```json
{
  "total": 3,
  "incomplete": 0,
  "compliant": 0,
  "violations": 3,
  "average_latency_ms": "75094.0000",
  "cost": "0.058300",
  "unpriced": 0,
  "known_cost_subtotal": "0.058300",
  "date": "2026-11-03",
  "by_axis": {
    "efficacy_claim": 2,
    "safety_guarantee": 3,
    "inducement": 1,
    "before_after": 1
  },
  "violation_rate": 1.0,
  "summary": "今日审查3条，未完成0条。",
  "disclaimer": "本系统输出为合规风险辅助提示，不构成法律意见，也不能替代《医疗广告审查证明》的行政前置审查。"
}
```

## 风险与未完成验收
真实生成质量、递进强度、16条判定/人工抽查、FN/FP率均未验收。expected_violation为生成器自报标签，不是官方真值。可选报告模型仅允许选择预先模板，不允许自由改写，避免新事实。
embedding单价未知；实际失败没有可读usage，不能计算全链路费用或声明费用影响<0.3%。成功路径才可记录usage。旧D3日报费用仍为当时口径，不能追溯补齐RAG；本轮禁止伪改历史。
单次调用耗时日志仍主要记录成功响应，失败尝试明细不完整；T-007语义空闸、T-008索引前缀仍保留。A4尚无独立冻结锚点前置门禁，不声称已验证。
本轮停止，不调用模型重跑。
