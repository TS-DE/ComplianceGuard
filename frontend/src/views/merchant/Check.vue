<script setup lang="ts">
/**
 * 文案检查：商家端的主入口，一条链路走完"粘贴/上传 → 切分 → 入库 → 批量审查 → 看结论"。
 *
 * 三个阶段刻意分开：
 * 1) 预览（不写库）：切分不可能百分百正确，先让人剔除误切片段；
 * 2) 入库：只写入勾选的条目；
 * 3) 审查：顺序执行，单条失败不影响其余，失败条如实标红。
 *
 * 明确不做：图片与语音（需要 OCR/ASR 服务）；扫描件 PDF 会被后端拒绝，
 * 这里把原因原样透出，而不是显示"0 条"让人以为没内容。
 */
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  importScripts, auditBatch, axisLabel,
  type BatchAuditItem, type Hit
} from '../../api/resource'
import { useAuth } from '../../stores/auth'

const router = useRouter()
const auth = useAuth()

const tab = ref<'paste' | 'file'>('paste')
const form = reactive({ scene: '', mode: 'blank' as 'blank' | 'line' })
const text = ref('')
const file = ref<File | null>(null)
const parsed = ref<string[]>([])
const selected = ref<Set<number>>(new Set())
const parsing = ref(false)
const checking = ref(false)
const results = ref<BatchAuditItem[]>([])
const expanded = ref<number | null>(null)

const clientId = computed(() => auth.user?.client_id ?? 0)
const selectedCount = computed(() => selected.value.size)
const picked = computed(() => parsed.value.filter((_, i) => selected.value.has(i)))

const verdict = (item: BatchAuditItem) =>
  item.error ? '失败'
    : item.incomplete || item.score === -1 ? '判定未完成'
      : ({ '0': '违规', '1': '轻微风险', '2': '合规' } as Record<string, string>)[String(item.score)] ?? '未知'
const tagType = (item: BatchAuditItem) =>
  item.error || item.incomplete || item.score === -1 || item.score === 0 ? 'danger'
    : item.score === 1 ? 'warning' : 'success'

const label = (axis: string) => axisLabel(axis)

function onFile(event: Event) {
  const input = event.target as HTMLInputElement
  file.value = input.files?.[0] ?? null
}

function buildForm(commit: boolean): FormData {
  const data = new FormData()
  data.append('client_id', String(clientId.value))
  data.append('scene', form.scene)
  data.append('mode', form.mode)
  data.append('commit', commit ? 'true' : 'false')
  if (commit) data.append('items', JSON.stringify(picked.value))
  if (tab.value === 'file' && file.value) data.append('file', file.value)
  else data.append('text', text.value)
  return data
}

async function preview() {
  if (!clientId.value) { ElMessage.error('账号未绑定机构，请重新登录'); return }
  if (tab.value === 'file' && !file.value) { ElMessage.warning('请先选择文件'); return }
  if (tab.value === 'paste' && !text.value.trim()) { ElMessage.warning('请粘贴文案'); return }
  parsing.value = true
  results.value = []
  try {
    const result = await importScripts(buildForm(false))
    parsed.value = result.items
    selected.value = new Set(result.items.map((_, i) => i))
    if (!result.items.length) ElMessage.warning('没有切出有效话术，换个切分方式试试')
  } catch {
    // 接口层已提示（含不支持类型、扫描件需 OCR 等）
  } finally {
    parsing.value = false
  }
}

async function runCheck() {
  if (!selectedCount.value) { ElMessage.warning('至少勾选一条'); return }
  if (selectedCount.value > 20) { ElMessage.warning('一次最多检查 20 条，请分批'); return }
  checking.value = true
  results.value = []
  try {
    const saved = await importScripts(buildForm(true))
    const batch = await auditBatch(clientId.value, saved.script_ids)
    results.value = batch.results
    const bad = batch.results.filter(item => !item.error && item.score === 0).length
    ElMessage.success(`已检查 ${batch.count} 条，其中 ${bad} 条需要修改`)
    parsed.value = []
    selected.value = new Set()
  } catch {
    // 失败不伪造结果
  } finally {
    checking.value = false
  }
}

function toggle(index: number) {
  const next = new Set(selected.value)
  if (next.has(index)) next.delete(index)
  else next.add(index)
  selected.value = next
}

const hitList = (item: BatchAuditItem): Hit[] => item.hits ?? []
</script>

