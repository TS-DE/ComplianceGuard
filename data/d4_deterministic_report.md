# D4 v0.4.3 确定性命中法源恢复

## 1. 改动说明
regex/keyword以rules.law_article为权威，不再被RAG缺召回否决；可绑定chunk时补项号与ref，否则to_refs降级并记录law_from_rule_table。LLM检索法条闸、pattern归属与项级match_refs均保留。未改rules数据、检索或阈值。

## 2. 关键代码与测试
backend/agents/base.py:bind_rule_law；backend/agents/compliance.py:_validate按rule.detector区分可信法源。
五类定向测试：核心缺召回保留、LLM非法法条拒绝、chunk补全、missing_docs告警放行、pattern跨轴拒绝。
中断前已观察RED（3 failed / 2 passed），修复5 passed。全量曾遇MySQL1041内存错误；恢复后238 passed in 12.07s。

## 3. 实际输出
本轮只生成absolute_terms四条、判定四条，未重跑其余12条；旧样本/审计未删除。
run_id: `rt_20261103_155339_absolute_terms`

|ID / 强度|原文|regex命中词|score / verdict|
|---|---|---|---|
|42 / low|姐妹，双眼皮我们做得很专业，效果基本都自然，口碑在本地算第一梯队。|第一|0 / TP_axis|
|43 / mid|双眼皮我们医生很专业，术后线条几乎100%自然，恢复期也很少出问题。|100%|0 / TP_axis|
|44 / high|双眼皮我们就是顶级专家操作，效果永久自然，绝对是最专业、最安全的第一选择。|顶级、永久、最专业、第一|0 / TP_axis|
|45 / control|双眼皮要看你的眼型、皮肤和期望，面诊后医生会和你讨论方案；每个人恢复和效果有差异，以医生评估为准。|无|2 / TN|

前三条的广告法第9条未在本次RAG候选里，持久化raw hits均包含law_from_rule_table=1、ref=广告法.9.3、chunk_id=null，证明确实走规则法源降级。控制组incomplete=false，score=2。四条A1 thinking=false / reasoning_chars=0 / attempt_count=1。
数据库读回：scripts22–45共24条、audits15–38共24条都在；新脚本42–45对应审计35–38。证据文件含完整行。

|指标|上轮v0.4.2|本轮|
|---|---:|---:|
|TP_axis|6|9|
|TP_other|4|1|
|FN|2|2|
|FP|0|0|
|TN|4|4|
|unjudged|0|0|
|整体漏杀率|16.67%|16.67%|
|轴级漏杀率|50%|25%|
|absolute_terms TP_axis|0|3|

整体漏杀率=2/(9+1+2)=16.67%；轴级漏杀率=(2+1)/(9+1+2)=25%。
本轮16条组合视图=旧功效安全22–29 + inducement38–41 + 新absolute42–45。

成本：生成0.006118元；判定0.033014元；rewrite记录0.000433元；embedding未计价，total=null。四条审查累计28.492秒；批次28.613秒；含生成总耗时74.137秒。控制样本出现query_rewrite_failed后使用原话术检索，未重试整个验收，仍完成判定；rewrite费用记录不等于完整供应商账单。

## 4. 风险与遗留
- 正则实测未覆盖：最适合、唯一、永远、最安全；最好已覆盖。最适合/最安全的极值表述、唯一的排他表述、永远的永久效果承诺，在推介服务语境下属于pattern“相同或者近似的其他绝对化用语”的候选范围；不是这些词在所有语境下都违法。列为待人工审核补词/上下文策略，本轮不改词表。
- low样本“第一梯队”被子串“第一”抓到，不等于其必然属于法律上的绝对化：梯队是集合排名，标签有争议，应人工复核；当前TP_axis是相对生成预期标签，不是官方真值。mid“几乎100%”也有修饰语边界。
- 本轮high中“最安全”未被absolute正则识别，但被安全语义轴命中；不能以本次整条命中掩盖词表缺口。
- 本轮没有验证全库按法条ID直取chunk：补全在传入候选中寻找匹配，未召回即规则ref降级；不影响确定性命中保留。
- 样本量16，仅内部对比，不具统计代表性。T-007语义空闸、T-008索引前缀仍保留。不构成法律意见。
