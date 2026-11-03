"""法条规范化只处理引用，不改法规或规则数据。"""
from backend.core import constants as law_ref


def test_strip_item():
    assert law_ref.to_refs('广告法第16条(一)') == {'广告法.16'}


def test_alias_chinese_number():
    assert law_ref.to_refs('医美指南第五条(六)') == {'医疗美容广告执法指南.5'}


def test_multiple_refs():
    assert law_ref.to_refs('广告法第16条(四)、医美指南第五条(六)') == {
        '广告法.16', '医疗美容广告执法指南.5'}
    assert law_ref.to_refs('广告法第13条、第16条(三)') == {'广告法.13', '广告法.16'}


def test_sixteen():
    assert law_ref.to_refs('广告法第十六条') == {'广告法.16'}


def test_unknown_is_logged_not_raised(caplog):
    assert law_ref.to_refs('无法识别的文本') == set()
    assert 'law_ref_unparsed' in caplog.text


def test_mixed_punctuation_and_missing_docs():
    assert law_ref.to_refs('广告法第16条（一），医美指南第五条(六);第八条；监管工作指南第十一条') == {
        '广告法.16', '医疗美容广告执法指南.5', '医疗美容广告执法指南.8', '医疗广告监管工作指南.11'}
    assert law_ref.missing_docs({'广告法.16', '未知法.7'}, {'广告法'}) == {'未知法'}
