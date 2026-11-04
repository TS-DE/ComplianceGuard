<script setup lang="ts">
/**
 * 批量导入：商家给的是整页文案（docx/pdf/txt 或直接粘贴），不是一条条数据。
 *
 * 强制两段式：
 *   1) 解析预览 —— 只切分不写库，让人先看切得对不对
 *   2) 勾选入库 —— 只提交勾选的条目
 * 理由：切分不可能百分百正确，若一键写库，脏数据会污染后面所有审计统计。
 *
 * 能力清单由后端注册表给出（GET /sources/formats）：现在能吃海报图片、扫描件 PDF、
 * xlsx/xls/pptx 与录音；缺引擎时界面会写明"未启用"，而不是让用户传上来才知道不支持。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { importScripts, parseCapabilities, type Capabilities, type Client, type ImportPiece } from '../../api/resource'

const props = defineProps<{ modelValue: boolean; clients: Client[] }>()
const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'imported'): void
}>()

const tab = ref<'paste' | 'file'>('paste')
const form = reactive({ clientId: undefined as number | undefined, scene: '', mode: 'blank' as 'blank' | 'line' | 'sentence' })
const text = ref('')
const file = ref<File | null>(null)
const parsed = ref<ImportPiece[]>([])
const selected = ref<Set<number>>(new Set())
const parsing = ref(false)
const saving = ref(false)
const caps = ref<Capabilities | null>(null)

/** accept 从后端能力清单生成：硬编码一份列表会在新增格式那天开始骗人，
 *  而且会把 .doc 这种"明确不做"的格式放进文件选择器里。 */
const accept = computed(() => (caps.value?.formats ?? [])
  .filter(item => item.available && item.suffix !== '.md').map(item => item.suffix).join(','))
const missingEngines = computed(() => Object.entries(caps.value?.engines ?? {})
  .filter(([, ok]) => !ok).map(([name]) => (name === 'ocr' ? 'OCR' : 'ASR')))
const modes = computed(() => caps.value?.modes ?? ['blank', 'line'])
const pickedTexts = computed(() =>
  [...selected.value].sort((a, b) => a - b).map(index => parsed.value[index]?.text).filter(Boolean))

const selectedCount = computed(() => selected.value.size)
const MODE_LABELS: Record<string, string> = {
  blank: '按空行（一段一条）', line: '按行（一行一条）', sentence: '按句（语音/连排）'
}
const percent = (value: number | null) => (value === null ? null : `${Math.round(value * 100)}%`)
const reset = () => {
  parsed.value = []
  selected.value = new Set()
  parsing.value = false
  saving.value = false
}

function close() {
  emit('update:modelValue', false)
  reset()
  text.value = ''
  file.value = null
}

onMounted(async () => {
  try {
    caps.value = await parseCapabilities()
    if (!modes.value.includes(form.mode)) form.mode = 'blank'
  } catch {
    // 拿不到能力清单时保留默认两种切分方式，不让弹窗打不开
  }
})

function onFile(event: Event) {
  const input = event.target as HTMLInputElement
  file.value = input.files?.[0] ?? null
}

function buildFormData(commit: boolean): FormData {
  const data = new FormData()
  if (form.clientId) data.append('client_id', String(form.clientId))
  data.append('scene', form.scene)
  data.append('mode', form.mode)
  data.append('commit', commit ? 'true' : 'false')
  if (commit) {
    // 只提交文本：页码与置信度由服务端重解析算出，前端传来的不作数
    data.append('items', JSON.stringify(pickedTexts.value))
  }
  if (tab.value === 'file' && file.value) data.append('file', file.value)
  else data.append('text', text.value)
  return data
}

async function preview() {
  if (!form.clientId) { ElMessage.warning('请先选择机构'); return }
  if (tab.value === 'file' && !file.value) { ElMessage.warning('请先选择文件'); return }
  if (tab.value === 'paste' && !text.value.trim()) { ElMessage.warning('请粘贴文案'); return }
  parsing.value = true
  try {
    const result = await importScripts(buildFormData(false))
    parsed.value = result.items_detail
    selected.value = new Set(result.items_detail.map((_, index) => index))
    if (!result.items_detail.length) ElMessage.warning('没有切出有效话术，换个切分方式试试')
  } catch {
    // 接口层已提示（含"不支持的文件类型""该 PDF 无文本层需 OCR"等）。
  } finally {
    parsing.value = false
  }
}

async function commit() {
  if (!selectedCount.value) { ElMessage.warning('至少勾选一条'); return }
  saving.value = true
  try {
    const result = await importScripts(buildFormData(true))
    ElMessage.success(`已入库 ${result.created} 条`)
    emit('imported')
    close()
  } catch {
    // 失败不写库、不提示成功。
  } finally {
    saving.value = false
  }
}

