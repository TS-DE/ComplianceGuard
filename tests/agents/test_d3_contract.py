"""D3 契约回归，仅使用本地可控检测器。"""
from backend.agents.base import Detector
from backend.agents.compliance import ComplianceAuditAgent

SRC = '这个能保证你做完之后能往上走1—3个色度；所以这个是非常的安全，而且非常的高效'


class Echo(Detector):
    def detect(self, text, rule):
        return [dict(quote=text, pattern=rule.pattern, law_article=rule.law_article)]


def test_quotes_are_original_after_nfkc():
    for source in [SRC, 'Ａ；， " "、（保证）', 'Ａ\u200b  Ｂ']:
        rule = dict(axis='efficacy_claim', pattern='功效', law_article='广告法第16条', detector='echo')
        result = ComplianceAuditAgent(lambda: [rule], lambda q: [dict(code='广告法第16条')],
                                     None, {'echo': Echo()}).review(source)
        assert result['hits']
        assert all(source.find(h['quote']) >= 0 for h in result['hits'])
