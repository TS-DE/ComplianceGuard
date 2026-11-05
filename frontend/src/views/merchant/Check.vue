<script setup lang="ts">
/**
 * 文案检查工作台：喂素材 → 对着原文核对切分 → 逐条判定 → 看证据、采纳改写。
 *
 * 这一版冲着三条真实抱怨改：
 * · 「切分把内容按标点切碎，只能一条条对着找，不知道在原文哪个位置」
 *   → 左栏永远是整篇原文，右栏每条都能定位回原文并滚动过去。
 * · 「明细里只有 ID 和切片」→ 命中卡固定四件事：片段±20字上下文、法条原文、判定理由、风险等级。
 * · 「主按钮离内容太远，长文档要滚到底」→ 工具条 sticky，步骤条本身可点回任意一步。
 *
 * 保留的既有设计（都是踩坑换来的，不能随重构丢掉）：
 * · 一次可喂多份文件，解析按顺序跑（OCR 吃 CPU，并发只会互相抢核心且看不出进度）；
 * · 预览一行都不写库；勾选只提交人工确认过的条目；
 * · 每份素材各自 commit、审查按 20 条分批（后端上限）；
 * · accept 与"未启用能力"提示一律来自后端能力清单。
 *
 * 两条不肯让步的边界：定位失败就写"位置未知"并列出引文，绝不猜位置；
 * 主题只显示"解析首行摘录（非模型提炼）"，没有可靠来源就显示未启用。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { UploadUserFile } from 'element-plus'
import {
  importScripts, auditBatch, parseCapabilities, axisLabel,
  type BatchAuditItem, type Capabilities, type Hit, type ImportPiece
} from '../../api/resource'
import { useAuth } from '../../stores/auth'
import { isCanceled } from '../../api/http'
import { acceptOf, missingEnginesOf, refuseReason } from '../../utils/parseAccept'
import { contextOf, locate, locateInSource } from '../../utils/locate'
import type { HitView } from '../../utils/risk'
import StepProgress from '../../components/layout/StepProgress.vue'
import SourceText from '../../components/text/SourceText.vue'
import type { Mark } from '../../components/text/marks'
import AuditResults from './parts/AuditResults.vue'
import ResultPane from './parts/ResultPane.vue'
import SourceDrawer from './parts/SourceDrawer.vue'
import type { HitRender, ResultRow } from './parts/types'

interface Chunk {
  scriptId: number; text: string
  ref: string | null; confidence: number | string | null
  /**
   * 这条话术在素材里的锚点（绝对偏移 + 全部出现位置）。
   * 带上整条 ImportPiece 而不是只带偏移数字：定位失败时界面要能区分
   * "服务端说没有锚点"与"前端模糊搜索没搜到"，两者的下一步动作不一样。
   */
  piece: ImportPiece
}

interface Group {
  key: string; filename: string; kind: string; engine: string
  confidence: number | null; warnings: string[]; fullText: string
  pieces: ImportPiece[]; file: File | null; text: string | null
  picked: Set<number>; sourceId: number | null; error: string | null; chunks: Chunk[]
}

const auth = useAuth()
const tab = ref<'paste' | 'file'>('paste')
const scene = ref('')
const mode = ref('blank')
const text = ref('')
const fileList = ref<UploadUserFile[]>([])
const caps = ref<Capabilities | null>(null)
const groups = ref<Group[]>([])
const activeGroup = ref(0)
const stage = ref<'input' | 'preview' | 'result'>('input')
const parsing = ref(false)
const checking = ref(false)
const progress = ref('')
// 一次运行一个 AbortController。用 let 而不是 ref：它不参与渲染，
// 放进响应式只会在每次点"停止"时多触发一轮无意义的更新。
let runController: AbortController | null = null
// 已耗时秒数：没有它，"6 秒的正常审查"和"10 分钟的假死"在界面上长得一模一样
const elapsed = ref(0)
const rows = ref<ResultRow[]>([])
const rawResults = ref<BatchAuditItem[]>([])
const activeKey = ref<string | null>(null)
const showTable = ref(false)
const drawerOpen = ref(false)
const drawerId = ref<number | null>(null)

