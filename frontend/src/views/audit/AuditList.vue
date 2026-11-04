<script setup lang="ts">
/**
 * 审查记录：系统每天产出的审计流水，是「可追溯」的主证据面。
 *
 * 表格里刻意把「未完成」与「违规」分色：判定未完成是红色警示，
 * 不能因为 score=-1 看上去不是 2 就被误读成没问题。
 */
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { audits, type AuditRow } from '../../api/resource'
import { copyText } from '../../utils/clipboard'
import AuditDetail from './AuditDetail.vue'

const route = useRoute()
const router = useRouter()
const rows = ref<AuditRow[]>([])
const page = ref(1)
const total = ref(0)
const loading = ref(false)
const open = ref(false)
const current = ref<AuditRow | null>(null)
// 从话术库跳过来时带 script_id，只显示该话术的审查历史（可能多条）。
const scriptId = ref<number | null>(route.query.script_id ? Number(route.query.script_id) : null)

async function load() {
  loading.value = true
  try {
    const data = await audits.list<AuditRow>({
      page: page.value, page_size: 20,
      script_id: scriptId.value ?? undefined
    })
    rows.value = data.items
    total.value = data.total
  } catch {
    // API 层已提示。
  } finally {
    loading.value = false
  }
}

function clearFilter() {
  scriptId.value = null
  page.value = 1
  void router.replace({ path: '/audits' })
  void load()
}

// 同一个页面内再次跳转时 router 不会重建组件，靠 watch 响应 query 变化。
watch(() => route.query.script_id, value => {
  scriptId.value = value ? Number(value) : null
  page.value = 1
  void load()
})

function detail(row: AuditRow) {
  current.value = row
  open.value = true
}

async function copyRow(row: AuditRow) {
  if (!row.script_content) return
  const done = await copyText(row.script_content)
  if (done) ElMessage.success('已复制原话术')
  else ElMessage.error('复制失败，请手动选中')
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
      <el-alert v-if="scriptId" type="info" :closable="false" show-icon style="margin-bottom: 12px"
                :title="`仅显示话术 #${scriptId} 的审查历史（共 ${total} 条）`">
        <el-button link type="primary" @click="clearFilter">显示全部审查记录</el-button>
      </el-alert>

      <el-table v-loading="loading" :data="rows" empty-text="暂无审查记录，请到话术库提交审查">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column label="被审话术" min-width="300">
          <template #default="{ row }">
            <div class="script-cell">
              <span class="script-no">#{{ row.script_id }}</span>
              <span class="script-text" :title="row.script_content || ''">
                {{ row.script_content || '（话术已删除）' }}
              </span>
              <el-button v-if="row.script_content" link type="primary" size="small"
                         @click.stop="copyRow(row)">复制</el-button>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="结论" width="120">
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
/* 话术内容可能很长：单行截断 + hover 看全文 + 右侧复制按钮 */
.script-cell { display: flex; align-items: center; gap: 8px; }
.script-no { flex: none; color: var(--el-text-color-secondary); font-variant-numeric: tabular-nums; }
.script-text {
  flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
</style>
