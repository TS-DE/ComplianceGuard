# D3 阶段F及唯一一次真实验收：未通过

## 1. 改动及迁移
cost 可空迁移默认预览、--apply执行、幂等。之前 decimal(10,6) NOT NULL DEFAULT 0.000000；之后 decimal(10,6) DEFAULT NULL；生产行数4→4；再执行跳过。compute_cost 使用Decimal、六位量化；环境优先作者提供的MODEL_PRICES；缺价NULL。known_docs读取本地Chroma；字符起点映射接入；save后总耗时回填数据库。无索引重建、无规则更改。
成本/迁移/接线13 passed；验收前全量202 passed in 10.37s。代码已提交且工作区为空后才运行。

## 2. 完整原始JSON
```json
{
  "hits": [
    {
      "pattern": "对医疗美容的诊疗效果或安全性作出保证性承诺，包括“保证…能…”“一定…”“做完就能…”等断言式表述，无论是否含违禁词。",
      "quote": "所以这个是非常的安全，而且非常的高效",
      "severity": "hard",
      "law_article": "广告法第16条",
      "detector": "llm_judge",
      "reason": "对安全性、功效作出断言或保证。",
      "axis": "efficacy_claim",
      "exempted_by": null,
      "start": 21,
      "end": 39,
      "original_quote": "所以这个是非常的安全，而且非常的高效",
      "normalized_start": 21,
      "normalized_end": 39,
      "sentence_id": 1,
      "axes": [
        "efficacy_claim"
      ],
      "evidence": [
        {
          "pattern": "对医疗美容的诊疗效果或安全性作出保证性承诺，包括“保证…能…”“一定…”“做完就能…”等断言式表述，无论是否含违禁词。",
          "quote": "所以这个是非常的安全，而且非常的高效",
          "severity": "hard",
          "law_article": "广告法第16条",
          "detector": "llm_judge",
          "reason": "对安全性、功效作出断言或保证。",
          "axis": "efficacy_claim",
          "exempted_by": null,
          "start": 21,
          "end": 39,
          "original_quote": "所以这个是非常的安全，而且非常的高效",
          "normalized_start": 21,
          "normalized_end": 39,
          "sentence_id": 1
        }
      ]
    },
    {
      "pattern": "对医疗服务的安全性作出断言或保证，如“非常安全”“绝对安全”“零风险”“无副作用”“没有任何副作用”“无毒副作用”“稳如泰山”。",
      "quote": "这个能保证你做完之后能往上走1—3个色度；所以这个是非常的安全，而且非常的高效",
      "severity": "hard",
      "law_article": "广告法第16条",
      "detector": "llm_judge",
      "reason": "文本对医疗服务安全性作出“非常的安全”等断言保证，并承诺“往上走1—3个色度”的功效，属于表示功效、安全性的断言或者保证。",
      "axis": "safety_guarantee",
      "exempted_by": null,
      "start": 0,
      "end": 39,
      "original_quote": "这个能保证你做完之后能往上走1—3个色度；所以这个是非常的安全，而且非常的高效",
      "normalized_start": 0,
      "normalized_end": 39,
      "sentence_id": 0,
      "axes": [
        "safety_guarantee",
        "before_after",
        "inducement"
      ],
      "evidence": [
        {
          "pattern": "对医疗服务的安全性作出断言或保证，如“非常安全”“绝对安全”“零风险”“无副作用”“没有任何副作用”“无毒副作用”“稳如泰山”。",
          "quote": "这个能保证你做完之后能往上走1—3个色度；所以这个是非常的安全，而且非常的高效",
          "severity": "hard",
          "law_article": "广告法第16条",
          "detector": "llm_judge",
          "reason": "文本对医疗服务安全性作出“非常的安全”等断言保证，并承诺“往上走1—3个色度”的功效，属于表示功效、安全性的断言或者保证。",
          "axis": "safety_guarantee",
          "exempted_by": null,
          "start": 0,
          "end": 39,
          "original_quote": "这个能保证你做完之后能往上走1—3个色度；所以这个是非常的安全，而且非常的高效",
          "normalized_start": 0,
          "normalized_end": 39,
          "sentence_id": 0
        },
        {
          "pattern": "使用患者名义或形象进行诊疗前后效果对比，或利用患者、卫生技术人员、医学教育科研机构及人员的名义、形象作证明。",
          "quote": "这个能保证你做完之后能往上走1—3个色度；所以这个是非常的安全，而且非常的高效",
          "severity": "soft",
          "law_article": "医疗美容广告执法指南第5条",
          "detector": "llm_judge",
          "reason": "文本对做完后的色度提升作出“能保证”“非常的安全”“非常的高效”等确定性承诺，属于宣传诊疗效果或对诊疗的安全性、功效作保证性承诺。",
          "axis": "before_after",
          "exempted_by": null,
          "start": 0,
          "end": 39,
          "original_quote": "这个能保证你做完之后能往上走1—3个色度；所以这个是非常的安全，而且非常的高效",
          "normalized_start": 0,
          "normalized_end": 39,
          "sentence_id": 0
        },
        {
          "pattern": "制造“容貌焦虑”，将容貌不佳与“低能”“懒惰”“贫穷”等负面评价因素作不当关联，或将容貌出众与“高素质”“勤奋”“成功”等积极因素作不当关联。",
          "quote": "这个能保证你做完之后能往上走1—3个色度；所以这个是非常的安全，而且非常的高效",
          "severity": "soft",
          "law_article": "医疗美容广告执法指南第5条",
          "detector": "llm_judge",
          "reason": "文本承诺做完后可提升1—3个色度，并宣称非常安全、高效，属于对诊疗效果或安全性、功效作保证性承诺。",
          "axis": "inducement",
          "exempted_by": null,
          "start": 0,
          "end": 39,
          "original_quote": "这个能保证你做完之后能往上走1—3个色度；所以这个是非常的安全，而且非常的高效",
          "normalized_start": 0,
          "normalized_end": 39,
          "sentence_id": 0
        }
      ]
    }
  ],
  "traces": [
    {
      "pattern": "对医疗美容的诊疗效果或安全性作出保证性承诺，包括“保证…能…”“一定…”“做完就能…”等断言式表述，无论是否含违禁词。",
      "quote": "这个能保证你做完之后能往上走1—3个色度",
      "severity": "hard",
      "law_article": "医疗美容广告执法指南第5条",
      "detector": "llm_judge",
      "reason": "对诊疗效果作出保证性承诺。",
      "axis": "efficacy_claim",
      "exempted_by": null,
      "status": "cross_axis_rejected"
    },
    {
      "pattern": "对医疗服务的安全性作出断言或保证，如“非常安全”“绝对安全”“零风险”“无副作用”“没有任何副作用”“无毒副作用”“稳如泰山”。",
      "quote": "这个能保证你做完之后能往上走1—3个色度;所以这个是非常的安全,而且非常的高效",
      "severity": "hard",
      "law_article": "医疗美容广告执法指南第5条",
      "detector": "llm_judge",
      "reason": "文本宣传诊疗效果并作出“能保证”“非常的安全”“非常的高效”等保证性承诺，符合对诊疗的安全性、功效做保证性承诺的情形。",
      "axis": "safety_guarantee",
      "exempted_by": null,
      "status": "cross_axis_rejected"
    }
  ],
  "law_refs": [
    {
      "text": "（一）表示功效、安全性的断言或者保证；",
      "code": "广告法第16条",
      "source": "01_广告法.md",
      "score": 0.17437512953213755,
      "route": "bm25+vector+lexicon+rewrite",
      "parent_text": "第十六条　医疗、药品、医疗器械广告不得含有下列内容：\n\n（一）表示功效、安全性的断言或者保证；\n\n（二）说明治愈率或者有效率；\n\n（三）与其他药品、医疗器械的功效和安全性或者其他医疗机构比较；\n\n（四）利用广告代言人作推荐、证明；\n\n（五）法律、行政法规规定禁止的其他内容。\n\n药品广告的内容不得与国务院药品监督管理部门批准的说明书不一致，并应当显著标明禁忌、不良反应。处方药广告应当显著标明“本广告仅供医学药学专业人士阅读”，非处方药广告应当显著标明“请按药品说明书或者在药师指导下购买和使用”。\n\n推荐给个人自用的医疗器械的广告，应当显著标明“请仔细阅读产品说明书或者在医务人员的指导下购买和使用”。医疗器械产品注册证明文件中有禁忌内容、注意事项的，广告中应当显著标明“禁忌内容或者注意事项详见说明书”。",
      "doc_type": "law"
    },
    {
      "text": "（一）表示功效、安全性的断言或者保证；",
      "code": "广告法第18条",
      "source": "01_广告法.md",
      "score": 0.1742221135802623,
      "route": "bm25+vector+lexicon+rewrite",
      "parent_text": "第十八条　保健食品广告不得含有下列内容：\n\n（一）表示功效、安全性的断言或者保证；\n\n（二）涉及疾病预防、治疗功能；\n\n（三）声称或者暗示广告商品为保障健康所必需；\n\n（四）与药品、其他保健食品进行比较；\n\n（五）利用广告代言人作推荐、证明；\n\n（六）法律、行政法规规定禁止的其他内容。\n\n保健食品广告应当显著标明“本品不能代替药物”。",
      "doc_type": "law"
    },
    {
      "text": "（四）宣传诊疗效果或者对诊疗的安全性、功效做保证性承诺。",
      "code": "医疗美容广告执法指南第5条",
      "source": "03_医疗美容广告执法指南.md",
      "score": 0.1571494627969426,
      "route": "bm25+vector+lexicon+rewrite",
      "parent_text": "五、市场监管部门依法整治各类医疗美容广告乱象，着力解决危害性大、群众反映集中的问题，对以下情形予以重点打击：\n\n（一）违背社会良好风尚，制造“容貌焦虑”，将容貌不佳与“低能”“懒惰”“贫穷”等负面评价因素做不当关联或者将容貌出众与“高素质”“勤奋”“成功”等积极评价因素做不当关联。\n\n（二）违反药品、医疗器械、广告等法律法规规定，对未经药品管理部门审批或者备案的药品、医疗器械作广告。\n\n（三）宣传未经卫生健康行政部门审批、备案的诊疗科目和服务项目。\n\n（四）宣传诊疗效果或者对诊疗的安全性、功效做保证性承诺。\n\n（五）利用行业协会以及其他社会社团或组织的名义、形象作证明，使用患者名义或者形象进行诊疗前后效果对比或者作证明。\n\n（六）利用广告代言人为医疗美容做推荐、证明。医疗美容广告中出现的所谓“推荐官”“体验官”等，以自己名义或者形象为医疗美容做推荐证明的，应当被认定为广告代言人。\n\n（七）以介绍健康、养生知识、人物专访、新闻报道等形式变相发布医疗美容广告。\n\n（八）对食品、保健食品、消毒产品、化妆品宣传与医疗美容相关的疾病治疗功能。\n\n（九）其他违反广告法律法规规定，严重侵害群众权益的行为。",
      "doc_type": "guideline"
    }
  ],
  "incomplete": false,
  "no_reference": false,
  "prompt_tokens": 9148,
  "completion_tokens": 8853,
  "cost": "0.031221",
  "model": "qwen3.8-flash",
  "disclaimer": "本系统输出为合规风险辅助提示，不构成法律意见，也不能替代《医疗广告审查证明》的行政前置审查。",
  "timings_ms": {
    "normalize": 0.04059999992023222,
    "rules": 2.3773000002620392,
    "retrieve": 12744.696200000362,
    "detect": 101845.78899999996,
    "aggregate": 0.40239999998448184,
    "persist": 28.217800000675197
  },
  "raw_hits": [
    {
      "pattern": "对医疗美容的诊疗效果或安全性作出保证性承诺，包括“保证…能…”“一定…”“做完就能…”等断言式表述，无论是否含违禁词。",
      "quote": "所以这个是非常的安全，而且非常的高效",
      "severity": "hard",
      "law_article": "广告法第16条",
      "detector": "llm_judge",
      "reason": "对安全性、功效作出断言或保证。",
      "axis": "efficacy_claim",
      "exempted_by": null,
      "start": 21,
      "end": 39,
      "original_quote": "所以这个是非常的安全，而且非常的高效",
      "normalized_start": 21,
      "normalized_end": 39,
      "sentence_id": 1
    },
    {
      "pattern": "对医疗服务的安全性作出断言或保证，如“非常安全”“绝对安全”“零风险”“无副作用”“没有任何副作用”“无毒副作用”“稳如泰山”。",
      "quote": "这个能保证你做完之后能往上走1—3个色度；所以这个是非常的安全，而且非常的高效",
      "severity": "hard",
      "law_article": "广告法第16条",
      "detector": "llm_judge",
      "reason": "文本对医疗服务安全性作出“非常的安全”等断言保证，并承诺“往上走1—3个色度”的功效，属于表示功效、安全性的断言或者保证。",
      "axis": "safety_guarantee",
      "exempted_by": null,
      "start": 0,
      "end": 39,
      "original_quote": "这个能保证你做完之后能往上走1—3个色度；所以这个是非常的安全，而且非常的高效",
      "normalized_start": 0,
      "normalized_end": 39,
      "sentence_id": 0
    },
    {
      "pattern": "使用患者名义或形象进行诊疗前后效果对比，或利用患者、卫生技术人员、医学教育科研机构及人员的名义、形象作证明。",
      "quote": "这个能保证你做完之后能往上走1—3个色度；所以这个是非常的安全，而且非常的高效",
      "severity": "soft",
      "law_article": "医疗美容广告执法指南第5条",
      "detector": "llm_judge",
      "reason": "文本对做完后的色度提升作出“能保证”“非常的安全”“非常的高效”等确定性承诺，属于宣传诊疗效果或对诊疗的安全性、功效作保证性承诺。",
      "axis": "before_after",
      "exempted_by": null,
      "start": 0,
      "end": 39,
      "original_quote": "这个能保证你做完之后能往上走1—3个色度；所以这个是非常的安全，而且非常的高效",
      "normalized_start": 0,
      "normalized_end": 39,
      "sentence_id": 0
    },
    {
      "pattern": "制造“容貌焦虑”，将容貌不佳与“低能”“懒惰”“贫穷”等负面评价因素作不当关联，或将容貌出众与“高素质”“勤奋”“成功”等积极因素作不当关联。",
      "quote": "这个能保证你做完之后能往上走1—3个色度；所以这个是非常的安全，而且非常的高效",
      "severity": "soft",
      "law_article": "医疗美容广告执法指南第5条",
      "detector": "llm_judge",
      "reason": "文本承诺做完后可提升1—3个色度，并宣称非常安全、高效，属于对诊疗效果或安全性、功效作保证性承诺。",
      "axis": "inducement",
      "exempted_by": null,
      "start": 0,
      "end": 39,
      "original_quote": "这个能保证你做完之后能往上走1—3个色度；所以这个是非常的安全，而且非常的高效",
      "normalized_start": 0,
      "normalized_end": 39,
      "sentence_id": 0
    }
  ],
  "hit_count": 2,
  "score": 0,
  "latency_ms": 114625,
  "id": 6,
  "audit_id": 6,
  "script_id": 3
}

```

