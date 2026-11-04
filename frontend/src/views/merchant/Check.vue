<script setup lang="ts">
/**
 * 文案检查：商家端主入口，一条链路走完「喂素材 → 切分预览 → 勾选入库 → 逐条审查」。
 *
 * 三个刻意的设计：
 * 1) 一次可以喂多份文件。商家手里的从来不只一张海报，逐个传太蠢；
 *    解析按文件顺序跑（OCR 吃 CPU，并发只会互相抢核心，还看不出进度）。
 * 2) 预览与入库分离，且预览**一行都不写**：切分不可能百分百正确，
 *    一键写库等于让脏数据污染之后所有审计统计。
 * 3) 每条话术显示它是从哪来的（第几页 / OCR 第几块 / 语音第几句）与识别置信度。
 *    商家核对时问的就是这句，不给位置等于让人对着黑盒猜。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { UploadUserFile } from 'element-plus'
import {
  importScripts, auditBatch, parseCapabilities,
  type BatchAuditItem, type Capabilities, type ImportPiece
} from '../../api/resource'
import { useAuth } from '../../stores/auth'
import { acceptOf, missingEnginesOf, refuseReason } from '../../utils/parseAccept'
import AuditResults from './AuditResults.vue'
import SourceDrawer from './SourceDrawer.vue'

interface Group {
  key: string
  filename: string
  kind: string
  engine: string
  confidence: number | null
  warnings: string[]
  pieces: ImportPiece[]
  file: File | null
  text: string | null
  picked: Set<number>
  scriptIds: number[]
  sourceId: number | null
  error: string | null
}

const router = useRouter()
const auth = useAuth()

const tab = ref<'paste' | 'file'>('paste')
const scene = ref('')
const mode = ref('blank')
const text = ref('')
const fileList = ref<UploadUserFile[]>([])
const groups = ref<Group[]>([])
const parsing = ref(false)
const checking = ref(false)
const progress = ref('')
const results = ref<BatchAuditItem[]>([])
const caps = ref<Capabilities | null>(null)
// 两个"展开"是不同东西：expanded 展开某条的违规明细；drawer 打开那份素材的原始档案
const expanded = ref<number | null>(null)
const drawerOpen = ref(false)
const drawerId = ref<number | null>(null)

const clientId = computed(() => auth.user?.client_id ?? 0)
const MODE_LABELS: Record<string, string> = {
  blank: '按空行（一段一条）', line: '按行（一行一条）', sentence: '按句（语音/连排）'
}
const modes = computed(() => caps.value?.modes ?? ['blank', 'line'])
/** accept 与"未启用能力"提示都取自后端能力清单（utils/parseAccept）：
 *  手写清单一定会和代码不同步，不同步的结果是用户传上来才知道"其实不支持"。 */
const accept = computed(() => acceptOf(caps.value))
const missingEngines = computed(() => missingEnginesOf(caps.value))
const pickedCount = computed(() => groups.value.reduce((sum, g) => sum + g.picked.size, 0))

/** 置信度显示为百分比；null 表示来自文本层，不存在识别误差（不是 0%）。 */
const conf = (value: number | null) => (value === null ? null : `${Math.round(value * 100)}%`)

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

/** 单份素材 → 一个预览分组；失败也留分组，原因原样写上去（不静默丢文件）。 */
async function parseOne(file: File | null, pasted: string | null, key: string): Promise<Group> {
  if (file) {
    const reason = refuseReason(caps.value, file.name)
    if (reason) {
      return {
        key, filename: file.name, kind: '-', engine: '-', confidence: null, warnings: [],
        pieces: [], file, text: null, picked: new Set(), scriptIds: [], sourceId: null, error: reason
      }
    }
  }
  const form = buildForm(false, { file, text: pasted }, [])
  try {
    const result = await importScripts(form)
    const picked = new Set(result.items_detail.map((_, index) => index))
    return {
      key, filename: file?.name ?? '粘贴内容', kind: result.kind, engine: result.engine,
      confidence: result.confidence, warnings: result.warnings ?? [],
      pieces: result.items_detail, file, text: pasted, picked, scriptIds: [],
      sourceId: null, error: null
    }
  } catch (error: unknown) {
    return {
      key, filename: file?.name ?? '粘贴内容', kind: '-', engine: '-',
      confidence: null, warnings: [], pieces: [], file, text: pasted,
      picked: new Set(), scriptIds: [], sourceId: null,
      error: error instanceof Error ? error.message : '解析失败'
    }
  }
}

