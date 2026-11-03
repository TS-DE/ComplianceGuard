# D4超时修复授权单轮：未完成，不重跑

8条传输测试RED全部失败，修复GREEN8通过；全量224 passed in 10.91s。A3成功生成16条，生成调用明细及所有原文/策略在JSON。终端工具420s处终止整个进程，Windows无残留python，非模型180s超时。6条已完成、余10条单列unjudged执行中断；未重启。

四格TP3/FN2/FP0/TN1/unjudged10；FN率2/5=0.4，FP率0/1=0，准确率4/16=0.25（分母含未判定，完整审查覆盖仅6/16）。不能声称16条完成。抽查script6/10预期违规且score2是FN；script7预期违规score0是TP；FP无条目，不能伪抽三条FN/FP。

已知判定/改写费用小计：{'known_judge_subtotal': Decimal('0.071959'), 'known_rewrite_subtotal': Decimal('0.007466')}；生成0.007146元。未完成项及embedding未知导致total_cost=null。实际embedding382token/A169084token=约0.553%，并非<0.3%，token占比不能证明费用影响。成本报告因未完成样本将三项总计均置未知，只能另报已完成小计。

标签局限：诱导轴样本更接近促销紧迫而非规则的容貌焦虑，绝对化low无明显绝对词，模型自报标签不是法律真值。固定生成prompt未改后重跑。

完整机器证据及日报/压测报告JSON：data/d4_timeout_fixed_report.json；初始进度原样保留data/d4_timeout_fixed_once.json。

样本量16，仅内部对比，不具统计代表性。验收失败，保留未完成，不重跑。