## 3. 只读证据
```json
{
  "claim_positions": [
    21,
    0
  ],
  "raw_positions": [
    21,
    0,
    0,
    0
  ],
  "law_membership": [
    {
      "axis": "efficacy_claim",
      "declared": "广告法第16条(一)",
      "canonical_declared": [
        "广告法.16"
      ],
      "cited": "广告法第16条",
      "canonical_cited": [
        "广告法.16"
      ],
      "matches": true
    },
    {
      "axis": "safety_guarantee",
      "declared": "广告法第16条(一)",
      "canonical_declared": [
        "广告法.16"
      ],
      "cited": "广告法第16条",
      "canonical_cited": [
        "广告法.16"
      ],
      "matches": true
    },
    {
      "axis": "before_after",
      "declared": "医疗广告管理办法第7条(六)、医美指南第五条(五)",
      "canonical_declared": [
        "医疗广告管理办法.7",
        "医疗美容广告执法指南.5"
      ],
      "cited": "医疗美容广告执法指南第5条",
      "canonical_cited": [
        "医疗美容广告执法指南.5"
      ],
      "matches": true
    },
    {
      "axis": "inducement",
      "declared": "广告法第9条(七)、医美指南第五条(一)",
      "canonical_declared": [
        "医疗美容广告执法指南.5",
        "广告法.9"
      ],
      "cited": "医疗美容广告执法指南第5条",
      "canonical_cited": [
        "医疗美容广告执法指南.5"
      ],
      "matches": true
    }
  ],
  "database": {
    "id": 6,
    "script_id": 3,
    "score": 0,
    "hit_count": 2,
    "incomplete": 0,
    "model": "qwen3.8-flash",
    "prompt_tokens": 9148,
    "completion_tokens": 8853,
    "cost": "0.031221",
    "latency_ms": 114625,
    "created_at": "2026-11-03 10:39:17",
    "hits_json_length": 8
  }
}
```

