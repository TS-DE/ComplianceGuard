<script setup lang="ts">
/**
 * 审查记录：系统每天产出的审计流水，是「可追溯」的主证据面。
 *
 * 表格里刻意把「未完成」与「违规」分色：判定未完成是红色警示，
 * 不能因为 score=-1 看上去不是 2 就被误读成没问题。
 */
import { onMounted, ref } from 'vue'
import { audits, type AuditRow } from '../../api/resource'
import AuditDetail from './AuditDetail.vue'

const rows = ref<AuditRow[]>([])
const page = ref(1)
const total = ref(0)
const loading = ref(false)
const open = ref(false)
const current = ref<AuditRow | null>(null)

async function load() {
  loading.value = true
  try {
    const data = await audits.list<AuditRow>({ page: page.value, page_size: 20 })
    rows.value = data.items
    total.value = data.total
  } catch {
    // API 层已提示。
  } finally {
    loading.value = false
  }
}

function detail(row: AuditRow) {
  current.value = row
  open.value = true
}

const label = (row: AuditRow) =>
  row.incomplete || row.score === -1 ? '判定未完成'
    : ({ '0': '违规', '1': '轻微风险', '2': '合规' } as Record<string, string>)[String(row.score)] ?? '未知'
const tagType = (row: AuditRow) =>
  row.incomplete || row.score === -1 || row.score === 0 ? 'danger' : row.score === 1 ? 'warning' : 'success'

onMounted(load)
</script>

<template>
  <div>
    <p class="muted">AUDIT TRAIL / 审查记录</p>
    <h1>审查记录</h1>
    <p class="muted">每一次审查的分数、命中条款、引文、成本与耗时都可回溯。</p>

    <el-card shadow="never">
      <el-table v-loading="loading" :data="rows" empty-text="暂无审查记录，请到话术库提交审查">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="script_id" label="话术 ID" width="100" />
        <el-table-column label="结论" width="130">
          <template #default="{ row }">
            <el-tag :type="tagType(row)" effect="light">{{ label(row) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="hit_count" label="命中" width="80" />
        <el-table-column label="成本" width="130">
          <template #default="{ row }">
            <span v-if="row.cost === null" class="unpriced">未计价</span>
            <span v-else>{{ row.cost }} 元</span>
          </template>
        </el-table-column>
        <el-table-column label="耗时" width="110">
          <template #default="{ row }">{{ row.latency_ms }} ms</template>
        </el-table-column>
        <el-table-column prop="model" label="模型" min-width="140" />
        <el-table-column prop="created_at" label="时间" min-width="170" />
        <el-table-column label="操作" width="110">
          <template #default="{ row }">
            <el-button link type="primary" @click="detail(row)">查看详情</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination v-model:current-page="page" :page-size="20" :total="total"
                     layout="total, prev, pager, next" style="margin-top: 24px" @current-change="load" />
    </el-card>

    <AuditDetail v-model="open" :row="current" @rewritten="load" />
  </div>
</template>

<style scoped>
.muted { color: var(--el-text-color-secondary); font-size: 13px; }
.unpriced { color: var(--el-color-warning-dark-2); }
</style>
