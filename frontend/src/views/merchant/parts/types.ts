/**
 * 商家检查页的展示模型。
 *
 * 单独成文件而不是塞在 SFC 里：页面（编排层）与右栏（展示层）都要用同一套类型，
 * 放在任何一方都会出现"另一方反过来 import 组件"的怪依赖。
 *
 * 这些类型是**后端契约的展示层投影**，字段名沿用 api_spec，只多不减：
 * `HitRender.context` 是前端算出来的原文上下文，后端不返回这个字段。
 */
import type { HitView } from '../../../utils/risk'

export interface HitRender {
  key: string
  view: HitView
  /** 原文上下文；null 表示这条没定位成功 */
  context: { before: string; after: string } | null
  /** 文档级区间：给左栏画高亮用；没定位上就是 undefined（不猜位置） */
  span?: { start: number; end: number }
  /**
   * 同一句话在原文别处的出现位置。服务端去重是按文本入库的（一句话只建一条记录），
   * 但原文里两处都还在——只亮一处，商家看到的就是"我写了两遍凭什么只标一遍"。
   */
  extra?: Array<{ start: number; end: number }>
}

export interface ResultRow {
  scriptId: number
  /** 属于哪一份素材：多文件上传时两个栏都要按这个切换 */
  groupIndex: number
  auditId: number | null
  text: string
  ref: string | null
  confidence: number | string | null
  score: number
  incomplete: boolean
  error?: string | null
  latencyMs: number | null
  cost: string | null
  hits: HitRender[]
  /** 定位失败的引文：必须显示出来，不能静默 */
  unlocated: string[]
  sourceLabel: string
}

export interface RewriteState {
  busy?: boolean
  /** 已等待秒数：改写是最容易长时间不返回的一步，不给数字用户只能靠猜 */
  elapsed?: number
  /** 停止等待的句柄；null 表示当前没有在等 */
  cancel?: (() => void) | null
  error?: string | null
  before?: string
  after?: string
  passed?: boolean | null
  recheckScore?: number | null
}