<template>
  <div>
    <h1>文案检查</h1>
    <p class="muted">
      粘贴或上传机构文案，系统会按条切分后逐条审查；违规条目会指出违反的条款、原文依据与判定理由。
    </p>

    <el-card shadow="never" class="card">
      <el-form label-width="86px">
        <el-form-item label="场景">
          <el-input v-model="form.scene" maxlength="50" style="width: 260px" placeholder="可选，如 双眼皮 / 热玛吉" />
        </el-form-item>
        <el-form-item label="切分方式">
          <el-radio-group v-model="form.mode">
            <el-radio-button value="blank">按空行（一段一条）</el-radio-button>
            <el-radio-button value="line">按行（一行一条）</el-radio-button>
          </el-radio-group>
          <span class="muted" style="margin-left: 12px">行首序号会自动去掉</span>
        </el-form-item>
      </el-form>

      <el-tabs v-model="tab">
        <el-tab-pane label="粘贴文本" name="paste">
          <el-input v-model="text" type="textarea" :rows="7" maxlength="20000" show-word-limit
                    placeholder="把整篇文案粘进来" />
        </el-tab-pane>
        <el-tab-pane label="上传文件" name="file">
          <input type="file" accept=".txt,.md,.csv,.docx,.pdf" @change="onFile" />
          <p class="muted" v-if="file">已选择：{{ file.name }}（{{ (file.size / 1024).toFixed(1) }} KB）</p>
          <p class="muted">支持 .txt / .md / .csv / .docx / .pdf（需有文字层）。图片与语音需要 OCR/ASR，暂不支持。</p>
        </el-tab-pane>
      </el-tabs>

      <el-button :loading="parsing" @click="preview">解析预览</el-button>
    </el-card>

    <el-card v-if="parsed.length" shadow="never" class="card">
      <h3>切出 {{ parsed.length }} 条，已勾选 {{ selectedCount }} 条</h3>
      <p class="muted">切分不准确的内容可以先取消勾选，不会写进库里。</p>
      <div class="list">
        <div v-for="(item, index) in parsed" :key="index" class="row" :class="{ on: selected.has(index) }">
          <el-checkbox :model-value="selected.has(index)" @change="toggle(index)" />
          <span class="idx">{{ index + 1 }}</span>
          <span class="text">{{ item }}</span>
        </div>
      </div>
      <el-button type="primary" style="margin-top: 12px" :loading="checking" :disabled="!selectedCount"
                 @click="runCheck">
        {{ checking ? '检查中，每条约 6 秒…' : `检查这 ${selectedCount} 条` }}
      </el-button>
    </el-card>

    <el-card v-if="results.length" shadow="never" class="card">
      <h3>检查结果</h3>
      <el-table :data="results" size="small" empty-text="无结果">
        <el-table-column label="话术" min-width="260">
          <template #default="{ row }">
            <span class="ellipsis" :title="row.script_id">{{ `#${row.script_id}` }}</span>
          </template>
        </el-table-column>
        <el-table-column label="结论" width="130">
          <template #default="{ row }"><el-tag :type="tagType(row)" effect="light">{{ verdict(row) }}</el-tag></template>
        </el-table-column>
        <el-table-column label="命中" width="80">
          <template #default="{ row }">{{ row.error ? '—' : row.hit_count }}</template>
        </el-table-column>
        <el-table-column label="耗时" width="100">
          <template #default="{ row }">{{ row.error ? '—' : `${row.latency_ms} ms` }}</template>
        </el-table-column>
        <el-table-column label="说明" min-width="240">
          <template #default="{ row }">
            <span v-if="row.error" class="err">{{ row.error }}</span>
            <el-button v-else-if="row.hit_count" link type="primary"
                       @click="expanded = expanded === row.script_id ? null : row.script_id">
              {{ expanded === row.script_id ? '收起' : '查看违规明细' }}
            </el-button>
            <span v-else class="muted">未发现违规</span>
          </template>
        </el-table-column>
      </el-table>

      <div v-for="row in results" :key="`d-${row.script_id}`">
        <div v-if="expanded === row.script_id" class="detail">
          <div v-for="(hit, i) in hitList(row)" :key="i" class="hit">
            <p class="hit-head">
              <el-tag size="small" type="danger" effect="light">{{ label(hit.axis) }}</el-tag>
              <span class="law">{{ hit.law_article }}</span>
            </p>
            <p class="quote">原文：{{ hit.quote }}</p>
            <p v-if="hit.reason" class="reason">理由：{{ hit.reason }}</p>
          </div>
        </div>
      </div>

      <el-button style="margin-top: 12px" @click="router.push('/merchant/audits')">到审查历史查看完整记录</el-button>
    </el-card>
  </div>
</template>

<style scoped>
.muted { color: var(--el-text-color-secondary); font-size: 13px; }
h1 { margin: 0 0 6px; font-size: 24px; }
h3 { margin: 0 0 8px; font-size: 15px; }
.card { margin-top: 16px; }
.list { max-height: 300px; overflow-y: auto; border: 1px solid var(--el-border-color-lighter); border-radius: 6px; }
.row { display: flex; align-items: flex-start; gap: 10px; padding: 8px 12px; border-bottom: 1px solid var(--el-border-color-lighter); }
.row:last-child { border-bottom: none; }
.row.on { background: var(--el-color-primary-light-9); }
.idx { min-width: 26px; color: var(--el-text-color-secondary); font-variant-numeric: tabular-nums; }
.text { line-height: 1.6; word-break: break-word; }
.ellipsis { display: inline-block; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; vertical-align: bottom; }
.err { color: var(--el-color-danger); font-size: 12px; }
.detail { margin-top: 8px; border: 1px solid var(--el-border-color-lighter); border-radius: 6px; padding: 12px; }
.hit { padding: 8px 0; border-bottom: 1px dashed var(--el-border-color-lighter); }
.hit:last-child { border-bottom: none; }
.hit-head { margin: 0 0 6px; display: flex; align-items: center; gap: 8px; }
.law { font-size: 12px; color: var(--el-text-color-secondary); }
.quote { margin: 0 0 4px; font-size: 13px; line-height: 1.6; }
.reason { margin: 0; font-size: 12px; line-height: 1.6; color: var(--el-text-color-regular); }
</style>