async function preview() {
  if (!clientId.value) { ElMessage.error('账号未绑定机构，请重新登录'); return }
  // el-upload 的 raw 是 File 的超集（多带一个 uid），FormData 只需要 File 那套接口
  const files = fileList.value.flatMap(item => (item.raw ? [item.raw as unknown as File] : []))
  if (tab.value === 'file' && !files.length) { ElMessage.warning('请先选择文件'); return }
  if (tab.value === 'paste' && !text.value.trim()) { ElMessage.warning('请粘贴文案'); return }
  parsing.value = true
  results.value = []
  groups.value = []
  try {
    const queue: (File | null)[] = tab.value === 'file' ? files : [null]
    for (let index = 0; index < queue.length; index += 1) {
      progress.value = `解析中 ${index + 1}/${queue.length}…`
      const item = queue[index] ?? null
      groups.value.push(await parseOne(item, item ? null : text.value, `g-${index}`))
    }
    const failed = groups.value.filter(group => group.error).length
    const pieces = groups.value.reduce((sum, group) => sum + group.pieces.length, 0)
    if (!pieces) ElMessage.warning(failed ? '有文件没解析出话术，原因见下方红色提示' : '没有切出有效话术，换个切分方式试试')
    else if (failed) ElMessage.warning(`${failed} 份解析失败，其余 ${groups.value.length - failed} 份可继续`)
  } finally {
    parsing.value = false
    progress.value = ''
  }
}

/** 勾选条目 → 入库（每份素材各一次 commit）→ 分批审查（后端一次最多 20 条）。 */
async function runCheck() {
  if (!pickedCount.value) { ElMessage.warning('至少勾选一条'); return }
  checking.value = true
  results.value = []
  const ids: number[] = []
  try {
    const ready = groups.value.filter(group => group.picked.size)
    for (let index = 0; index < ready.length; index += 1) {
      const group = ready[index]
      progress.value = `入库 ${index + 1}/${ready.length}：${group.filename}`
      const items = [...group.picked].sort((a, b) => a - b).map(p => group.pieces[p].text)
      const saved = await importScripts(buildForm(true, group, items))
      group.scriptIds = saved.script_ids
      group.sourceId = saved.source_id ?? null
      ids.push(...saved.script_ids)
    }
    for (let start = 0; start < ids.length; start += 20) {
      const chunk = ids.slice(start, start + 20)
      progress.value = `检查中 ${Math.min(start + 20, ids.length)}/${ids.length}，每条约 6 秒…`
      const batch = await auditBatch(clientId.value, chunk)
      results.value.push(...batch.results)
    }
    const bad = results.value.filter(item => !item.error && item.score === 0).length
    ElMessage.success(`已检查 ${results.value.length} 条，其中 ${bad} 条需要修改`)
  } catch {
    // 失败不伪造结果：已经入库的部分照常保留，去「我的话术」能看到。
  } finally {
    checking.value = false
    progress.value = ''
  }
}

function toggle(key: string, index: number) {
  const group = groups.value.find(item => item.key === key)
  if (!group) return
  const next = new Set(group.picked)
  if (next.has(index)) next.delete(index)
  else next.add(index)
  group.picked = next
}

function toggleAll(group: Group) {
  const all = group.pieces.length === group.picked.size
  group.picked = all ? new Set() : new Set(group.pieces.map((_, index) => index))
}

onMounted(async () => {
  try {
    caps.value = await parseCapabilities()
    if (!caps.value.modes.includes(mode.value)) mode.value = caps.value.modes[0]
  } catch {
    // 能力清单拿不到就退回最保守的两种模式，而不是让页面报错打不开
  }
})
</script>

