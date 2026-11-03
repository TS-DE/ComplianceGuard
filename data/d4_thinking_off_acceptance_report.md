# D4 v0.4.1：关闭思考真实单轮完成

## 代码与离线测试
thinking判定false/生成true/改写false，显式配置才透传；JUDGE_PASS_THINKING_PARAM可禁用。audits.hits_json存call_metadata。脚本4条分批、--resume跳过任何已有verdict；本轮一次运行到底，未使用resume重判。RED：3种payload/批处理4失败；GREEN含生成分离与ignored参数检测，全量229 passed in 11.80s。

## 16条及调用明细
|id|axis|strength|expected_violation|原文|score|actual_axes|verdict|LLM ms|completion_tokens|thinking/reasoning_chars|
|---|---|---|---|---|---|---|---|---|---|---|
|22|efficacy_claim|low|True|姐妹，双眼皮做完一般会显得眼睛更有神一点，不过具体还是要看你的眼型基础。|2|-|FN|2239.9|70|false/0|
|23|efficacy_claim|mid|True|很多做完双眼皮的姐妹反馈，恢复后线条会更清晰，睁眼也更自然，整体气质会提升不少。|0|efficacy_claim|TP|4903.2|239|false/0|
|24|efficacy_claim|high|True|放心，这款双眼皮方案做完眼睛一定放大，线条一定自然，绝对看不出是做的。|0|efficacy_claim|TP|3585.8|183|false/0|
|25|efficacy_claim|control|False|双眼皮效果因人而异，需要结合你的皮肤、脂肪和眼型面诊评估，我们不会提前承诺具体变化。|2|-|TN|1829.7|70|false/0|
|26|safety_guarantee|low|True|正规医生操作的话，双眼皮的风险通常会比外面小一些，术前也会帮你评估。|2|-|FN|3108.5|170|false/0|
|27|safety_guarantee|mid|True|我们医生经验比较熟，会尽量把双眼皮恢复期不舒服和并发症概率降下来。|0|efficacy_claim|TP|3669.2|199|false/0|
|28|safety_guarantee|high|True|这个双眼皮项目零风险，绝对安全，术后不会出现任何失败情况。|0|efficacy_claim,safety_guarantee|TP|4322.5|246|false/0|
|29|safety_guarantee|control|False|任何手术都存在一定风险，双眼皮也需要术前检查、医生评估和术后护理，不能简单说绝对安全。|2|-|TN|1917.5|70|false/0|
|30|absolute_terms|low|True|从你照片看，这种双眼皮方案是比较稳妥的选择，适合大多数人。|0|efficacy_claim|TP|2456.2|155|false/0|
|31|absolute_terms|mid|True|这款双眼皮就是最适合你的方案，做完基本不会有后悔的情况。|0|efficacy_claim|TP|2904.4|144|false/0|
|32|absolute_terms|high|True|这是市面上最好的双眼皮技术，唯一不会变形，永远自然。|0|derogatory_compare,efficacy_claim|TP|6233.2|307|false/0|
|33|absolute_terms|control|False|没有绝对最好的双眼皮方案，只有面诊后更适合你基础条件的选择。|2|-|TN|1875.5|70|false/0|
|34|inducement|low|True|现在预约双眼皮面诊，可以优先安排医生，不用等太久。|2|-|FN|1855.8|70|false/0|
|35|inducement|mid|True|这个双眼皮名额不多了，今天定下来还能帮你保留优惠，建议尽快锁定。|2|-|FN|2018.2|70|false/0|
|36|inducement|high|True|今天不交定金就抢不到这个双眼皮优惠了，马上安排，错过就没有变美机会。|2|-|FN|3226.3|167|false/0|
|37|inducement|control|False|你可以先预约咨询，了解双眼皮方案后再理性决定，是否预约完全由你自己判断。|2|-|TN|1642.0|70|false/0|

全部A1调用attempt_count=1、last_error=null、thinking=false、reasoning_chars=0。A3 thinking=true，42690.8983ms，completion2097/reasoning1820。每条strategy和完整尝试明细保留机器JSON。

