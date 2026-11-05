<script setup lang="ts">
/**
 * 待复核队列（L3 人机回环）。
 *
 * 这一页存在的理由：机器判定必然有拿不准的时候——判定未完成、分级闸降级后的疑似、
 * 以及分数为 1 的轻微风险。如果这些只在别处挂一个"待人工复核"的标签而没有入口，
 * 回环就是假的：没人能处理，系统准确率也永远没有真值。
 *
 * 两个刻意的设计：
 * 1) 裁定是终态，页面明确提示"提交后不可更改"——人工投入不能被后来的点击抹掉；
 * 2) 一致率的分母只算已裁定记录，未裁定时显示"—"而不是 0%，
 *    否则"还没开始复核"看起来会像"一致率为零"。
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  reviewQueue, reviewAudit, reviewStats, axisLabel,
  type ReviewItem, type ReviewStats
} from '../../api/resource'

const loading = ref(false)
const saving = ref(false)
const rows = ref<ReviewItem[]>([])
const total = ref(0)
const page = ref(1)
const stats = ref<ReviewStats | null>(null)
const dialog = ref(false)
const current = ref<ReviewItem | null>(null)
const form = reactive({ verdict: 'confirmed' as 'confirmed' | 'dismissed', note: '' })

const verdictText = (row: ReviewItem) =>
  row.incomplete || row.score === -1 ? '判定未完成'
    : ({ '0': '违规', '1': '疑似违规', '2': '合规' } as Record<string, string>)[String(row.score)] ?? '未知'
const tagType = (row: ReviewItem) =>
  row.incomplete || row.score === -1 || row.score === 0 ? 'danger' : row.score === 1 ? 'warning' : 'success'
const pct = (value: number | null) => (value === null ? '—' : `${(value * 100).toFixed(1)}%`)

async function load() {
  loading.value = true
  try {
    const data = await reviewQueue({ status: 'pending', page: page.value, page_size: 20 })
    rows.value = data.items
    total.value = data.total
  } catch {
    // API 层已提示
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  try {
    stats.value = await reviewStats()
  } catch {
    // 统计失败不影响队列
  }
}

function open(row: ReviewItem, verdict: 'confirmed' | 'dismissed') {
  current.value = row
  form.verdict = verdict
  form.note = ''
  dialog.value = true
}

async function submit() {
  if (!current.value) return
  saving.value = true
  try {
    await reviewAudit(current.value.id, form.verdict, form.note)
    ElMessage.success(form.verdict === 'confirmed' ? '已确认系统判定' : '已记录为人工推翻')
    dialog.value = false
    await Promise.all([load(), loadStats()])
  } catch {
    // 失败保持原状，不假装成功
  } finally {
    saving.value = false
  }
}

onMounted(() => { void load(); void loadStats() })
</script>

<template>
  <div>
    <h1>待复核队列</h1>
    <p class="muted">
      机器拿不准的记录集中在这里：判定未完成、分级闸降级后的疑似、以及轻微风险。
      你的裁定会成为系统准确率的真值来源。
    </p>

    <el-row :gutter="14" class="stats">
      <el-col :span="6">
        <el-card shadow="never" class="stat danger">
          <p class="label">待复核</p>
          <p class="value">{{ stats?.pending ?? 0 }}</p>
          <p class="hint">条待处理</p>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="stat">
          <p class="label">已确认</p>
          <p class="value">{{ stats?.confirmed ?? 0 }}</p>
          <p class="hint">机器判对</p>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="stat">
          <p class="label">已推翻</p>
          <p class="value">{{ stats?.dismissed ?? 0 }}</p>
          <p class="hint">机器判错</p>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="stat">
          <p class="label">判定一致率</p>
          <p class="value">{{ pct(stats?.agree_rate ?? null) }}</p>
          <p class="hint">已裁定 {{ stats?.judged ?? 0 }} 条</p>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" style="margin-top: 16px">
      <el-table v-loading="loading" :data="rows" empty-text="没有待复核记录">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column label="被审话术" min-width="300">
          <template #default="{ row }">
            <span class="ellipsis" :title="row.script_content || ''">{{ row.script_content || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="机器结论" width="130">
          <template #default="{ row }">
            <el-tag :type="tagType(row)" effect="light">{{ verdictText(row) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="命中" width="80">
          <template #default="{ row }">{{ row.hit_count }}</template>
        </el-table-column>
        <el-table-column label="命中要点" min-width="220">
          <template #default="{ row }">
            <span v-if="!row.hits?.length" class="muted">无有效命中</span>
            <span v-for="(hit, i) in row.hits" :key="i" class="hit-line">
              {{ axisLabel(hit.axis) }}：{{ hit.quote }}
              <el-tag v-if="hit.downgraded" size="small" type="warning" effect="plain">已降级</el-tag>
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="时间" width="180" />
        <el-table-column label="操作" width="180">
          <template #default="{ row }">
            <el-button link type="danger" @click="open(row, 'confirmed')">确认违规</el-button>
            <el-button link type="primary" @click="open(row, 'dismissed')">推翻</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination v-model:current-page="page" :page-size="20" :total="total"
                     layout="total, prev, pager, next" style="margin-top: 20px" @current-change="load" />
    </el-card>

    <el-dialog v-model="dialog" width="720px"
               :title="form.verdict === 'confirmed' ? '确认机器判定' : '推翻机器判定'">
      <template v-if="current">
        <p class="dlg-label">被审话术</p>
        <p class="quote-box">{{ current.script_content || '—' }}</p>

        <p class="dlg-label">命中明细</p>
        <div v-if="!current.hits?.length" class="muted">无有效命中（该条可能是判定未完成）</div>
        <div v-for="(hit, i) in current.hits" :key="i" class="hit-card">
          <p class="hit-head">
            <el-tag size="small" :type="hit.downgraded ? 'warning' : 'danger'" effect="light">
              {{ axisLabel(hit.axis) }}
            </el-tag>
            <el-tag v-if="hit.downgraded" size="small" type="warning" effect="plain">已降级</el-tag>
            <span class="law">{{ hit.law_article }}</span>
          </p>
          <p class="hit-quote">原文：{{ hit.quote }}</p>
          <p v-if="hit.reason" class="hit-reason">理由：{{ hit.reason }}</p>
        </div>

        <p class="dlg-label">复核备注（可选，会随裁定一起存档）</p>
        <el-input v-model="form.note" type="textarea" :rows="3" maxlength="500" show-word-limit
                  placeholder="如：属预后描述，判罚偏严；或：确实是保证性承诺" />
        <el-alert type="warning" :closable="false" style="margin-top: 12px"
                  title="裁定提交后不可更改——它是系统准确率的真值来源，不能反复改写。" />
      </template>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button :type="form.verdict === 'confirmed' ? 'danger' : 'primary'"
                   :loading="saving" @click="submit">
          {{ form.verdict === 'confirmed' ? '确认为违规' : '确认推翻' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.muted { color: var(--el-text-color-secondary); font-size: 13px; }
h1 { margin: 0 0 6px; font-size: 24px; }
.stats { margin-top: 16px; }
.stat { text-align: center; }
.stat.danger .value { color: var(--el-color-danger); }
.label { margin: 0; font-size: 12px; color: var(--el-text-color-secondary); }
.value { margin: 8px 0 2px; font-size: 28px; font-weight: 700; line-height: 1; }
.hint { margin: 0; font-size: 12px; color: var(--el-text-color-placeholder); }
.ellipsis { display: inline-block; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; vertical-align: bottom; }
.hit-line { display: block; font-size: 12px; line-height: 1.7; }
.dlg-label { margin: 14px 0 6px; font-size: 13px; font-weight: 600; }
.quote-box { margin: 0; padding: 10px 12px; background: var(--el-fill-color-lighter); border-radius: 6px; line-height: 1.7; white-space: pre-wrap; }
.hit-card { border: 1px solid var(--el-border-color-lighter); border-radius: 6px; padding: 10px 12px; margin-bottom: 8px; }
.hit-head { margin: 0 0 6px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.law { font-size: 12px; color: var(--el-text-color-secondary); }
.hit-quote { margin: 0 0 4px; font-size: 13px; line-height: 1.6; }
.hit-reason { margin: 0; font-size: 12px; line-height: 1.6; color: var(--el-text-color-regular); }
</style>