<template>
  <div>
    <h1>文案检查</h1>
    <p class="muted">
      粘贴文案，或把海报、报价表、PDF、录音直接丢进来 —— 系统会解析成逐条话术、标出每条来自哪里，
      再由你勾选后审查。违规条目会指出违反哪一条、原文依据与判定理由。
    </p>

    <el-alert v-if="missingEngines.length" type="warning" :closable="false" show-icon class="card"
              :title="`以下能力当前未启用：${missingEngines.join('、')}`">
      <p class="muted">
        对应格式暂时不能上传，界面不会假装支持。安装命令与说明见项目 RUNBOOK §6。
      </p>
    </el-alert>

    <el-card shadow="never" class="card">
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
          <span class="muted" style="margin-left: 12px">行首序号会自动去掉；录音请用「按句」</span>
        </el-form-item>
      </el-form>

      <el-tabs v-model="tab">
        <el-tab-pane label="粘贴文本" name="paste">
          <el-input v-model="text" type="textarea" :rows="7" maxlength="20000" show-word-limit
                    placeholder="把整篇文案粘进来" />
        </el-tab-pane>
        <el-tab-pane label="上传文件（可多选）" name="file">
          <el-upload drag multiple :auto-upload="false" v-model:file-list="fileList" :accept="accept">
            <div class="drop">
              <p>把文件拖进来，或<span class="link">点击选择</span></p>
              <p class="muted">{{ accept || '后端未提供能力清单' }}</p>
            </div>
            <template #tip>
              <div class="muted">支持海报图片、扫描件 PDF、docx/xlsx/pptx、txt/csv 与录音；可一次多选</div>
            </template>
          </el-upload>
        </el-tab-pane>
      </el-tabs>

      <el-button :loading="parsing" @click="preview">解析预览</el-button>
      <span v-if="progress" class="muted" style="margin-left: 12px">{{ progress }}</span>
    </el-card>

    <el-card v-for="group in groups" :key="group.key" shadow="never" class="card">
      <h3>{{ group.filename }}
        <el-tag size="small" effect="plain">{{ group.kind }}</el-tag>
        <el-tag size="small" type="info" effect="plain">{{ group.engine }}</el-tag>
        <el-tag v-if="group.confidence !== null" size="small"
                :type="group.confidence < 0.6 ? 'warning' : 'success'" effect="plain">
          识别置信度 {{ conf(group.confidence) }}
        </el-tag>
      </h3>
      <el-alert v-if="group.error" type="error" :closable="false" show-icon :title="group.error" />
      <el-button v-if="group.sourceId" link type="primary" class="material"
                 @click="drawerId = group.sourceId; drawerOpen = true">
        查看原始素材
      </el-button>
      <div v-for="item in group.warnings" :key="item">
        <el-alert type="warning" :closable="false" show-icon :title="item" class="warn" />
      </div>
      <template v-if="group.pieces.length">
        <el-checkbox :model-value="group.picked.size === group.pieces.length"
                    :indeterminate="group.picked.size > 0 && group.picked.size < group.pieces.length"
                    @change="toggleAll(group)">全选 / 全不选</el-checkbox>
        <p class="muted">切得不准的先取消勾选，不会写进库。</p>
        <div class="list">
          <div v-for="(piece, index) in group.pieces" :key="index" class="row"
               :class="{ on: group.picked.has(index) }">
            <el-checkbox :model-value="group.picked.has(index)" @change="toggle(group.key, index)" />
            <span class="idx">{{ index + 1 }}</span>
            <span class="text">{{ piece.text }}</span>
            <span class="src">
              <el-tag v-if="piece.ref" size="small" type="info" effect="plain">{{ piece.ref }}</el-tag>
              <el-tag v-if="piece.confidence !== null" size="small"
                      :type="piece.confidence < 0.6 ? 'warning' : 'info'" effect="plain">
                {{ conf(piece.confidence) }}
              </el-tag>
            </span>
          </div>
        </div>
      </template>
    </el-card>

    <el-card v-if="pickedCount" shadow="never" class="card">
      <el-button type="primary" size="large" :loading="checking" @click="runCheck">
        {{ checking && progress ? progress : `检查这 ${pickedCount} 条` }}
      </el-button>
      <p class="muted">后端顺序执行，单条约 6 秒；超过 20 条会自动分批跑完。</p>
    </el-card>

    <AuditResults v-if="results.length" :items="results" />

    <SourceDrawer v-model="drawerOpen" :source-id="drawerId" />
  </div>
</template>

<style scoped>
.muted { color: var(--el-text-color-secondary); font-size: 13px; }
h1 { margin: 0 0 6px; font-size: 24px; }
h3 { margin: 0 0 8px; font-size: 15px; }
h3 .el-tag { margin-left: 8px; }
.card { margin-top: 16px; }
.warn { margin-top: 8px; }
.drop { padding: 10px 0; text-align: center; }
.drop p { margin: 4px 0; }
.link { color: var(--el-color-primary); cursor: pointer; text-decoration: underline; }
.list { max-height: 320px; overflow-y: auto; border: 1px solid var(--el-border-color-lighter); border-radius: 6px; margin-top: 8px; }
.row { display: flex; align-items: flex-start; gap: 10px; padding: 8px 12px; border-bottom: 1px solid var(--el-border-color-lighter); }
.row:last-child { border-bottom: none; }
.row.on { background: var(--el-color-primary-light-9); }
.idx { min-width: 26px; color: var(--el-text-color-secondary); font-variant-numeric: tabular-nums; }
.text { line-height: 1.6; word-break: break-word; flex: 1; }
.src { display: flex; gap: 6px; flex-shrink: 0; }
</style>
