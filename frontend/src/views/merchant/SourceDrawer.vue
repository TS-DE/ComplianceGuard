<script setup lang="ts">
/**
 * 素材档案抽屉：一份上传素材的解析结果 + 原始文件回看 + 当场体检。
 *
 * 为什么要能直接看原始素材：商家问"这句真是海报上写的吗"时，
 * 唯一有说服力的回答是把那张海报摊在他面前，并指出是哪一块。
 * 只给一段纯文本，等于让人对着黑盒自证。
 *
 * Blob URL 必须在关闭和卸载时回收：一份录音几十 MB，
 * 不 revoke 就会一直压在页面内存里，开合几次抽屉浏览器就吃紧。
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  previewSource, sources, axisLabel,
  type PreviewItem, type SourceDetail
} from '../../api/resource'

const props = defineProps<{ modelValue: boolean; sourceId: number | null }>()
const emit = defineEmits<{ (event: 'update:modelValue', value: boolean): void }>()

const detail = ref<SourceDetail | null>(null)
const loading = ref(false)
const objectUrl = ref<string | null>(null)
const fileError = ref<string | null>(null)
const previewing = ref(false)
const preview = ref<PreviewItem[] | null>(null)

const KIND_LABELS: Record<string, string> = {
  text: '纯文本', sheet: '表格', docx: 'Word', slides: 'PPT',
  pdf_text: 'PDF（文字层）', pdf_scan: 'PDF（扫描件 OCR）', image: '图片（OCR）', audio: '录音（语音转写）'
}
const kindLabel = computed(() => KIND_LABELS[detail.value?.kind ?? ''] ?? detail.value?.kind ?? '-')
/** 能在浏览器里直接渲染的形态；docx/xlsx 这类只能下载，不假装能预览。 */
const view = computed<'image' | 'audio' | 'pdf' | 'text' | 'none'>(() => {
  const kind = detail.value?.kind ?? ''
  if (kind === 'image' || kind === 'pdf_scan') return 'image'
  if (kind === 'audio') return 'audio'
  if (kind === 'pdf_text') return 'pdf'
  if (kind === 'text' || kind === 'sheet') return 'text'
  return 'none'
})
const verdict = (item: PreviewItem) =>
  item.error ? '判定未完成'
    : item.incomplete || item.score === -1 ? '判定未完成'
      : ({ '0': '违规', '1': '疑似违规', '2': '合规' } as Record<string, string>)[String(item.score)] ?? '未知'
const tagType = (item: PreviewItem) =>
  item.error || item.incomplete || item.score === -1 || item.score === 0 ? 'danger'
    : item.score === 1 ? 'warning' : 'success'
const label = (axis: string) => axisLabel(axis)
// 后端把 DECIMAL 序列化成字符串（同 cost 口径），所以两种都要能接
const percent = (value: number | string | null) =>
  (value === null || value === '' ? '—' : `${Math.round(Number(value) * 100)}%`)
const size = (bytes: number) => `${(bytes / 1024).toFixed(1)} KB`

function release() {
  if (objectUrl.value) URL.revokeObjectURL(objectUrl.value)
  objectUrl.value = null
}

async function load() {
  if (!props.sourceId) return
  loading.value = true
  preview.value = null
  fileError.value = null
  release()
  try {
    detail.value = await sources.get(props.sourceId)
    if (!detail.value.file_available) {
      fileError.value = '这份素材没有落盘（只做过预览），只能看解析结果'
      return
    }
    const blob = await sources.blob(props.sourceId)
    objectUrl.value = URL.createObjectURL(blob)
  } catch {
    // 失败原因由 API 层提示过；这里保持档案为空态，不显示半成品
  } finally {
    loading.value = false
  }
}

/** 当场体检：走 A1 的素材入口，逐条给结论但不写审查记录。 */
async function checkNow() {
  if (!props.sourceId) return
  previewing.value = true
  try {
    const result = await previewSource(props.sourceId)
    preview.value = result.results
    if (result.truncated) {
      ElMessage.warning(`这份素材共 ${result.total_items} 条，本次只体检前 ${result.count} 条`)
    }
    if (result.warnings.length) ElMessage.warning(result.warnings[0])
  } catch {
    preview.value = null
  } finally {
    previewing.value = false
  }
}

watch(() => [props.modelValue, props.sourceId], ([open]) => {
  if (open && props.sourceId) void load()
  if (!open) { release(); preview.value = null }
})
onBeforeUnmount(release)
</script>

