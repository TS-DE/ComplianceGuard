"""Scope exclusions run before rule evaluation; not per-rule exemptions.

Copied verbatim from data/seeds/rules.json, including traceable sources.
These records are code constants, never a database table.
"""

SCOPE_EXEMPTIONS = [
    {
        "id": "scope_01",
        "text": "医疗机构以医疗科研为目的，发布的招募受试者、临床研究患者等信息，不构成广告。",
        "source": "医疗广告认定指南 第三条",
    },
    {
        "id": "scope_02",
        "text": "医疗机构对患者进行分诊或者就医引导，以及在开展互联网诊疗过程中线上解答患者咨询、指导患者接受诊疗等行为，不构成广告。",
        "source": "医疗广告认定指南 第四条",
    },
    {
        "id": "scope_03",
        "text": "医疗机构在本机构服务场所或自有互联网媒介公开发布机构概况、重点学科、医务人员信息、服务项目、诊疗流程、医保价格收费等信息，不存在该指南第六条规定情形的，不构成广告。",
        "source": "医疗广告认定指南 第五条",
    },
    {
        "id": "scope_04",
        "text": "医疗机构及其医务人员按照医疗卫生健康科普有关要求开展科普宣传，不存在该指南第八条规定情形的，不构成广告。",
        "source": "医疗广告认定指南 第七条",
    },
]