const clientId = computed(() => auth.user?.client_id ?? 0)
const MODE_LABELS: Record<string, string> = {
  blank: '按空行（一段一条）', line: '按行（一行一条）', sentence: '按句（语音/连排）'
}
const modes = computed(() => caps.value?.modes ?? ['blank', 'line'])
const accept = computed(() => acceptOf(caps.value))
const missingEngines = computed(() => missingEnginesOf(caps.value))
const pickedCount = computed(() => groups.value.reduce((sum, g) => sum + g.picked.size, 0))
const current = computed(() => groups.value[activeGroup.value] ?? null)
const currentRows = computed(() => rows.value.filter(row => row.groupIndex === activeGroup.value))
/** 主题线索只取解析结果的首行摘录并写明"非模型提炼"——没有可靠来源就不装。 */
const topicHint = computed(() => {
  const line = (current.value?.fullText ?? '').split('\n').find(item => item.trim().length > 3)
  return line ? line.trim().slice(0, 40) : null
})
const steps = [
  { key: 'input', label: '喂素材' },
  { key: 'preview', label: '核对切分' },
  { key: 'result', label: '看结论' }
]

/**
 * 一条话术在整篇里的区间：服务端锚点优先，模糊定位只当兜底。
 *
 * `source_start/source_end` 是解析层按块算好的绝对区间，同一句出现两次时各自不同，
 * 所以走锚点这条路不需要游标；只有老数据（手工录入、没有锚点）才退回 locate，
 * 那时才需要按顺序推进游标，否则短句会被定位到同前缀的长句上。
 */
function pieceSpan(fullText: string, piece: ImportPiece, cursor: number):
  { start: number; end: number } | null {
  if (typeof piece.source_start === 'number' && typeof piece.source_end === 'number') {
    return { start: piece.source_start, end: piece.source_end }
  }
  return locate(fullText, piece.text, cursor)
}

/** 这句话在整篇里的全部出现区间；没有锚点时退化成"只有一处"。 */
function pieceRegions(fullText: string, piece: ImportPiece,
                      cursor: number): Array<{ start: number; end: number }> {
  if (piece.source_occurrences?.length) {
    return piece.source_occurrences.map(([start, end]) => ({ start, end }))
  }
  const span = pieceSpan(fullText, piece, cursor)
  return span ? [span] : []
}

/**
 * 左栏标记。
 * 预览阶段画"切分边界"（中性描边，不是风险色，否则预览看起来像已经判过）；
 * 结果阶段画命中区间，降级的命中一律显示为赭黄而不是朱红。
 */
const marks = computed<Mark[]>(() => {
  const group = current.value
  if (!group) return []
  const out: Mark[] = []
  if (stage.value === 'preview') {
    let cursor = 0
    for (const pickIndex of [...group.picked].sort((a, b) => a - b)) {
      const regions = pieceRegions(group.fullText, group.pieces[pickIndex], cursor)
      if (regions.length) cursor = regions[regions.length - 1].end
      // 一个都定位不到就不画边界：宁缺毋错，画错位置会让人以为系统在他正文里指错了话
      regions.forEach((span, at) => out.push({
        key: `p-${pickIndex}-${at}`, start: span.start, end: span.end, severity: 'piece'
      }))
    }
    return out
  }
  for (const row of currentRows.value) {
    for (const hit of row.hits) {
      if (!hit.span) continue
      const severity = hit.view.downgraded ? 'soft' : hit.view.severity
      out.push({ key: hit.key, start: hit.span.start, end: hit.span.end, severity })
      // 同一句话在别处也出现过，那些位置一起亮：只标一处会让商家以为系统没看见第二遍
      ;(hit.extra ?? []).forEach((span, at) => out.push({
        key: `${hit.key}-x${at}`, start: span.start, end: span.end, severity
      }))
    }
  }
  return out
})

function buildForm(commit: boolean, group: { file: File | null; text: string | null },
                   items: string[]): FormData {
  const form = new FormData()
  form.append('client_id', String(clientId.value))
  form.append('scene', scene.value)
  form.append('mode', mode.value)
  form.append('commit', commit ? 'true' : 'false')
  if (commit) form.append('items', JSON.stringify(items))
  if (group.file) form.append('file', group.file)
  else form.append('text', group.text ?? '')
  return form
}

function blankGroup(key: string, file: File | null, pasted: string | null): Group {
  return {
    key, filename: file?.name ?? '粘贴内容', kind: '-', engine: '-', confidence: null,
    warnings: [], fullText: '', pieces: [], file, text: pasted, picked: new Set(),
    sourceId: null, error: null, chunks: []
  }
}