## 4. 结论和五类归因
1. 数据及法条：当前规则全部可规范化；本次检索code来自真实RAG，所有raw_hits均通过条级本轴集合校验。
2. 引文：hits位置[21,0]，raw_hits位置[21,0,0,0]，逐字原文定位通过；未再发生半角标点契约bug。
3. 轴归属：未通过。before_after、inducement仍误命中。模型按第5条第四项功效保证举证，却被放进第五项前后对比、第一项焦虑轴。按要求剥项号的条级归属只能验证同一条，不能区分同条不同项；pattern由可信规则注入而非模型证明，不足以校验语义。两条引用医美指南第5条的efficacy/safety候选则按本轴仅声明广告法16条被正确拒绝，保留traces。
4. 网络及延迟：总114625ms，不满足90000ms；retrieve12744.6962ms、detect101845.789ms、persist28.2178ms，瓶颈仍在8个语义任务的4-worker两批模型请求。没有逐任务网络尝试日志，不能断言供应商排队或重试具体贡献。
5. 计价：模型qwen3.8-flash，prompt9148、completion8853，cost0.031221元，是逐请求六位量化后的费用汇总。仅计量A1可读响应，不含RAG内部rewrite/embedding，不是账单。

判据1失败（仍有before_after）；判据2通过；判据3部分通过（score0且incomplete=false，但114625ms超时）。按要求不改代码、不再重跑、不合并main或打成功标签。索引正文带code前缀技术债保留，仅返回时剥离。真实结果JSON中Decimal成本按原脚本序列化为字符串；不是数值零，也不是NULL。