<template>
  <el-drawer :model-value="props.modelValue" size="720px" title="素材档案"
             @update:model-value="emit('update:modelValue', $event)">
    <div v-loading="loading">
      <template v-if="detail">
        <h3 class="name">{{ detail.filename }}</h3>
        <p class="muted">
          {{ kindLabel }} · 引擎 {{ detail.engine }} · {{ size(detail.size_bytes) }}
          · 切出 {{ detail.item_count }} 条 · 解析 {{ detail.parse_ms ?? 0 }} ms
        </p>
        <p class="muted">
          识别置信度
          <el-tag size="small" :type="detail.confidence === null ? 'info'
                                       : detail.confidence < 0.6 ? 'warning' : 'success'" effect="plain">
            {{ detail.confidence === null ? '文本层（无识别误差）' : percent(detail.confidence) }}
          </el-tag>
          <span v-if="detail.warnings?.length" class="err">
            ；解析警告：{{ detail.warnings.join('；') }}
          </span>
        </p>

        <el-alert v-if="fileError" type="info" :closable="false" show-icon :title="fileError" class="block" />
        <template v-else-if="objectUrl">
          <img v-if="view === 'image'" :src="objectUrl" class="material" alt="原始素材" />
          <audio v-else-if="view === 'audio'" :src="objectUrl" controls class="block" />
          <iframe v-else-if="view === 'pdf'" :src="objectUrl" class="frame" title="原始 PDF" />
          <p v-else class="muted block">
            该格式无法在浏览器内直接渲染，可
            <el-link type="primary" :href="objectUrl" :download="detail.filename">下载原文件</el-link>
            后核对。
          </p>
        </template>

        <el-button type="primary" :loading="previewing" class="block" @click="checkNow">
          {{ previewing ? '逐条判定中，每条约 6 秒…' : '当场体检（不写审查记录）' }}
        </el-button>

        <div v-if="preview" class="block">
          <el-alert type="info" :closable="false" show-icon class="block"
                    title="预审不落库：以下结论不会写入审查记录。需要留档请走「文案检查 → 勾选入库 → 检查」。" />
          <div v-for="(item, index) in preview" :key="index" class="row">
            <el-tag size="small" :type="tagType(item)" effect="light">{{ verdict(item) }}</el-tag>
            <span class="ref">{{ item.ref ?? '—' }}</span>
            <span class="content">{{ item.text }}</span>
            <span class="axes">
              <el-tag v-for="hit in item.hits" :key="hit.axis + hit.law_article" size="small"
                      type="danger" effect="plain">{{ label(hit.axis) }}</el-tag>
              <span v-if="item.error" class="err">{{ item.error }}</span>
            </span>
          </div>
        </div>

        <h4 class="block">这份素材切出的话术</h4>
        <el-table :data="detail.scripts" size="small" empty-text="未入库任何条目">
          <el-table-column label="位置" width="130">
            <template #default="{ row }">{{ row.ref ?? '—' }}</template>
          </el-table-column>
          <el-table-column label="置信度" width="90">
            <template #default="{ row }">{{ row.confidence === null ? '—' : percent(row.confidence) }}</template>
          </el-table-column>
          <el-table-column prop="content" label="内容" min-width="240" />
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag size="small" :type="row.status === 'audited' ? 'primary' : 'info'" effect="plain">
                {{ row.status === 'audited' ? '已审查' : row.status === 'pending' ? '未审查' : '已归档' }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </template>
      <el-empty v-else description="没有可显示的素材" />
    </div>
  </el-drawer>
</template>

<style scoped>
.muted { color: var(--el-text-color-secondary); font-size: 12px; }
.name { margin: 0 0 4px; font-size: 16px; }
.block { margin-top: 12px; }
.err { color: var(--el-color-danger); font-size: 12px; }
.material { max-width: 100%; border: 1px solid var(--el-border-color-lighter); border-radius: 6px; }
.frame { width: 100%; height: 420px; border: 1px solid var(--el-border-color-lighter); border-radius: 6px; }
.row { display: flex; align-items: flex-start; gap: 8px; padding: 6px 0; border-bottom: 1px dashed var(--el-border-color-lighter); }
.ref { min-width: 92px; font-size: 12px; color: var(--el-text-color-secondary); }
.content { flex: 1; font-size: 13px; line-height: 1.6; word-break: break-word; }
.axes { display: flex; gap: 4px; flex-wrap: wrap; max-width: 220px; }
</style>