/** 单份素材 → 一个分组；失败也留分组，原因原样写上去（不静默丢文件）。 */
async function parseOne(file: File | null, pasted: string | null, key: string): Promise<Group> {
  const base = blankGroup(key, file, pasted)
  // 拖拽不受 accept 约束（Element Plus 只在选择框上过滤），所以发请求前先本地判一次
  if (file) {
    const reason = refuseReason(caps.value, file.name)
    if (reason) return { ...base, error: reason }
  }
  try {
    const result = await importScripts(buildForm(false, { file, text: pasted }, []))
    return {
      ...base, filename: file?.name ?? result.filename ?? '粘贴内容',
      kind: result.kind, engine: result.engine, confidence: result.confidence,
      warnings: result.warnings ?? [], fullText: result.full_text ?? '',
      pieces: result.items_detail, picked: new Set(result.items_detail.map((_, i) => i))
    }
  } catch (error: unknown) {
    return { ...base, error: error instanceof Error ? error.message : '解析失败' }
  }
}

async function preview() {
  if (!clientId.value) { ElMessage.error('账号未绑定机构，请重新登录'); return }
  // el-upload 的 raw 是 File 的超集（多带 uid），FormData 只需要 File 那套接口
  const files = fileList.value.flatMap(item => (item.raw ? [item.raw as unknown as File] : []))
  if (tab.value === 'file' && !files.length) { ElMessage.warning('请先选择文件'); return }
  if (tab.value === 'paste' && !text.value.trim()) { ElMessage.warning('请粘贴文案'); return }
  parsing.value = true
  rows.value = []
  groups.value = []
  try {
    const queue: (File | null)[] = tab.value === 'file' ? files : [null]
    for (let index = 0; index < queue.length; index += 1) {
      progress.value = `解析中 ${index + 1}/${queue.length}…`
      const item = queue[index] ?? null
      groups.value.push(await parseOne(item, item ? null : text.value, `g-${index}`))
    }
    activeGroup.value = 0
    stage.value = 'preview'
    const failed = groups.value.filter(group => group.error).length
    const pieces = groups.value.reduce((sum, group) => sum + group.pieces.length, 0)
    if (!pieces) ElMessage.warning(failed ? '有文件没解析出话术，原因见分组提示' : '没有切出有效话术，换个切分方式试试')
    else if (failed) ElMessage.warning(`${failed} 份解析失败，其余 ${groups.value.length - failed} 份可继续`)
  } finally {
    parsing.value = false
    progress.value = ''
  }
}

/**
 * 后端命中 → 展示模型。定位在这一步完成，定位不到就标失败，不猜位置。
 *
 * `cursors` 按素材顺序推进：话术是依次入库的，下一条只应在上一条之后找。
 * 不加这个游标，短句会被定位到内容更长的同前缀话术上——位置看着指了，其实指错。
 */
const cursors = new Map<number, number>()

function toHit(groupIndex: number, fullText: string, piece: ImportPiece, scriptId: number,
               index: number, hit: Hit): HitRender {
  const quote = hit.original_quote ?? hit.quote
  const anchorStart = typeof piece.source_start === 'number' ? piece.source_start : null
  const regions = pieceRegions(fullText, piece, cursors.get(groupIndex) ?? 0)
  // 引文只在**这句话术自己的区间**里找：整篇搜会让右侧第 5 条点亮、左栏滚到第 1 条
  const inside = regions.map((region) => {
    const found = locate(fullText.slice(region.start, region.end), quote)
    return found
      ? { start: region.start + found.start, end: region.start + found.end, own: region.start === anchorStart }
      : null
  }).filter((item): item is { start: number; end: number; own: boolean } => item !== null)
  let spans = inside
  if (!spans.length) {
    // 没有服务端锚点（手工录入的老数据）才退回整篇模糊定位，并如实推进游标
    const located = locateInSource(fullText, piece.text, quote, cursors.get(groupIndex) ?? 0)
    if (located) {
      cursors.set(groupIndex, located.nextCursor)
      spans = [{ start: located.quote.start, end: located.quote.end, own: true }]
    }
  }
  const primary = spans.find(item => item.own) ?? spans[0] ?? null
  const others = spans.filter(item => item !== primary)
  const view: HitView = {
    key: `${scriptId}-${index}`, axis: hit.axis, axisLabel: axisLabel(hit.axis),
    lawArticle: hit.law_article, itemNo: hit.item_no ?? null, quote,
    reason: hit.reason ?? null, severity: hit.severity ?? 'hard',
    downgraded: Boolean(hit.downgraded), downgradeReason: hit.downgrade_reason ?? null,
    detector: hit.detector ?? null
  }
  return {
    key: view.key, view, span: primary ?? undefined,
    extra: others.map(({ start, end }) => ({ start, end })),
    context: primary ? contextOf(fullText, primary) : null
  }
}

