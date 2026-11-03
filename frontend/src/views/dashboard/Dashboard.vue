<script setup lang="ts">
/**
 * 工作台：一天的审计概览。
 *
 * 数据全部来自日报接口的 SQL 聚合，前端不做任何二次计算——
 * 报告里的每个数字都必须能在数据库里复算出来，否则就不该出现在这里。
 * 「未完成」单列且标红：判定未完成绝不能被算进合规。
 */
import { computed, onMounted, ref } from 'vue'
import { dailyReport, type DailyReport } from '../../api/resource'

const data = ref<DailyReport | null>(null)
const loading = ref(false)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    data.value = await dailyReport()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '日报加载失败'
  } finally {
    loading.value = false
  }
}

const axisRows = computed(() =>
  Object.entries(data.value?.by_axis ?? {})
    .sort((a, b) => b[1] - a[1])
    .map(([axis, count]) => ({ axis, count }))
)
const maxAxis = computed(() => Math.max(1, ...axisRows.value.map(row => row.count)))
const percent = (value: number) => `${Math.round(value * 100)}%`

onMounted(load)
</script>

<template>
  <div v-loading="loading">
    <p class="muted">COMPLIANCE WORKSPACE / 工作台</p>
    <h1>工作台</h1>
    <p class="muted">{{ data?.date ?? '今日' }} 的审查概览，数据来自审计表聚合。</p>

    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon style="margin-bottom: 16px" />

    <template v-if="data">
      <el-row :gutter="16">
        <el-col :span="6"><el-card shadow="never"><el-statistic title="今日审查" :value="data.total" /></el-card></el-col>
        <el-col :span="6"><el-card shadow="never"><el-statistic title="违规" :value="data.violations" /></el-card></el-col>
        <el-col :span="6">
          <el-card shadow="never">
            <el-statistic title="违规率" :value="Number(percent(data.violation_rate).replace('%', ''))" suffix="%" />
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="never">
            <el-statistic title="未完成（不计入合规）" :value="data.incomplete"
                          :value-style="data.incomplete > 0 ? { color: 'var(--el-color-danger)' } : undefined" />
          </el-card>
        </el-col>
      </el-row>

      <el-row :gutter="16" style="margin-top: 16px">
        <el-col :span="6"><el-card shadow="never"><el-statistic title="合规放行" :value="data.compliant" /></el-card></el-col>
        <el-col :span="6">
          <el-card shadow="never">
            <el-statistic title="平均耗时" :value="Math.round(Number(data.average_latency_ms))" suffix="ms" />
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="never">
            <el-statistic :title="data.cost === null ? '已知成本小计' : '累计成本'"
                          :value="Number(data.cost ?? data.known_cost_subtotal ?? 0)" :precision="6">
              <template #suffix><span style="font-size: 13px">元</span></template>
            </el-statistic>
            <p v-if="data.cost === null" class="unpriced">
              含 {{ data.unpriced }} 条未计价，不显示伪合计
            </p>
            <p v-else-if="data.unpriced > 0" class="unpriced">另有 {{ data.unpriced }} 条未计价</p>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="never">
            <p class="summary">{{ data.summary }}</p>
          </el-card>
        </el-col>
      </el-row>

      <el-card shadow="never" style="margin-top: 16px">
        <h3>按风险轴分布</h3>
        <el-empty v-if="!axisRows.length" description="今日暂无命中" :image-size="80" />
        <div v-for="row in axisRows" :key="row.axis" class="axis-row">
          <span class="axis-name">{{ row.axis }}</span>
          <div class="axis-bar"><i :style="{ width: `${(row.count / maxAxis) * 100}%` }" /></div>
          <span class="axis-count">{{ row.count }}</span>
        </div>
      </el-card>

      <p class="muted" style="margin-top: 16px">{{ data.disclaimer }}</p>
    </template>
  </div>
</template>

<style scoped>
.muted { color: var(--el-text-color-secondary); font-size: 13px; }
.unpriced { margin: 6px 0 0; color: var(--el-color-warning-dark-2); font-size: 12px; }
.summary { margin: 0; font-size: 13px; color: var(--el-text-color-regular); line-height: 1.7; }
h3 { margin: 0 0 14px; font-size: 14px; font-weight: 600; }
.axis-row { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
.axis-name { width: 190px; font-size: 13px; color: var(--el-text-color-regular); }
.axis-bar { flex: 1; height: 10px; background: var(--el-fill-color-light); border-radius: 5px; overflow: hidden; }
.axis-bar i { display: block; height: 100%; background: var(--el-color-primary); border-radius: 5px; }
.axis-count { width: 40px; text-align: right; font-size: 13px; }
</style>
