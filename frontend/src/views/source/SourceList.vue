<script setup lang="ts">
/**
 * 素材档案：商家上传过的每一份原始文件。
 *
 * 这一页存在的理由只有一个问题：「这条被判违规的话是从哪来的」。
 * 话术库答不了（它只存切出来的句子），必须能回到那份海报 / 那份 PDF / 那段录音。
 *
 * 平台端与商家端复用同一组件：数据裁剪在服务端 data_scope 完成，
 * 前端再过滤一遍只会造成"两边口径不同"的错觉。
 */
import { onMounted, ref } from 'vue'
import { sources, type SourceRow } from '../../api/resource'
import SourceDrawer from '../merchant/SourceDrawer.vue'

const rows = ref<SourceRow[]>([])
const page = ref(1)
const total = ref(0)
const loading = ref(false)
const drawerOpen = ref(false)
const drawerId = ref<number | null>(null)

const KIND_LABELS: Record<string, string> = {
  text: '文本', sheet: '表格', docx: 'Word', slides: 'PPT',
  pdf_text: 'PDF 文字层', pdf_scan: 'PDF 扫描件', image: '图片 OCR', audio: '录音'
}
const kindLabel = (kind: string) => KIND_LABELS[kind] ?? kind
const percent = (value: number | null) => (value === null ? '—' : `${Math.round(value * 100)}%`)
const size = (bytes: number) => `${(bytes / 1024).toFixed(1)} KB`

async function load() {
  loading.value = true
  try {
    const data = await sources.list<SourceRow>({ page: page.value, page_size: 20 })
    rows.value = data.items
    total.value = data.total
  } catch {
    // 失败保留当前列表供重试，不闪空态假装"没有数据"
  } finally {
    loading.value = false
  }
}

function open(row: SourceRow) {
  drawerId.value = row.id
  drawerOpen.value = true
}

onMounted(load)
</script>

<template>
  <div>
    <p class="muted">MATERIAL ARCHIVE / 原始素材</p>
    <h1>素材档案</h1>
    <p class="muted">
      每一份上传素材都保留原始文件与解析过程：用了哪个引擎、共几页、识别置信度多少、切出几条。
      点开可以看原图 / 听录音 / 翻 PDF，也可以「当场体检」——预审结论不写入审查记录。
    </p>

    <el-card shadow="never">
      <el-button :loading="loading" @click="load">刷新</el-button>
      <el-table v-loading="loading" :data="rows" size="small" empty-text="还没有上传过素材"
                style="margin-top: 12px">
        <el-table-column prop="id" label="#" width="60" />
        <el-table-column label="文件" min-width="220">
          <template #default="{ row }">
            <span class="ellipsis" :title="row.filename">{{ row.filename }}</span>
            <el-tag v-if="!row.file_available" size="small" type="warning" effect="plain" class="tag">
              原文件缺失
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="形态" width="120">
          <template #default="{ row }">{{ kindLabel(row.kind) }}</template>
        </el-table-column>
        <el-table-column prop="engine" label="引擎" width="150" />
        <el-table-column label="置信度" width="100">
          <template #default="{ row }">{{ percent(row.confidence) }}</template>
        </el-table-column>
        <el-table-column label="条数" width="80">
          <template #default="{ row }">{{ row.item_count }}</template>
        </el-table-column>
        <el-table-column label="大小" width="100">
          <template #default="{ row }">{{ size(row.size_bytes) }}</template>
        </el-table-column>
        <el-table-column label="解析耗时" width="100">
          <template #default="{ row }">{{ row.parse_ms === null ? '—' : `${row.parse_ms} ms` }}</template>
        </el-table-column>
        <el-table-column prop="created_at" label="上传时间" min-width="160" />
        <el-table-column width="130">
          <template #default="{ row }">
            <el-button link type="primary" @click="open(row)">档案与原文件</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination v-model:current-page="page" :page-size="20" :total="total"
                     layout="total, prev, pager, next" style="margin-top: 16px" @current-change="load" />
    </el-card>

    <SourceDrawer v-model="drawerOpen" :source-id="drawerId" />
  </div>
</template>

<style scoped>
.muted { color: var(--el-text-color-secondary); font-size: 13px; }
h1 { margin: 0 0 6px; font-size: 24px; }
.ellipsis { display: inline-block; max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; vertical-align: bottom; }
.tag { margin-left: 6px; }
</style>