/** 勾选条目 → 每份素材各一次入库 → 分批审查（后端一次最多 20 条）→ 组装双栏数据。 */
async function runCheck() {
  if (!pickedCount.value) { ElMessage.warning('至少勾选一条'); return }
  checking.value = true
  runController = new AbortController()
  const signal = runController.signal
  rows.value = []
  rawResults.value = []
  const index = new Map<number, { group: Group; chunk: Chunk }>()
  try {
    const ready = groups.value.filter(group => group.picked.size)
    for (let gi = 0; gi < ready.length; gi += 1) {
      const group = ready[gi]
      progress.value = `入库 ${gi + 1}/${ready.length}：${group.filename}`
      const pickedIndexes = [...group.picked].sort((a, b) => a - b)
      const items = pickedIndexes.map(pi => group.pieces[pi].text)
      const saved = await importScripts(buildForm(true, group, items))
      group.sourceId = saved.source_id ?? null
      // 提交响应里的 items_detail 带 script_id：锚点优先信服务端刚算的这份，
      // 预览那份只当兜底（老服务端不返回 script_id 时仍能工作）
      const anchors = new Map<number, ImportPiece>()
      ;(saved.items_detail ?? []).forEach(piece => {
        if (typeof piece.script_id === 'number') anchors.set(piece.script_id, piece)
      })
      group.chunks = saved.script_ids.map((scriptId, position) => ({
        scriptId, text: items[position],
        ref: group.pieces[pickedIndexes[position]].ref,
        confidence: group.pieces[pickedIndexes[position]].confidence,
        piece: anchors.get(scriptId) ?? group.pieces[pickedIndexes[position]]
      }))
      group.chunks.forEach(chunk => index.set(chunk.scriptId, { group, chunk }))
    }
    const ids = [...index.keys()]
    const results: BatchAuditItem[] = []
    for (let start = 0; start < ids.length; start += 20) {
      const batchIds = ids.slice(start, start + 20)
      elapsed.value = 0
      const timer = setInterval(() => { elapsed.value += 1 }, 1000)
      progress.value = `检查中 ${Math.min(start + 20, ids.length)}/${ids.length}，每条约 6 秒…`
      try {
        const batch = await auditBatch(clientId.value, batchIds, signal)
        results.push(...batch.results)
      } finally {
        clearInterval(timer)
      }
    }
    rawResults.value = results
    cursors.clear()
    rows.value = results.map(item => {
      const entry = index.get(item.script_id)
      const group = entry?.group
      const chunk = entry?.chunk
      const groupIndex = group ? groups.value.indexOf(group) : 0
      const hits = (item.hits ?? []).map((hit, hitIndex) => (group && chunk
        ? toHit(groupIndex, group.fullText, chunk.piece, item.script_id, hitIndex, hit)
        : { key: `${item.script_id}-${hitIndex}`, view: {} as HitView, context: null }))
      return {
        scriptId: item.script_id,
        groupIndex,
        auditId: item.audit_id ?? null,
        text: chunk?.text ?? '', ref: chunk?.ref ?? null,
        confidence: chunk?.confidence ?? null,
        score: item.score, incomplete: Boolean(item.incomplete), error: item.error ?? null,
        latencyMs: item.latency_ms ?? null, cost: item.cost ?? null,
        hits, unlocated: hits.filter(hit => !hit.span).map(hit => hit.view.quote),
        sourceLabel: group?.filename ?? '—'
      } satisfies ResultRow
    })
    stage.value = 'result'
    const bad = results.filter(item => !item.error && item.score === 0).length
    ElMessage.success(`已检查 ${results.length} 条，其中 ${bad} 条需要修改`)
  } catch (error: unknown) {
    // 取消要单独说：静默吞掉的话，用户看到的是"点了没反应"，比报错更让人怀疑系统坏了。
    // 后端那一次仍然会跑完（同步任务没有服务端取消钩子），所以措辞是"已停止等待"，
    // 不谎称"已终止"。
    if (isCanceled(error)) ElMessage.info('已停止等待，可重新发起检查')
    // 其他失败不伪造结果：已入库的部分在「我的资产」里仍然能看到
  } finally {
    checking.value = false
    runController = null
    progress.value = ''
  }
}

