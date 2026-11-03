"""法条规范化只处理引用，不改法规或规则数据。"""
from backend.core import constants as law_ref


def test_strip_item():
    assert law_ref.to_refs('广告法第16条(一)') == {'广告法.16.1'}


def test_alias_chinese_number():
    assert law_ref.to_refs('医美指南第五条(六)') == {'医疗美容广告执法指南.5.6'}


def test_multiple_refs():
    assert law_ref.to_refs('广告法第16条(四)、医美指南第五条(六)') == {
        '广告法.16.4', '医疗美容广告执法指南.5.6'}
    assert law_ref.to_refs('广告法第13条、第16条(三)') == {'广告法.13', '广告法.16.3'}


def test_sixteen():
    assert law_ref.to_refs('广告法第十六条') == {'广告法.16'}


def test_unknown_is_logged_not_raised(caplog):
    assert law_ref.to_refs('无法识别的文本') == set()
    assert 'law_ref_unparsed' in caplog.text


def test_mixed_punctuation_and_missing_docs():
    assert law_ref.to_refs('广告法第16条（一），医美指南第五条(六);第八条；监管工作指南第十一条') == {
        '广告法.16.1', '医疗美容广告执法指南.5.6', '医疗美容广告执法指南.8', '医疗广告监管工作指南.11'}
    assert law_ref.missing_docs({'广告法.16', '未知法.7'}, {'广告法'}) == {'未知法'}



def test_item_match_and_article_fallback():
    from backend.core.constants import match_refs
    assert law_ref.to_refs('医美指南第五条(五)') == {'医疗美容广告执法指南.5.5'}
    assert law_ref.to_refs('医美指南第八条') == {'医疗美容广告执法指南.8'}
    assert match_refs({'指南.5.5'}, {'指南.5.4'}) == 'item_mismatch'
    assert match_refs({'指南.5.5'}, {'指南.5'}) == 'matched_at_article_level'
    assert match_refs({'指南.8'}, {'指南.8.2'}) == 'matched'
    assert match_refs({'广告法.16.1'}, {'广告法.16.3'}) == 'item_mismatch'
