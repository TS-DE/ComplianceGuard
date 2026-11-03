# D4 v0.4.2：仅重做inducement

## 实施与证据
生成器读取启用规则pattern/law_article，pattern_ref逐字检查；无轴拒绝；错引样本invalid_axis_ref不入矩阵。新run rt_20261103_152505_inducement，仅生成一次及四次A1，旧12条无模型调用。旧34–37/所有审计保留，新增无效标签及原因，不删除。
新增契约测试先3失败，修复后全量233 passed in 11.48s。五格fixture分别1条，整体漏杀1/3、轴漏杀2/3。

## 新4条人工论证
38 low：单眼皮→没精神/面试吃亏/不利索，把眼型与机会和能力印象相连，属轻度容貌焦虑诱导，不是促销紧迫；A1 score1/TP_axis。
39 mid：眼睛有神→相亲谈客户更顺，把容貌改善和社交商业结果相连，方向对齐规则“成功”正向关联；非字面低能贫穷，属较宽语义边界，需人工复核；A1 score1/TP_axis。
40 high：双眼皮→面试升职桃花，消除“拖沓没能力”，显式把容貌与能力/成功相连，明显容貌焦虑；A1 score1/TP_axis。
41 control：只讲流程、差异、评估，不评价眼型高低、不承诺事业人际，不应构成容貌焦虑；A1 score2/TN。对照应是合法负例，不要求其也制造焦虑。
四条均pattern_ref完全一致，invalid_axis_ref=0；判定thinking=false/reasoning0，attempt1，无重跑。

## 主视图16条
TP_axis6 / TP_other4 / FN2 / FP0 / TN4 / unjudged0，五格合计16。
整体漏杀率2/(6+4+2)=16.6667%；轴级漏杀率(2+4)/12=50%。误杀0/4，整体准确率14/16=87.5%。
上轮FN5/整体41.67%；本轮FN2/整体16.67%；上轮未区分目标轴，本轮TP_axis6、TP_other4。旧数据离线重算上轮为TP_axis3/TP_other4/FN5，轴漏杀9/12=75%，仅是回溯，不是新模型实验。
TP_other为安全mid1条和绝对化3条，不能把这些算目标轴召回。剩余FN22/26为限定语边界样本，生成标签不是法律真值。
样本量16，仅内部对比，不具统计代表性。

## 新增成本与时间
生成0.005112元；judge0.034622、rewrite0.000470、embedding=null、total=null（未计价不冒充合计）。判定41420tokens、rewrite507、embedding402。
新四条审查累计28778ms；一批28912.229ms；含生成总71546ms。生成保持thinking=true，判定全部false且reasoning0。

## 附视图全部20条（原文/调用明细见机器JSON）
|id|target_axis|strength|历史verdict|label_invalid|原因|
|---|---|---|---|---|---|
|22|efficacy_claim|low|FN|False|-|
|23|efficacy_claim|mid|TP|False|-|
|24|efficacy_claim|high|TP|False|-|
|25|efficacy_claim|control|TN|False|-|
|26|safety_guarantee|low|FN|False|-|
|27|safety_guarantee|mid|TP|False|-|
|28|safety_guarantee|high|TP|False|-|
|29|safety_guarantee|control|TN|False|-|
|30|absolute_terms|low|TP|False|-|
|31|absolute_terms|mid|TP|False|-|
|32|absolute_terms|high|TP|False|-|
|33|absolute_terms|control|TN|False|-|
|34|inducement|low|FN|True|生成器将促销紧迫误标为inducement，与rules容貌焦虑定义不符；整轴对照随批次排除|
|35|inducement|mid|FN|True|生成器将促销紧迫误标为inducement，与rules容貌焦虑定义不符；整轴对照随批次排除|
|36|inducement|high|FN|True|生成器将促销紧迫误标为inducement，与rules容貌焦虑定义不符；整轴对照随批次排除|
|37|inducement|control|TN|True|生成器将促销紧迫误标为inducement，与rules容貌焦虑定义不符；整轴对照随批次排除|
|38|inducement|low|TP_axis|False|-|
|39|inducement|mid|TP_axis|False|-|
|40|inducement|high|TP_axis|False|-|
|41|inducement|control|TN|False|-|

## 完整证据文件
原始JSON：data/d4_axis_aligned_once.json（含主视图16条、附视图20条、原文策略与调用明细）。数据库读回data/d4_axis_alignment_db.json：旧16脚本/16审计仍存在，新审计31–34。
未修改旧审计。34–36促销标签失配；37合法对照随整轴批次排除，不称其文本违法。

## 局限
pattern_ref校验保证定义引用一致，不证明生成语义一定正确；mid仍有解释边界。T-007/T-008继续保留；embedding未计价，全链路估算非账单。无其他12条的重新生成/判定。