/** 停止等待：只断开这次的连接，不动已入库的数据。 */
function cancelChecking() {
  runController?.abort()
}

function toggle(index: number) {
  const group = current.value
  if (!group) return
  const next = new Set(group.picked)
  if (next.has(index)) next.delete(index)
  else next.add(index)
  group.picked = next
}

/** 左栏点击：预览阶段点切分边界 → 改勾选；结果阶段点命中 → 与右栏联动。 */
function onPick(key: string) {
  if (stage.value === 'preview' && key.startsWith('p-')) {
    toggle(Number(key.slice(2)))
    return
  }
  activeKey.value = activeKey.value === key ? null : key
}

function goStage(key: string) {
  if (key === 'input') { stage.value = 'input'; return }
  if (key === 'preview' && groups.value.length) { stage.value = 'preview'; return }
  if (key === 'result' && rows.value.length) stage.value = 'result'
}

function selectGroup(value: number) {
  activeGroup.value = value
  activeKey.value = null
}

onMounted(async () => {
  try {
    caps.value = await parseCapabilities()
    if (!caps.value.modes.includes(mode.value)) mode.value = caps.value.modes[0]
  } catch {
    // 能力清单拿不到就退回最保守的两种切分方式，不让页面打不开
  }
})
</script>

<template>
  <div class="work">
    <div class="toolbar">
      <StepProgress :steps="steps" :current="stage"
                    :done="stage === 'result' ? ['input', 'preview'] : stage === 'preview' ? ['input'] : []"
                    @go="goStage" />
      <div class="tools">
        <el-radio-group v-if="groups.length > 1" :model-value="activeGroup" size="small"
                        @change="selectGroup($event as number)">
          <el-radio-button v-for="(group, pos) in groups" :key="group.key" :value="pos">
            {{ group.filename }}
          </el-radio-button>
        </el-radio-group>
        <el-button v-if="current?.sourceId" size="small"
                   @click="drawerId = current.sourceId; drawerOpen = true">看原始素材</el-button>
        <el-button v-if="stage === 'result' && rawResults.length" size="small"
                   @click="showTable = !showTable">
          {{ showTable ? '收起汇总表' : '看汇总表' }}
        </el-button>
      </div>
    </div>

    <el-alert v-if="missingEngines.length" type="warning" :closable="false" show-icon
              :title="`以下能力当前未启用：${missingEngines.join('、')}`">
      <p class="cg-muted">对应格式传上来会被直接拒绝并说明装什么，界面不假装支持（安装命令见 RUNBOOK §6）。</p>
    </el-alert>

    <section v-if="stage === 'input'" class="card">
      <el-form label-width="86px">
        <el-form-item label="场景">
          <el-input v-model="scene" maxlength="50" style="width: 260px" placeholder="可选，如 双眼皮 / 热玛吉" />
        </el-form-item>
        <el-form-item label="切分方式">
          <el-radio-group v-model="mode">
            <el-radio-button v-for="item in modes" :key="item" :value="item">
              {{ MODE_LABELS[item] ?? item }}
            </el-radio-button>
          </el-radio-group>
          <span class="cg-muted inline">行首序号会自动去掉；录音请用「按句」</span>
        </el-form-item>
      </el-form>

      <el-tabs v-model="tab">
        <el-tab-pane label="粘贴文本" name="paste">
          <el-input v-model="text" type="textarea" :rows="8" maxlength="20000" show-word-limit
                    placeholder="把整篇文案粘进来" />
        </el-tab-pane>
        <el-tab-pane label="上传文件（可多选）" name="file">
          <el-upload drag multiple :auto-upload="false" v-model:file-list="fileList" :accept="accept">
            <div class="drop">
              <p>把海报、PDF、话术表、录音拖进来，或<span class="link">点击选择</span></p>
              <p class="cg-muted">{{ accept || '后端未提供能力清单' }}</p>
            </div>
            <template #tip>
              <p class="cg-muted">可一次多选；解析按顺序跑，一份失败不影响其余。</p>
            </template>
          </el-upload>
        </el-tab-pane>
      </el-tabs>

      <el-button type="primary" :loading="parsing" @click="preview">
        {{ parsing && progress ? progress : '解析并对到原文' }}
      </el-button>
    </section>

    <div v-else class="split">
      <SourceText :text="current?.fullText ?? ''" :marks="marks" :active-key="activeKey"
                  :title-hint="topicHint" :unlocated="[]" @pick="onPick" />

      <div class="right">
        <div v-if="stage === 'preview'" class="card">
          <p class="cg-muted">左栏是整篇原文：点原文段落或下面的行都能取消勾选，切错的先剔掉再入库。</p>
          <p v-if="current?.error" class="err">{{ current.error }}</p>
          <p v-for="warn in current?.warnings ?? []" :key="warn" class="warn">{{ warn }}</p>
          <div class="list">
            <div v-for="(piece, index) in current?.pieces ?? []" :key="index" class="row"
                 :class="{ on: current?.picked.has(index) }">
              <el-checkbox :model-value="current?.picked.has(index) ?? false" @change="toggle(index)" />
              <span class="idx">{{ index + 1 }}</span>
              <span class="body">{{ piece.text }}</span>
              <span class="src">
                <el-tag v-if="piece.ref" size="small" type="info" effect="plain">{{ piece.ref }}</el-tag>
                <el-tag v-if="piece.confidence !== null" size="small" effect="plain"
                        :type="piece.confidence < 0.6 ? 'warning' : 'info'">
                  {{ Math.round(piece.confidence * 100) }}%
                </el-tag>
              </span>
            </div>
          </div>
          <el-button type="primary" :loading="checking" :disabled="!pickedCount" @click="runCheck">
            {{ checking && progress ? `${progress}（已 ${elapsed} 秒）` : `检查这 ${pickedCount} 条` }}
          </el-button>
          <!-- 取消不是"关掉请求就完事"：后端这一次还会跑完，所以按钮写"停止等待"，
               并明确告诉用户已经入库的话术仍在「我的档案」里，避免他以为数据丢了 -->
          <el-button v-if="checking" plain @click="cancelChecking">停止等待</el-button>
          <p class="cg-muted">顺序执行，单条约 6 秒；超过 20 条自动分批跑完。</p>
        </div>

        <ResultPane v-else class="grow" :rows="currentRows" :active-key="activeKey"
                    @locate="key => activeKey = key" />

        <AuditResults v-if="showTable && rawResults.length" :items="rawResults" />
      </div>
    </div>

    <SourceDrawer v-model="drawerOpen" :source-id="drawerId" />
  </div>
