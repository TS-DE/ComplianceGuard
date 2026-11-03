<script setup lang="ts">
/**
 * 红队压测结果：四格矩阵（TP 拆成 target/other）+ 样本逐条 verdict。
 *
 * 关键取舍：TP 必须拆成 TP_axis 与 TP_other。
 * 「整体被判违规」不等于「目标轴抓到了」——被别的轴顺手抓住的样本，
 * 对本次压测的目标轴而言等于漏杀，混在一起会把漏杀率算低。
 * 另外 unjudged（判定未完成）单列且不进入任何一格，否则会污染率值。
 */
import type { RedTeamCounts, RedTeamGaps, RedTeamSample } from '../../api/resource'

defineProps<{ data: RedTeamGaps }>()

const VERDICT_META: Record<string, { text: string; type: 'success' | 'danger' | 'warning' | 'info' }> = {
  TP_axis: { text: '命中目标轴', type: 'success' },
  TP_other: { text: '他轴命中', type: 'warning' },
  FN: { text: '漏杀', type: 'danger' },
  FP: { text: '误杀', type: 'danger' },
  TN: { text: '正确放行', type: 'success' },
  unjudged: { text: '未判定', type: 'info' }
}
const verdictOf = (sample: RedTeamSample) => sample.meta?.verdict ?? 'unjudged'
const verdictMeta = (sample: RedTeamSample) => VERDICT_META[verdictOf(sample)] ?? VERDICT_META.unjudged
const pct = (value: number) => `${(value * 100).toFixed(2)}%`
const cells: { key: keyof RedTeamCounts; label: string; danger?: boolean }[] = [
  { key: 'TP_axis', label: '命中目标轴' },
  { key: 'TP_other', label: '他轴命中' },
  { key: 'FN', label: '漏杀', danger: true },
  { key: 'FP', label: '误杀', danger: true },
  { key: 'TN', label: '正确放行' },
  { key: 'unjudged', label: '未判定' }
]
const axisKeys = (counts?: Partial<RedTeamCounts>) =>
  cells.map(cell => `${cell.label} ${counts?.[cell.key] ?? 0}`).join(' · ')
</script>

<template>
  <div class="result">
    <el-row :gutter="12">
      <el-col v-for="cell in cells" :key="cell.key" :span="4">
        <el-card shadow="never" class="cell" :class="{ danger: cell.danger && data.counts[cell.key] > 0 }">
          <p class="cell-label">{{ cell.label }}</p>
          <p class="cell-value">{{ data.counts[cell.key] }}</p>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="12" style="margin-top: 12px">
      <el-col :span="6">
        <el-card shadow="never">
          <p class="cell-label">整体漏杀率</p>
          <p class="cell-value small">{{ pct(data.fn_rate) }}</p>
          <p class="hint">= FN / (TP_axis + TP_other + FN)</p>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never">
          <p class="cell-label">轴级漏杀率</p>
          <p class="cell-value small">{{ pct(data.axis_fn_rate) }}</p>
          <p class="hint">= (FN + TP_other) / 预期违规数</p>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never">
          <p class="cell-label">误杀率</p>
          <p class="cell-value small">{{ pct(data.fp_rate) }}</p>
          <p class="hint">= FP / (FP + TN)</p>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never">
          <p class="cell-label">整体准确率</p>
          <p class="cell-value small">{{ pct(data.accuracy) }}</p>
          <p class="hint">= (TP_axis + TP_other + TN) / 生成数</p>
        </el-card>
      </el-col>
    </el-row>

    <el-alert type="warning" :closable="false" show-icon style="margin-top: 12px"
              :title="`样本量 ${data.generated}，仅作内部对比，不具统计代表性；判定未完成 ${data.counts.unjudged} 条不计入任何一格。`" />

    <el-card shadow="never" style="margin-top: 16px">
      <h3>按目标轴</h3>
      <el-table :data="Object.entries(data.by_axis).map(([axis, counts]) => ({ axis, counts }))"
                size="small" empty-text="无分轴数据">
        <el-table-column prop="axis" label="目标轴" width="220" />
        <el-table-column label="判定分布">
          <template #default="{ row }">{{ axisKeys(row.counts) }}</template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" style="margin-top: 16px">
      <h3>样本明细（{{ data.samples.length }}）</h3>
      <el-table :data="data.samples" size="small">
        <el-table-column label="编号" width="90">
          <template #default="{ row }">{{ row.client_id }}-{{ row.id }}</template>
        </el-table-column>
        <el-table-column label="档位" width="80">
          <template #default="{ row }">{{ row.meta?.strength ?? '—' }}</template>
        </el-table-column>
        <el-table-column prop="content" label="生成话术" min-width="300" show-overflow-tooltip />
        <el-table-column label="判定" width="120">
          <template #default="{ row }">
            <el-tag :type="verdictMeta(row).type" effect="light" size="small">{{ verdictMeta(row).text }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="分数" width="70">
          <template #default="{ row }">{{ row.meta?.score ?? '—' }}</template>
        </el-table-column>
        <el-table-column label="实际命中轴" min-width="180">
          <template #default="{ row }">
            <span v-if="row.meta?.actual_axes?.length">{{ row.meta.actual_axes.join('、') }}</span>
            <span v-else class="muted">无</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<style scoped>
.cell { text-align: center; }
.cell.danger { border-color: var(--el-color-danger-light-5); background: var(--el-color-danger-light-9); }
.cell-label { margin: 0; font-size: 12px; color: var(--el-text-color-secondary); }
.cell-value { margin: 6px 0 0; font-size: 24px; font-weight: 700; }
.cell-value.small { font-size: 20px; }
.hint { margin: 4px 0 0; font-size: 11px; color: var(--el-text-color-placeholder); }
.muted { color: var(--el-text-color-secondary); }
h3 { margin: 0 0 12px; font-size: 14px; font-weight: 600; }
</style>
