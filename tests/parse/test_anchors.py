"""切分锚点：话术必须带得出「在整篇原文里的绝对区间」，而不是只有页号/行号。

覆盖三层，缺任何一层都会退化成"前端猜位置"：
1. 解析层：split_doc 就地算出 start/end 与全部出现位置 spans；
2. 剥序号/压空白之后仍然锚得上（话术不是原文的字面子串，逐字 find 会失败）；
3. 同一句出现两次：入库一条（按文本去重是既有策略），但两处都要能亮出来。
"""

from backend.parse import Doc, Block, doc_index, occurrences, split_doc, split_scripts


def test_pieces_carry_absolute_offsets_into_full_text() -> None:
    doc = Doc(filename="a.txt", kind="text", engine="paste", blocks=[
        Block("第一句承诺。\n第二句保证三个月恢复正常肤色。")])
    pieces = split_doc(doc, "line")
    assert [p.text for p in pieces] == ["第一句承诺。", "第二句保证三个月恢复正常肤色。"]
    for piece in pieces:
        assert piece.start is not None and piece.end is not None
        # 反向校验：按偏移从整篇切出来的那段，忽略空白后必须等于话术本身
        sliced = doc.text[piece.start:piece.end]
        assert ''.join(sliced.split()) == ''.join(piece.text.split())


def test_offsets_are_absolute_across_blocks() -> None:
    """块与块之间要接上：第二块的起点不是 0，而是第一块长度 + 连接换行。"""
    first, second = "术后零风险。", "效果永久。"
    doc = Doc(filename="b.txt", kind="text", engine="paste", blocks=[Block(first), Block(second)])
    pieces = split_doc(doc, "line")
    assert [p.text for p in pieces] == [first, second]
    assert pieces[1].start == len(first) + 1            # "\n".join 的那个换行
    assert doc.text[pieces[1].start:pieces[1].end] == second


def test_leading_numbering_is_stripped_yet_still_locatable() -> None:
    """话术剥掉了行首序号，锚点仍要指回带序号的原文位置——否则逐字 find 必然失败。"""
    doc = Doc(filename="c.txt", kind="text", engine="paste",
              blocks=[Block("1、保证三个月恢复正常肤色\n2、可能需要大约三个月")])
    pieces = split_doc(doc, "line")
    assert pieces[0].text == "保证三个月恢复正常肤色"
    assert pieces[0].start == 2                          # 跳过 "1、"
    assert doc.text[pieces[0].start:pieces[0].end] == pieces[0].text


def test_same_sentence_twice_anchors_every_occurrence() -> None:
    """同一句写两遍：入库一条话术（按文本去重），但两处位置都必须给出来。

    只给一个位置，界面就只能亮一处，商家看到的还是"写了两遍凭什么只标一遍"。
    """
    line = "保证三个月恢复正常肤色。"
    doc = Doc(filename="d.txt", kind="text", engine="paste",
              blocks=[Block(f"{line}\n中间的说明文字若干。\n{line}")])
    pieces = split_doc(doc, "line")
    assert [p.text for p in pieces] == [line, "中间的说明文字若干。"]   # 去重保序
    anchored = pieces[0]
    assert len(anchored.spans) == 2
    assert anchored.spans[0] == (anchored.start, anchored.end)
    assert [doc.text[s:e] for s, e in anchored.spans] == [line, line]
    assert anchored.spans[1][0] > anchored.spans[0][1]   # 两处互不重叠


def test_occurrences_ignores_whitespace_differences() -> None:
    """话术里空白被压平过，整篇里却是原始换行：忽略空白才锚得上。"""
    text = "效果\n  永久"
    # 效0 果1 \n2 空3 空4 永5 久6 → 区间回到原串末尾，end 是开区间
    assert occurrences(text, "效果 永久") == [[0, 7]]
    assert occurrences(text, "查无此句") == []


def test_doc_index_maps_back_to_original_positions() -> None:
    hay, starts = doc_index(" a\nb ")
    assert hay == "ab" and starts == [1, 3]


def test_split_scripts_and_split_doc_share_one_path() -> None:
    """粘贴入口与文件入口必须切出同样的结果（含锚点），否则接口和页面对不上。"""
    text = "保证三个月恢复正常肤色\n效果永久"
    from_pieces = [p.text for p in split_doc(
        Doc(filename="", kind="text", engine="memory", blocks=[Block(text)]), "line")]
    assert from_pieces == split_scripts(text, "line")
