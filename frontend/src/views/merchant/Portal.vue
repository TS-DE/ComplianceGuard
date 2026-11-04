<script setup lang="ts">
/**
 * 商家端首页：只回答三个问题——今天查了多少、有几条要改、下一步点哪里。
 *
 * 数字来自 getReportsDaily，服务端已按机构裁剪（商家看不到平台总量），
 * 所以这里可以直接展示，不需要在前端再过滤一遍。
 */
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { dailyReport, audits, type AuditRow, type DailyReport } from '../../api/resource'
import { useAuth } from '../../stores/auth'

const router = useRouter()
const auth = useAuth()
const report = ref<DailyReport | null>(null)
const recent = ref<AuditRow[]>([])
const loading = ref(false)

const today = () => {
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

async function load() {
  loading.value = true
  try {
    report.value = await dailyReport(today())
  } catch {
    // 日报失败不影响快捷入口使用
  }
  try {
    const page = await audits.list<AuditRow>({ page: 1, page_size: 5 })
    recent.value = page.items
  } catch {
    // 同上
  } finally {
    loading.value = false
  }
}

const verdict = (row: AuditRow) =>
  row.incomplete || row.score === -1 ? '判定未完成'
    : ({ '0': '违规', '1': '轻微风险', '2': '合规' } as Record<string, string>)[String(row.score)] ?? '未知'
const tagType = (row: AuditRow) =>
  row.incomplete || row.score === -1 || row.score === 0 ? 'danger' : row.score === 1 ? 'warning' : 'success'

onMounted(load)
</script>

<template>
  <div v-loading="loading">
    <h1>我的工作台</h1>
    <p class="muted">{{ auth.user?.username }} · 今天还没查文案的话，从「文案检查」开始。</p>

    <el-row :gutter="14" class="stats">
      <el-col :span="6">
        <el-card shadow="never" class="stat">
          <p class="label">今日审查</p>
          <p class="value">{{ report?.total ?? 0 }}</p>
          <p class="hint">条</p>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="stat danger">
          <p class="label">违规</p>
          <p class="value">{{ report?.violations ?? 0 }}</p>
          <p class="hint">需要修改</p>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="stat">
          <p class="label">合规</p>
          <p class="value">{{ report?.compliant ?? 0 }}</p>
          <p class="hint">可直接使用</p>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="stat">
          <p class="label">判定未完成</p>
          <p class="value">{{ report?.incomplete ?? 0 }}</p>
          <p class="hint">需人工复核</p>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="quick">
      <h3>开始检查</h3>
      <p class="muted">把文案粘贴进来或上传文档，系统会切分后逐条审查，违规的会指出违反哪一条并给出理由。</p>
      <el-button type="primary" size="large" @click="router.push('/merchant/check')">文案检查</el-button>
      <el-button size="large" @click="router.push('/merchant/scripts')">我的话术</el-button>
      <el-button size="large" @click="router.push('/merchant/audits')">审查历史</el-button>
    </el-card>

    <el-card shadow="never" style="margin-top: 16px">
      <h3>最近审查</h3>
      <el-table :data="recent" size="small" empty-text="还没有审查记录">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column label="话术" min-width="320">
          <template #default="{ row }">
            <span class="ellipsis" :title="row.script_content || ''">{{ row.script_content || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="结论" width="120">
          <template #default="{ row }"><el-tag :type="tagType(row)" effect="light">{{ verdict(row) }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="hit_count" label="命中" width="80" />
        <el-table-column prop="created_at" label="时间" min-width="170" />
      </el-table>
    </el-card>
  </div>
</template>

<style scoped>
.muted { color: var(--el-text-color-secondary); font-size: 13px; }
h1 { margin: 0 0 6px; font-size: 24px; }
h3 { margin: 0 0 10px; font-size: 15px; }
.stats { margin-top: 16px; }
.stat { text-align: center; }
.stat.danger .value { color: var(--el-color-danger); }
.label { margin: 0; font-size: 12px; color: var(--el-text-color-secondary); }
.value { margin: 8px 0 2px; font-size: 30px; font-weight: 700; line-height: 1; }
.hint { margin: 0; font-size: 12px; color: var(--el-text-color-placeholder); }
.quick { margin-top: 16px; }
.quick .el-button { margin-top: 8px; margin-right: 10px; }
.ellipsis { display: inline-block; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; vertical-align: bottom; }
</style>
