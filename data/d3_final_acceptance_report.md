# D3最终单次真实验收：指标未全部通过

## 代码与测试
验收前全量206 passed in 10.57s，工作区空，已提交。项级规范化7测试通过；metadata错项拒绝；merged缺轴/多路一致测试通过。未改规则或法规、未重建索引；此后不再运行模型。

## 完整原始JSON
```json
{
  "hits": [
    {
      "pattern": "对医疗服务的安全性作出断言或保证，如“非常安全”“绝对安全”“零风险”“无副作用”“没有任何副作用”“无毒副作用”“稳如泰山”。",
      "quote": "所以这个是非常的安全",
      "severity": "hard",
      "law_article": "广告法第16条",
      "detector": "llm_judge",
      "reason": "对安全性作出断言或保证，属于表示安全性的断言或者保证。",
      "axis": "safety_guarantee",
      "exempted_by": null,
      "chunk_id": "01_广告法:16:1:1",
      "code": "广告法第16条",
      "item_no": "第十六条(一)",
      "ref": "广告法.16.1",
      "start": 21,
      "end": 31,
      "original_quote": "所以这个是非常的安全",
      "normalized_start": 21,
      "normalized_end": 31,
      "sentence_id": 1,
      "axes": [
        "safety_guarantee"
      ],
      "evidence": [
        {
          "pattern": "对医疗服务的安全性作出断言或保证，如“非常安全”“绝对安全”“零风险”“无副作用”“没有任何副作用”“无毒副作用”“稳如泰山”。",
          "quote": "所以这个是非常的安全",
          "severity": "hard",
          "law_article": "广告法第16条",
          "detector": "llm_judge",
          "reason": "对安全性作出断言或保证，属于表示安全性的断言或者保证。",
          "axis": "safety_guarantee",
          "exempted_by": null,
          "chunk_id": "01_广告法:16:1:1",
          "code": "广告法第16条",
          "item_no": "第十六条(一)",
          "ref": "广告法.16.1",
          "start": 21,
          "end": 31,
          "original_quote": "所以这个是非常的安全",
          "normalized_start": 21,
          "normalized_end": 31,
          "sentence_id": 1
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
      "reason": "对做完后的色度提升作出保证性承诺，属于诊疗效果保证。",
      "axis": "efficacy_claim",
      "exempted_by": null,
      "chunk_id": "03_医疗美容广告执法指南:5:4:1",
      "code": "医疗美容广告执法指南第5条",
      "item_no": "第五条(四)",
      "ref": "医疗美容广告执法指南.5.4",
      "status": "cross_axis_rejected"
    },
    {
      "pattern": "对医疗美容的诊疗效果或安全性作出保证性承诺，包括“保证…能…”“一定…”“做完就能…”等断言式表述，无论是否含违禁词。",
      "quote": "而且非常的高效",
      "severity": "hard",
      "law_article": "医疗美容广告执法指南第5条",
      "detector": "llm_judge",
      "reason": "对效果作出高效断言，属于诊疗功效保证性承诺。",
      "axis": "efficacy_claim",
      "exempted_by": null,
      "chunk_id": "03_医疗美容广告执法指南:5:4:1",
      "code": "医疗美容广告执法指南第5条",
      "item_no": "第五条(四)",
      "ref": "医疗美容广告执法指南.5.4",
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
      "doc_type": "law",
      "chunk_id": "01_广告法:16:1:1",
      "item_no": "第十六条(一)"
    },
    {
      "text": "（一）表示功效、安全性的断言或者保证；",
      "code": "广告法第18条",
      "source": "01_广告法.md",
      "score": 0.1742221135802623,
      "route": "bm25+vector+lexicon+rewrite",
      "parent_text": "第十八条　保健食品广告不得含有下列内容：\n\n（一）表示功效、安全性的断言或者保证；\n\n（二）涉及疾病预防、治疗功能；\n\n（三）声称或者暗示广告商品为保障健康所必需；\n\n（四）与药品、其他保健食品进行比较；\n\n（五）利用广告代言人作推荐、证明；\n\n（六）法律、行政法规规定禁止的其他内容。\n\n保健食品广告应当显著标明“本品不能代替药物”。",
      "doc_type": "law",
      "chunk_id": "01_广告法:18:1:1",
      "item_no": "第十八条(一)"
    },
    {
      "text": "（四）宣传诊疗效果或者对诊疗的安全性、功效做保证性承诺。",
      "code": "医疗美容广告执法指南第5条",
      "source": "03_医疗美容广告执法指南.md",
      "score": 0.1571494627969426,
      "route": "bm25+vector+lexicon+rewrite",
      "parent_text": "五、市场监管部门依法整治各类医疗美容广告乱象，着力解决危害性大、群众反映集中的问题，对以下情形予以重点打击：\n\n（一）违背社会良好风尚，制造“容貌焦虑”，将容貌不佳与“低能”“懒惰”“贫穷”等负面评价因素做不当关联或者将容貌出众与“高素质”“勤奋”“成功”等积极评价因素做不当关联。\n\n（二）违反药品、医疗器械、广告等法律法规规定，对未经药品管理部门审批或者备案的药品、医疗器械作广告。\n\n（三）宣传未经卫生健康行政部门审批、备案的诊疗科目和服务项目。\n\n（四）宣传诊疗效果或者对诊疗的安全性、功效做保证性承诺。\n\n（五）利用行业协会以及其他社会社团或组织的名义、形象作证明，使用患者名义或者形象进行诊疗前后效果对比或者作证明。\n\n（六）利用广告代言人为医疗美容做推荐、证明。医疗美容广告中出现的所谓“推荐官”“体验官”等，以自己名义或者形象为医疗美容做推荐证明的，应当被认定为广告代言人。\n\n（七）以介绍健康、养生知识、人物专访、新闻报道等形式变相发布医疗美容广告。\n\n（八）对食品、保健食品、消毒产品、化妆品宣传与医疗美容相关的疾病治疗功能。\n\n（九）其他违反广告法律法规规定，严重侵害群众权益的行为。",
      "doc_type": "guideline",
      "chunk_id": "03_医疗美容广告执法指南:5:4:1",
      "item_no": "第五条(四)"
    }
  ],
  "incomplete": false,
  "no_reference": false,
  "prompt_tokens": 10049,
  "completion_tokens": 1961,
  "cost": "0.013334",
  "model": "qwen3.8-flash",
  "disclaimer": "本系统输出为合规风险辅助提示，不构成法律意见，也不能替代《医疗广告审查证明》的行政前置审查。",
  "timings_ms": {
    "normalize": 0.04259999877831433,
    "rules": 2.9300000005605398,
    "retrieve": 11419.63399999986,
    "detect": 58891.93840000007,
    "aggregate": 0.426500000685337,
    "persist": 27.28209999986575
  },
  "raw_hits": [
    {
      "pattern": "对医疗服务的安全性作出断言或保证，如“非常安全”“绝对安全”“零风险”“无副作用”“没有任何副作用”“无毒副作用”“稳如泰山”。",
      "quote": "所以这个是非常的安全",
      "severity": "hard",
      "law_article": "广告法第16条",
      "detector": "llm_judge",
      "reason": "对安全性作出断言或保证，属于表示安全性的断言或者保证。",
      "axis": "safety_guarantee",
      "exempted_by": null,
      "chunk_id": "01_广告法:16:1:1",
      "code": "广告法第16条",
      "item_no": "第十六条(一)",
      "ref": "广告法.16.1",
      "start": 21,
      "end": 31,
      "original_quote": "所以这个是非常的安全",
      "normalized_start": 21,
      "normalized_end": 31,
      "sentence_id": 1
    }
  ],
  "hit_count": 1,
  "score": 0,
  "latency_ms": 70346,
  "llm_calls": [
    {
      "latency_ms": 58887.353600001006,
      "attempt_count": 2,
      "retried": true,
      "prompt_tokens": 10049,
      "completion_tokens": 1961
    }
  ],
  "id": 7,
  "audit_id": 7,
  "script_id": 3
}

```
## 六样证据
```json
{
  "positions": [
    21
  ],
  "candidates": [
    {
      "axis": "safety_guarantee",
      "code": "广告法第16条",
      "item_no": "第十六条(一)",
      "ref": "广告法.16.1",
      "status": null
    },
    {
      "axis": "efficacy_claim",
      "code": "医疗美容广告执法指南第5条",
      "item_no": "第五条(四)",
      "ref": "医疗美容广告执法指南.5.4",
      "status": "cross_axis_rejected"
    },
    {
      "axis": "efficacy_claim",
      "code": "医疗美容广告执法指南第5条",
      "item_no": "第五条(四)",
      "ref": "医疗美容广告执法指南.5.4",
      "status": "cross_axis_rejected"
    }
  ],
  "database": {
    "id": 7,
    "script_id": 3,
    "score": 0,
    "hit_count": 1,
    "incomplete": 0,
    "model": "qwen3.8-flash",
    "prompt_tokens": 10049,
    "completion_tokens": 1961,
    "cost": "0.013334",
    "latency_ms": 70346,
    "created_at": "2026-11-03 11:10:14",
    "hits_json_length": 4
  }
}
```
分阶段毫秒：normalize0.0426/rules2.9300/retrieve11419.6340/detect58891.9384/aggregate0.4265/persist27.2821；总70346。
A1合并调用耗时58887.3536ms，attempt_count2/retried=true；10049输入/1961输出，计量cost0.013334元。没有单个尝试时长，不能补造。RAG费用仍未计入。
原文quote位置21；raw命中安全轴继承广告法第16条第一项，ref广告法.16.1，属于规则广告法第16条(一)。另两条功效候选引用医美指南第五条第四项，被本轴仅声明广告法16.1的规则拒绝。
traces：cross_axis_rejected2条；item_mismatch0条；matched_at_article_level0条。本次模型未输出before_after/inducement候选，不能把“未出现”说成是本次被项号闸拦截。

## 判据及归因
1. 失败：安全命中、无before_after/inducement误命中，但有效功效轴缺失。模型功效举证本身合理，却选择医美指南5.4；既有规则只允许广告法16.1，严格归属拒绝了替代法源。未自行扩大规则允许集合，不改后重跑。
2. 通过：原文引文可定位，保留项号且来自可信chunk元数据；有效安全命中规则/证据均为广告法.16.1。
3. 通过：score0/incomplete=false/latency70346<90000。合并调用经历适配器自动重试一次，属于这一次审查内既有重试，不是人工重跑。
总体验收未全部通过，按用户要求无论结果均合并发布；不得宣称功效召回达标。

## 风险技术债
T-007 pattern预填仍非客观语义证明，候选方案判据短语/weak_evidence。
T-008 索引正文code前缀未重建，仅输出边界剥离。
T-009 cost仅A1可读响应，不含RAG、失败响应未知费用。