function toggle(index: number) {
  const next = new Set(selected.value)
  if (next.has(index)) next.delete(index)
  else next.add(index)
  selected.value = next
}

function toggleAll(checked: boolean) {
  selected.value = checked ? new Set(parsed.value.map((_, index) => index)) : new Set()
}
</script>

<template>
  <el-dialog :model-value="modelValue" title="批量导入话术" width="780px" @update:model-value="emit('update:modelValue', $event)">
    <el-alert type="info" :closable="false" show-icon style="margin-bottom: 14px"
              title="支持粘贴文本，或上传海报图片、扫描件/文字层 PDF、docx / xlsx / xls / pptx、txt / csv 与录音。" />
    <el-alert v-if="missingEngines.length" type="warning" :closable="false" show-icon style="margin-bottom: 14px"
              :title="`以下能力当前未启用：${missingEngines.join('、')}（对应格式传上来会被明确拒绝，不会假装成功）`" />

    <el-form label-width="86px">
      <el-form-item label="归属机构">
        <el-select v-model="form.clientId" filterable placeholder="选择机构" style="width: 280px">
          <el-option v-for="client in props.clients" :key="client.id"
                     :label="`${client.id} · ${client.name}`" :value="client.id" />
        </el-select>
        <el-input v-model="form.scene" placeholder="场景（可选，如 双眼皮）" maxlength="50"
                  style="width: 220px; margin-left: 12px" />
      </el-form-item>
      <el-form-item label="切分方式">
        <el-radio-group v-model="form.mode">
          <el-radio-button v-for="item in modes" :key="item" :value="item">
            {{ MODE_LABELS[item] ?? item }}
          </el-radio-button>
        </el-radio-group>
        <span class="muted" style="margin-left: 12px">行首序号会自动去掉；录音请用「按句」</span>
      </el-form-item>
    </el-form>

    <el-tabs v-model="tab">
      <el-tab-pane label="粘贴文本" name="paste">
        <el-input v-model="text" type="textarea" :rows="6" maxlength="20000" show-word-limit
                  placeholder="把整页文案粘进来，系统会按所选方式切分成逐条话术" />
      </el-tab-pane>
      <el-tab-pane label="上传文件" name="file">
        <input type="file" :accept="accept || undefined" @change="onFile" />
        <p class="muted" v-if="file">已选择：{{ file.name }}（{{ (file.size / 1024).toFixed(1) }} KB）</p>
      </el-tab-pane>
    </el-tabs>

    <div class="actions">
      <el-button :loading="parsing" @click="preview">解析预览</el-button>
      <span v-if="parsed.length" class="muted">切出 {{ parsed.length }} 条，已勾选 {{ selectedCount }} 条</span>
    </div>

    <template v-if="parsed.length">
      <el-checkbox :model-value="selectedCount === parsed.length"
                   :indeterminate="selectedCount > 0 && selectedCount < parsed.length"
                   style="margin: 10px 0" @change="toggleAll($event as boolean)">
        全选 / 全不选
      </el-checkbox>
      <div class="list">
        <div v-for="(item, index) in parsed" :key="index" class="row" :class="{ on: selected.has(index) }">
          <el-checkbox :model-value="selected.has(index)" @change="toggle(index)" />
          <span class="idx">{{ index + 1 }}</span>
          <span class="text">{{ item.text }}</span>
          <span class="src">
            <el-tag v-if="item.ref" size="small" type="info" effect="plain">{{ item.ref }}</el-tag>
            <el-tag v-if="item.confidence !== null" size="small"
                    :type="item.confidence < 0.6 ? 'warning' : 'info'" effect="plain">
              {{ percent(item.confidence) }}
            </el-tag>
          </span>
        </div>
      </div>
    </template>

    <template #footer>
      <el-button @click="close">取消</el-button>
      <el-button type="primary" :disabled="!selectedCount" :loading="saving" @click="commit">
        确认入库（{{ selectedCount }} 条）
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.muted { color: var(--el-text-color-secondary); font-size: 12px; }
.actions { display: flex; align-items: center; gap: 12px; margin-top: 6px; }
.list { max-height: 300px; overflow-y: auto; border: 1px solid var(--el-border-color-lighter); border-radius: 6px; }
.row { display: flex; align-items: flex-start; gap: 10px; padding: 8px 12px; border-bottom: 1px solid var(--el-border-color-lighter); }
.row:last-child { border-bottom: none; }
.row.on { background: var(--el-color-primary-light-9); }
.idx { min-width: 26px; color: var(--el-text-color-secondary); font-variant-numeric: tabular-nums; }
.text { line-height: 1.6; word-break: break-word; }
</style>
