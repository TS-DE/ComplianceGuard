/**
 * 忽略空白的子串定位。
 *
 * 为什么不能直接 indexOf：
 * 解析层切出的话术经过两步改写——剥行首序号（`1.` / `（1）` / `一、`）与压平换行
 * （段内 `\n` 变空格）。所以"话术文本"往往**不是整篇原文的字面子串**，
 * 直接 indexOf 会在最需要它的地方返回 -1，界面就成了"找不到位置"。
 *
 * 做法：把原文里所有非空白字符抽成一个匹配串，同时记住每个字符在原文里的真实下标；
 * 匹配串命中后用这张表换算回原文区间。命中的是"内容相同"，位置给的是"原文真实下标"。
 *
 * 定位失败必须原样上报（返回 null），不允许退化成"猜一个位置"——
 * 指错位置比指不出位置更坏：商家会以为系统在他的正文里找到了根本没写过的话。
 */
export interface Span { start: number; end: number }

/** 取原文的下标映射表：stripped 为去空白后的串，map[i] 是它在原文中的真实下标。 */
function stripIndex(text: string): { stripped: string; map: number[] } {
  const map: number[] = []
  const chars: string[] = []
  for (let i = 0; i < text.length; i += 1) {
    if (!/\s/.test(text[i])) {
      chars.push(text[i])
      map.push(i)
    }
  }
  return { stripped: chars.join(''), map }
}

/**
 * 在 hay 中定位 needle（忽略空白差异），返回 hay 的真实区间。
 * `from` 是"从原文第几个字符之后找"：调用方按话术顺序推进游标，
 * 否则短句 "术后零风险" 会被定位到长句 "术后零风险 全城最低价" 的开头，
 * 界面就变成"看起来指了，其实指错了"——比不指更坏。
 * 命中多个时取 from 之后的第一个；去空白后为空则视为定位失败。
 */
export function locate(hay: string, needle: string, from = 0): Span | null {
  if (!hay || !needle) return null
  const { stripped, map } = stripIndex(hay)
  const target = needle.replace(/\s+/g, '')
  if (!target) return null
  // stripped 下标与原文下标不同，先把 from 换算成 stripped 里的起点
  let start = 0
  while (start < map.length && map[start] < from) start += 1
  const at = stripped.indexOf(target, start)
  if (at < 0) return null
  return { start: map[at], end: map[at + target.length - 1] + 1 }
}

/**
 * 命中片段的原文区间：先把一条话术定位到整篇里，再在**这段话术自己的范围内**找片段。
 *
 * 为什么要分两级：同一个词（如"保证"）会在多条话术里重复出现，
 * 直接在整篇里找会全部命中第一处，右侧第 5 条点亮却滚到第 1 条的位置。
 * 传入的 `cursor` 是这条话术在整篇里的搜索起点，返回的 `nextCursor` 要交给下一条用。
 */
export function locateInSource(
  fullText: string, pieceText: string, quote: string,
  cursor = 0
): { piece: Span; quote: Span; nextCursor: number } | null {
  const piece = locate(fullText, pieceText, cursor)
  if (!piece) return null
  const region = fullText.slice(piece.start, piece.end)
  const found = locate(region, quote)
  if (!found) return null
  return {
    piece,
    quote: { start: piece.start + found.start, end: piece.start + found.end },
    nextCursor: piece.end
  }
}

/** 取上下文：命中前后各若干字，用于"这条到底出现在哪句话里"的可读核对。 */
export function contextOf(text: string, span: Span, around = 20): { before: string; after: string } {
  const before = text.slice(Math.max(0, span.start - around), span.start)
  const after = text.slice(span.end, Math.min(text.length, span.end + around))
  return { before, after }
}
