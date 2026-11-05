/**
 * 商家检查页的三段状态持久化：材料 → 分段 → 结论。
 *
 * 为什么必须做：一条一条粘话术、勾选、等 6~8 秒出结论之后，刷一下页面全没了。
 * 更糟的是"看起来没了"——商家会以为自己把已入库的数据弄丢了，于是重复上传同一份素材。
 *
 * 一条不能假装的事实：**File 对象存不进 sessionStorage**。
 * 所以"材料"这一栏持久化的是文件名、大小与已入库的 source_id，
 * 恢复时明确告诉用户"文件要重新选一次，但话术和结论都在库里"，
 * 而不是悄悄丢掉文件再让他以为是自己操作失误。
 *
 * 按 client_id 分键：同一台电脑上登录过两家机构时，
 * 用 A 的分段去续 B 的结论就是把租户隔离做成样子货。
 */
import { ref } from 'vue'
import { defineStore } from 'pinia'
import type { ImportPiece } from '../api/resource'

const PREFIX = 'cg-check-draft'
const SHAPE_VERSION = 1

export interface DraftGroup {
  filename: string
  kind: string
  engine: string
  sizeBytes: number | null
  sourceId: number | null
  fullText: string
  /** 直接复用接口契约类型：在这里另抄一份字段，两边就会各自漂移，
   *  而锚点字段（source_start / source_occurrences）恰恰是最容易漏抄的那几个 */
  pieces: ImportPiece[]
  picked: number[]
}

export interface DraftResult {
  scriptId: number
  auditId: number | null
  groupIndex: number
  text: string
  score: number
  incomplete: boolean
}

interface DraftShape {
  shape: number
  clientId: number
  stage: 'input' | 'preview' | 'result'
  scene: string
  mode: string
  savedAt: string
  groups: DraftGroup[]
  results: DraftResult[]
}

const now = () => new Date().toISOString()

export const useCheckDraft = defineStore('checkDraft', () => {
  const stage = ref<DraftShape['stage']>('input')
  const scene = ref('')
  const mode = ref('blank')
  const groups = ref<DraftGroup[]>([])
  const results = ref<DraftResult[]>([])
  const savedAt = ref<string | null>(null)
  const restored = ref(false)
  // 恢复出来的分组缺文件本体，界面必须区分"这是历史草稿"与"我刚传的"
  const needsReupload = ref(false)
  let owner = 0

  function keyOf(clientId: number) {
    return `${PREFIX}.${clientId}`
  }

  /** 只有非空且不超限才写：把 2MB 配额塞满会让用户下次登录连别的草稿都存不进。 */
  function persist(clientId: number) {
    if (!clientId) return
    owner = clientId
    const shape: DraftShape = {
      shape: SHAPE_VERSION, clientId, stage: stage.value, scene: scene.value,
      mode: mode.value, savedAt: now(), groups: groups.value, results: results.value
    }
    if (!groups.value.length && !results.value.length) {
      sessionStorage.removeItem(keyOf(clientId))
      savedAt.value = null
      return
    }
    try {
      sessionStorage.setItem(keyOf(clientId), JSON.stringify(shape))
      savedAt.value = shape.savedAt
    } catch {
      // 配额满或隐私模式禁用存储：丢弃草稿可以接受，但必须告知，
      // 否则用户以为"已经保存了"，刷新才发现全丢
      sessionStorage.removeItem(keyOf(clientId))
      savedAt.value = null
    }
  }

  function restore(clientId: number) {
    const raw = sessionStorage.getItem(keyOf(clientId))
    restored.value = false
    needsReupload.value = false
    if (!raw) return false
    let shape: DraftShape
    try {
      shape = JSON.parse(raw) as DraftShape
    } catch {
      sessionStorage.removeItem(keyOf(clientId))
      return false
    }
    if (shape.shape !== SHAPE_VERSION || shape.clientId !== clientId) {
      // 结构变了或归属不对就直接丢弃：拿旧 schema 或别的机构的数据渲染，
      // 比丢一次草稿危险得多
      sessionStorage.removeItem(keyOf(clientId))
      return false
    }
    stage.value = shape.stage
    scene.value = shape.scene
    mode.value = shape.mode
    groups.value = shape.groups
    results.value = shape.results
    savedAt.value = shape.savedAt
    owner = clientId
    restored.value = true
    needsReupload.value = shape.groups.some(group => !group.sourceId)
    return true
  }

  /** 显式清除：只由用户点"清空本次草稿"触发，绝不在页面卸载时自动删。 */
  function clear() {
    if (owner) sessionStorage.removeItem(keyOf(owner))
    stage.value = 'input'
    scene.value = ''
    mode.value = 'blank'
    groups.value = []
    results.value = []
    savedAt.value = null
    restored.value = false
    needsReupload.value = false
  }

  function remember(clientId: number, input: {
    stage: DraftShape['stage']; scene: string; mode: string
    groups: DraftGroup[]; results: DraftResult[]
  }) {
    stage.value = input.stage
    scene.value = input.scene
    mode.value = input.mode
    groups.value = input.groups
    results.value = input.results
    persist(clientId)
  }

  return { stage, scene, mode, groups, results, savedAt, restored, needsReupload,
           persist, restore, clear, remember }
})