</template>

<style scoped>
.work { display: flex; flex-direction: column; gap: var(--cg-s-3); }
.toolbar {
  position: sticky; top: 0; z-index: 5; display: flex; flex-direction: column; gap: var(--cg-s-2);
  background: var(--cg-paper); padding-bottom: var(--cg-s-2);
}
.tools { display: flex; align-items: center; gap: var(--cg-s-2); flex-wrap: wrap; }
.card { background: var(--cg-sheet); border: var(--cg-line); border-radius: var(--cg-radius);
  padding: var(--cg-s-3); }
.inline { margin-left: var(--cg-s-2); }
.drop { padding: var(--cg-s-3); text-align: center; }
.drop p { margin: 4px 0; }
.link { color: var(--cg-accent); text-decoration: underline; cursor: pointer; }

/* 双栏：桌面优先，1280 以下退成上下，不横向挤压 */
.split { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: var(--cg-s-3); height: calc(100vh - 216px); min-height: 460px; }
.right { display: flex; flex-direction: column; gap: var(--cg-s-2); min-height: 0; overflow: auto; }
.grow { flex: 1; min-height: 0; }
@media (max-width: 1280px) {
  .split { grid-template-columns: minmax(0, 1fr); height: auto; }
  .right { overflow: visible; }
}

.list { max-height: 300px; overflow-y: auto; border: var(--cg-line);
  border-radius: var(--cg-radius); margin: var(--cg-s-2) 0 var(--cg-s-3); }
.row { display: flex; align-items: flex-start; gap: var(--cg-s-2); padding: 8px var(--cg-s-3);
  border-bottom: var(--cg-line); }
.row:last-child { border-bottom: none; }
.row.on { background: var(--cg-accent-soft); }
.idx { min-width: 22px; color: var(--cg-ink-mute); font-family: var(--cg-font-num); }
.body { flex: 1; line-height: 1.7; word-break: break-word; }
.src { display: flex; gap: 6px; flex: none; }
.err { font-size: var(--cg-t-aux); color: var(--cg-hard); }
.warn { font-size: var(--cg-t-aux); color: var(--cg-pending); background: var(--cg-pending-bg);
  padding: 6px 8px; border-radius: var(--cg-radius); }
</style>
