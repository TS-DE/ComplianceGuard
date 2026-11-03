<script setup lang="ts">
/**
 * 话术库：列表/分页/机构筛选/内容搜索/增删改 + 提交审查。
 *
 * 两点刻意的界面决定：
 * 1) 话术长度差异极大，若让表格按内容自适应，行高会忽高忽低、滚动观感很差，
 *    因此统一锁成两行高度，完整内容走 tooltip。
 * 2) 审查结果的「法条依据」必须可点开追到条文原文——这是本系统「可解释」的落点，
 *    只给条号等于让用户自己去翻法条。
 */
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  allClients, scripts, runAudit,
  type Client, type ScriptRow, type AuditResult
} from '../../api/resource'
import ScriptDialog from './ScriptDialog.vue'
import ArticleDrawer from '../law/ArticleDrawer.vue'

const rows = ref<ScriptRow[]>([])
const clients = ref<Client[]>([])
const page = ref(1)
const total = ref(0)
const keyword = ref('')
const clientId = ref<number>()
const loading = ref(false)
const editing = ref(false)
const selected = ref<ScriptRow | null>(null)
const auditing = ref<number | null>(null)
const result = ref<AuditResult | null>(null)
const resultOpen = ref(false)
const articleOpen = ref(false)
const articleCode = ref<string | null>(null)
const articleItemNo = ref<string | null>(null)

async function load() {
  loading.value = true
  try {
    const data = await scripts.list<ScriptRow>({
      page: page.value, page_size: 20,
      client_id: clientId.value, q: keyword.value || undefined
    })
    rows.value = data.items
    total.value = data.total
  } catch {
    // API 层已提示错误，这里保持旧列表避免闪烁。
  } finally {
    loading.value = false
  }
}

function search() { page.value = 1; void load() }
function edit(row: ScriptRow | null) { selected.value = row; editing.value = true }

async function remove(row: ScriptRow) {
  try {
    await scripts.remove(row.id)
    ElMessage.success('话术已删除')
    if (rows.value.length === 1 && page.value > 1) page.value--
    await load()
  } catch {
    // 删除失败保留列表供重试。
  }
}

async function audit(row: ScriptRow) {
  auditing.value = row.id
  try {
    result.value = await runAudit(row)
    resultOpen.value = true
    await load()
  } catch {
    // 请求失败绝不伪造审查结果。
  } finally {
    auditing.value = null
  }
}

function openArticle(code: string, itemNo?: string | null) {
  articleCode.value = code
  articleItemNo.value = itemNo ?? null
  articleOpen.value = true
}

const clientName = (id: number) => clients.value.find(c => c.id === id)?.name ?? `机构 #${id}`
const label = (score: number) =>
  ({ '-1': '判定未完成', '0': '违规', '1': '轻微风险', '2': '合规' } as Record<string, string>)[String(score)] ?? '未知结果'
const alertType = (r: AuditResult) =>
  r.incomplete || r.score === -1 || r.score === 0 ? 'error' : r.score === 1 ? 'warning' : 'success'

onMounted(async () => {
  try {
    clients.value = await allClients()
    await load()
  } catch {
    // 机构接口失败时不白屏，列表仍可展示。
  }
})
</script>

<template>
  <div>
    <p class="muted">CONTENT LIBRARY / 话术管理</p>
    <h1>话术库</h1>
    <p class="muted">统一管理营销原文，提交审查后查看风险与证据。</p>

    <el-card shadow="never">
      <div class="toolbar">
        <el-input v-model="keyword" placeholder="按话术内容搜索" clearable style="width: 260px"
                  maxlength="500" @keyup.enter="search" @clear="search" />
        <el-select v-model="clientId" placeholder="全部机构" clearable filterable style="width: 200px"
                   @change="search">
          <el-option v-for="client in clients" :key="client.id" :label="client.name" :value="client.id" />
        </el-select>
        <el-button @click="search">搜索</el-button>
        <el-button type="primary" @click="edit(null)">新建话术</el-button>
      </div>

      <el-table v-loading="loading" :data="rows" class="script-table" empty-text="暂无话术，请先新建">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column label="机构" min-width="130">
          <template #default="{ row }">{{ clientName(row.client_id) }}</template>
        </el-table-column>
        <el-table-column prop="scene" label="场景" width="100" />
        <el-table-column label="话术内容" min-width="260">
          <template #default="{ row }">
            <el-tooltip :content="row.content" placement="top" :show-after="300">
              <div class="clamp-2">{{ row.content }}</div>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <!-- 未审查用灰色 info，已审查用蓝色 primary：原先两者同为蓝色，扫视时无法区分。 -->
            <el-tag v-if="row.status === 'audited'" type="primary" effect="light">已审查</el-tag>
            <el-tag v-else-if="row.status === 'pending'" type="info" effect="plain">未审查</el-tag>
            <el-tag v-else type="info">已归档</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" min-width="170" />
        <el-table-column label="操作" width="250">
          <template #default="{ row }">
            <el-button link type="primary" @click="edit(row)">编辑</el-button>
            <el-popconfirm title="确定删除这条话术？" confirm-button-text="删除" cancel-button-text="取消"
                           @confirm="remove(row)">
              <template #reference><el-button link type="danger">删除</el-button></template>
            </el-popconfirm>
            <el-button link type="primary" :loading="auditing === row.id"
                       :disabled="auditing !== null" @click="audit(row)">提交审查</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination v-model:current-page="page" :page-size="20" :total="total"
                     layout="total, prev, pager, next" style="margin-top: 24px" @current-change="load" />
    </el-card>

    <ScriptDialog v-model="editing" :clients="clients" :item="selected" @saved="load" />

    <el-dialog v-model="resultOpen" title="审查结果" width="760px">
      <template v-if="result">
        <el-alert
          :title="`${result.incomplete ? '判定未完成' : label(result.score)} · score=${result.score}`"
          :type="alertType(result)" :closable="false" show-icon
        />
        <p class="muted" style="margin-top: 12px">命中条数：{{ result.hit_count }}</p>
        <el-table :data="result.hits" empty-text="无有效命中">
          <el-table-column prop="axis" label="风险轴" width="160" />
          <el-table-column label="法条依据" width="230">
            <template #default="{ row }">
              <el-link type="primary" :underline="false" @click="openArticle(row.law_article, row.item_no)">
                {{ row.law_article }}<span v-if="row.item_no" class="item-hint">{{ row.item_no.slice(row.item_no.indexOf('条') + 1) }}</span>
              </el-link>
            </template>
          </el-table-column>
          <el-table-column prop="quote" label="原文引文" min-width="220" />
        </el-table>
        <p class="muted" style="margin-top: 12px">
          {{ result.disclaimer || '本系统输出为合规风险辅助提示，不构成法律意见' }}
        </p>
      </template>
    </el-dialog>

    <ArticleDrawer v-model="articleOpen" :code="articleCode" :item-no="articleItemNo" />
  </div>
</template>

<style scoped>
.toolbar { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }
.muted { color: var(--el-text-color-secondary); font-size: 13px; }
.item-hint { margin-left: 2px; color: var(--el-color-warning-dark-2); }
/* 统一两行高度：话术长短不一时表格不再忽高忽低。 */
.script-table :deep(.el-table__row) { height: 68px; }
.clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  line-height: 22px;
  max-height: 44px;
}
</style>
