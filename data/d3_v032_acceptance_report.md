# D3 v0.3.2 第4次验收：三项通过

## 依据与规则版本
03指南第五条(四)及事先入库建议映射efficacy_claim/safety_guarantee；08管理办法第七条(三)对应cure_rate。三轴v1停用/v2启用，旧内容保留，总数11→14，仍启用11条。仅enabled停用标志允许UPDATE，历史内容不覆盖。重复种子新增0。未放宽项级闸、未改评测集。
版本化测试RED：旧v1仍enabled1；修复后seed9 passed；验收前全量207 passed in 11.09s、提交且工作区空。

## 完整原始JSON
```json
{
  "hits": [
    {
      "pattern": "对医疗美容的诊疗效果或安全性作出保证性承诺，包括“保证…能…”“一定…”“做完就能…”等断言式表述，无论是否含违禁词。",
      "quote": "这个能保证你做完之后能往上走1—3个色度",
      "severity": "hard",
      "law_article": "医疗美容广告执法指南第5条",
      "detector": "llm_judge",
      "reason": "使用“能保证……能……”对做完后的色度提升作出保证性承诺，属于对诊疗效果的断言式表述。",
      "axis": "efficacy_claim",
      "exempted_by": null,
      "chunk_id": "03_医疗美容广告执法指南:5:4:1",
      "code": "医疗美容广告执法指南第5条",
      "item_no": "第五条(四)",
      "ref": "医疗美容广告执法指南.5.4",
      "start": 0,
      "end": 20,
      "original_quote": "这个能保证你做完之后能往上走1—3个色度",
      "normalized_start": 0,
      "normalized_end": 20,
      "sentence_id": 0,
      "axes": [
        "efficacy_claim"
      ],
      "evidence": [
        {
          "pattern": "对医疗美容的诊疗效果或安全性作出保证性承诺，包括“保证…能…”“一定…”“做完就能…”等断言式表述，无论是否含违禁词。",
          "quote": "这个能保证你做完之后能往上走1—3个色度",
          "severity": "hard",
          "law_article": "医疗美容广告执法指南第5条",
          "detector": "llm_judge",
          "reason": "使用“能保证……能……”对做完后的色度提升作出保证性承诺，属于对诊疗效果的断言式表述。",
          "axis": "efficacy_claim",
          "exempted_by": null,
          "chunk_id": "03_医疗美容广告执法指南:5:4:1",
          "code": "医疗美容广告执法指南第5条",
          "item_no": "第五条(四)",
          "ref": "医疗美容广告执法指南.5.4",
          "start": 0,
          "end": 20,
          "original_quote": "这个能保证你做完之后能往上走1—3个色度",
          "normalized_start": 0,
          "normalized_end": 20,
          "sentence_id": 0
        }
      ]
    },
    {
      "pattern": "对医疗服务的安全性作出断言或保证，如“非常安全”“绝对安全”“零风险”“无副作用”“没有任何副作用”“无毒副作用”“稳如泰山”。",
      "quote": "所以这个是非常的安全",
      "severity": "hard",
      "law_article": "广告法第16条",
      "detector": "llm_judge",
      "reason": "对医疗服务安全性作出“非常的安全”的断言式保证。",
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
          "reason": "对医疗服务安全性作出“非常的安全”的断言式保证。",
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
  "traces": [],
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
  "prompt_tokens": 10063,
  "completion_tokens": 2109,
  "cost": "0.013745",
  "model": "qwen3.8-flash",
  "disclaimer": "本系统输出为合规风险辅助提示，不构成法律意见，也不能替代《医疗广告审查证明》的行政前置审查。",
  "timings_ms": {
    "normalize": 0.039399999877787195,
    "rules": 2.554100001361803,
    "retrieve": 10187.414899999567,
    "detect": 30097.22900000088,
    "aggregate": 0.21500000002561137,
    "persist": 20.907800000713905
  },
  "raw_hits": [
    {
      "pattern": "对医疗美容的诊疗效果或安全性作出保证性承诺，包括“保证…能…”“一定…”“做完就能…”等断言式表述，无论是否含违禁词。",
      "quote": "这个能保证你做完之后能往上走1—3个色度",
      "severity": "hard",
      "law_article": "医疗美容广告执法指南第5条",
      "detector": "llm_judge",
      "reason": "使用“能保证……能……”对做完后的色度提升作出保证性承诺，属于对诊疗效果的断言式表述。",
      "axis": "efficacy_claim",
      "exempted_by": null,
      "chunk_id": "03_医疗美容广告执法指南:5:4:1",
      "code": "医疗美容广告执法指南第5条",
      "item_no": "第五条(四)",
      "ref": "医疗美容广告执法指南.5.4",
      "start": 0,
      "end": 20,
      "original_quote": "这个能保证你做完之后能往上走1—3个色度",
      "normalized_start": 0,
      "normalized_end": 20,
      "sentence_id": 0
    },
    {
      "pattern": "对医疗服务的安全性作出断言或保证，如“非常安全”“绝对安全”“零风险”“无副作用”“没有任何副作用”“无毒副作用”“稳如泰山”。",
      "quote": "所以这个是非常的安全",
      "severity": "hard",
      "law_article": "广告法第16条",
      "detector": "llm_judge",
      "reason": "对医疗服务安全性作出“非常的安全”的断言式保证。",
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
  "hit_count": 2,
  "score": 0,
  "latency_ms": 40311,
  "llm_calls": [
    {
      "latency_ms": 30092.4212000009,
      "attempt_count": 1,
      "retried": false,
      "prompt_tokens": 10063,
      "completion_tokens": 2109
    }
  ],
  "id": 8,
  "audit_id": 8,
  "script_id": 3
}

```
## 六样证据
```json
{
  "positions": [
    0,
    21
  ],
  "candidates": [
    {
      "axis": "efficacy_claim",
      "code": "医疗美容广告执法指南第5条",
      "item_no": "第五条(四)",
      "ref": "医疗美容广告执法指南.5.4",
      "declared": [
        "医疗美容广告执法指南.5.4",
        "广告法.16.1"
      ],
      "exact": true,
      "rejected": false,
      "reason": null
    },
    {
      "axis": "safety_guarantee",
      "code": "广告法第16条",
      "item_no": "第十六条(一)",
      "ref": "广告法.16.1",
      "declared": [
        "医疗美容广告执法指南.5.4",
        "广告法.16.1"
      ],
      "exact": true,
      "rejected": false,
      "reason": null
    }
  ],
  "database": {
    "id": 8,
    "script_id": 3,
    "score": 0,
    "hit_count": 2,
    "incomplete": 0,
    "model": "qwen3.8-flash",
    "prompt_tokens": 10063,
    "completion_tokens": 2109,
    "cost": "0.013745",
    "latency_ms": 40311,
    "created_at": "2026-11-03 11:21:55",
    "hits_json_length": 4
  },
  "traces": []
}
```
阶段毫秒：normalize0.0394/rules2.5541/retrieve10187.4149/detect30097.2290/aggregate0.2150/persist20.9078；总40311。
A1调用30092.4212ms，attempt_count1/retried=false，prompt10063、completion2109、cost0.013745元。
拒绝/降级记录traces=[]，无任何被拦候选，不能凭空声称拦截。

## 判据
1. 通过：efficacy_claim与safety_guarantee均命中，无before_after/inducement。
2. 通过：quote位置[0,21]，继承ref分别为医美指南5.4和广告法16.1，均与对应v2规则某一项精确一致，未使用条级兜底。
3. 通过：score0、incomplete=false、40311<90000。
仅执行本轮一次A1，未跑A2、未重跑。

## 风险技术债
这是指定单案例验收通过，不代表全量语义质量达标。
T-007语义空闸仍保留；T-008索引正文code前缀仍待未来重建；T-009cost不含RAG rewrite/embedding及无法计量费用。作者单价是估算不是账单。
