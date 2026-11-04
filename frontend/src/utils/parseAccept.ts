/**
 * 解析能力的前端共用逻辑：accept 列表、缺引擎提示、上传前的本地预判。
 *
 * 为什么单独一个文件：商家端「文案检查」与平台端「批量导入」要的是同一套规则，
 * 复制两份迟早会出现"一边提示未启用、另一边直接把文件发出去"的不一致。
 */
import type { Capabilities, ParseFormat } from '../api/resource'

const LABELS: Record<string, string> = {
  image: '图片 OCR', audio: '语音转写', pdf_scan: '扫描件 OCR'
}

/** 文件选择框的 accept 值。只收 available=true 的扩展名。 */
export function acceptOf(caps: Capabilities | null): string {
  return availableFormats(caps).filter(item => item.suffix !== '.md').map(item => item.suffix).join(',')
}

export function availableFormats(caps: Capabilities | null): ParseFormat[] {
  return (caps?.formats ?? []).filter(item => item.available)
}

/** 未启用的能力名，用于页面顶部的黄色提示条。 */
export function missingEnginesOf(caps: Capabilities | null): string[] {
  return Object.entries(caps?.engines ?? {}).filter(([, ok]) => !ok)
    .map(([name]) => (name === 'ocr' ? 'OCR（海报与扫描件）' : '语音转写（ASR）'))
}

export function suffixOf(name: string): string {
  const dot = name.lastIndexOf('.')
  return dot > 0 ? name.slice(dot).toLowerCase() : ''
}

/**
 * 上传前的本地预判：返回拒绝理由，null 表示可以发出去。
 *
 * el-upload 的 accept 只作用于文件选择框，拖拽时根本不过滤（Element Plus 源码如此），
 * 不拦的话一张 30MB 的 .doc 会白传一次才拿到 422，用户等半天只看一行红字。
 * 能力清单没拉到时返回 null 交给后端判——前端不瞎猜，也不假装支持。
 */
export function refuseReason(caps: Capabilities | null, name: string): string | null {
  const suffix = suffixOf(name)
  if (!suffix) return `「${name}」没有扩展名，无法判断是什么素材；请补上 .pdf/.docx/.png 等后缀`
  const formats = caps?.formats ?? []
  if (!formats.length) return null
  const hit = formats.find(item => item.suffix === suffix)
  if (!hit) {
    return `不支持 ${suffix}。当前可解析：${availableFormats(caps).map(item => item.suffix).join(' ')}`
  }
  if (!hit.available) return `${LABELS[hit.kind] ?? '该能力'}未启用：${hit.note}`
  return null
}