## 矩阵及率
TP7/FN5/FP0/TN4/unjudged0，总16；漏杀5/12=41.6667%，误杀0/4=0%，准确率11/16=68.75%。样本量16，仅内部对比，不具统计代表性。
FN id22、26、34、35、36；FP空。人工核对22、26、34均expected=true且score2/actual_axes=[]，分类一致；不代表其生成标签必然符合法律真值。
按轴TP/FN：功效2/1、安全2/1、绝对化3/0、诱导0/3。安全mid与绝对化样本由其他轴命中，TP是整体风险命中，不等于目标轴召回。

## 性能与成本
审查平均5921ms（含RAG/落库），A1 completion平均143.75；总wall141251ms含生成/初始化/报告。
四批24689.61/25305.79/25635.02/19601.55ms。
累计阶段ms：normalize0.9483/rules59.2106/retrieve46419.7818/detect47912.3645/aggregate2.5811/persist277.4377。
judge_cost0.124447、rewrite_cost0.001676、embedding_cost=null、total_cost=null；生成另0.005840元。embedding实际998tokens；A1总150097tokens。全链路估算，非供应商账单，未知项不冒充合计。

## 上轮对照（非同一批样本，不是受控精度A/B）
上轮仅6条完成，平均审查46120.17ms、completion1464.17、unjudged10、FN/FP/TN/TP=2/0/1/3；本轮16条，5921ms、143.75、0、5/0/4/7。不能用此表宣称关闭思考提升整体准确率。

## 判据
16条完成、矩阵和16、平均<15秒、reasoning全部0，抽查3条FN一致，全部满足本轮执行判据。模型标签问题、T-007语义空闸/T-008索引前缀依旧；T-009成功响应全链路计量已接，但embedding单价未知及失败响应费用不可得。

## 完整日报及压测JSON
完整原始运行（含日报与压测报告）在 data/d4_thinking_off_once.json，DB读回在data/d4_thinking_off_db_evidence.json；以下保留报告数值摘要。
```json
{
  "run_id": "rt_20261103_151028",
  "counts": {
    "TP": 7,
    "FN": 5,
    "FP": 0,
    "TN": 4,
    "unjudged": 0
  },
  "costs": {
    "judge_cost": "0.124447",
    "rewrite_cost": "0.001676",
    "embedding_cost": null,
    "judge_tokens": 150097,
    "rewrite_tokens": 1727,
    "embedding_tokens": 998,
    "total_cost": null,
    "generation_cost": "0.005840",
    "run_total_cost": null,
    "latency_ms": 94736,
    "embedding_token_ratio": 0.00664903362492255,
    "cost_note": "全链路估算，非供应商账单；embedding未计价，token占比不等于费用占比"
  },
  "daily": {
    "total": 25,
    "incomplete": 0,
    "compliant": 12,
    "violations": 13,
    "average_latency_ms": "23869.5600",
    "cost": null,
    "unpriced": 22,
    "known_cost_subtotal": "0.058300",
    "date": "2026-11-03",
    "by_axis": {
      "efficacy_claim": 11,
      "safety_guarantee": 5,
      "before_after": 1,
      "inducement": 1,
      "derogatory_compare": 1
    },
    "violation_rate": 0.52,
    "summary": "今日审查25条，未完成0条。",
    "disclaimer": "本系统输出为合规风险辅助提示，不构成法律意见，也不能替代《医疗广告审查证明》的行政前置审查。"
  },
  "batches": [
    {
      "completed": 4,
      "total": 16,
      "latency_ms": 24689.609900000505
    },
    {
      "completed": 8,
      "total": 16,
      "latency_ms": 25305.785399999877
    },
    {
      "completed": 12,
      "total": 16,
      "latency_ms": 25635.02399999925
    },
    {
      "completed": 16,
      "total": 16,
      "latency_ms": 19601.551600000676
    }
  ]
}
```
