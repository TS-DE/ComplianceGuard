<script setup lang="ts">
/**
 * 话术库：按机构分组的二级列表 + 平铺列表两种视图。
 *
 * 为什么是「机构ID-话术ID」（9-46）而不是「机构内第几条」（9-1）：
 * 后者是动态序号，删掉中间某条会让后续编号整体漂移，而 audits.script_id 存的是全局话术 ID，
 * 编号一漂移审计记录就指向了别的话术。所以取复合编号时必须用稳定主键，不能用排序位次。
 *
 * 分组视图按需加载（展开某机构才拉它的话术）；搜索/筛选需要全局视野，会自动切回平铺。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  allClients, scripts, runAudit,
  type Client, type ScriptRow, type AuditResult
} from '../../api/resource'
import ScriptDialog from './ScriptDialog.vue'
import ScriptImport from './ScriptImport.vue'
import ArticleDrawer from '../law/ArticleDrawer.vue'

interface ScriptNode extends ScriptRow {
  rowKey: string
  kind: 'script'
}
interface ClientNode {
  rowKey: string
  kind: 'client'
  clientId: number
  clientName: string
  count: number | null
  hasChildren: boolean
  children: ScriptNode[]
}

const router = useRouter()
const rows = ref<ScriptRow[]>([])
const clients = ref<Client[]>([])
const page = ref(1)
const total = ref(0)
const keyword = ref('')
const clientId = ref<number>()
const loading = ref(false)
const editing = ref(false)
const importOpen = ref(false)
const selected = ref<ScriptRow | null>(null)
const auditing = ref<number | null>(null)
const auditScriptId = ref(0)
const result = ref<AuditResult | null>(null)
const resultOpen = ref(false)
const articleOpen = ref(false)
const articleCode = ref<string | null>(null)
const articleItemNo = ref<string | null>(null)

const viewMode = ref<'group' | 'flat'>('group')
const groupNodes = ref<ClientNode[]>([])
const groupLoading = ref(false)
const tableRef = ref()

/** 复合编号：机构ID-话术ID，唯一且稳定。 */
const code = (row: ScriptRow) => `${row.client_id}-${row.id}`
const clientName = (id: number) => clients.value.find(c => c.id === id)?.name ?? `机构 #${id}`

async function loadFlat() {
  loading.value = true
  try {
    const data = await scripts.list<ScriptRow>({
      page: page.value, page_size: 20,
      client_id: clientId.value, q: keyword.value || undefined
    })
    rows.value = data.items
    total.value = data.total
  } catch {
    // API 层已提示。
  } finally {
    loading.value = false
  }
}

async function loadGroups() {
  groupLoading.value = true
  try {
    if (!clients.value.length) clients.value = await allClients()
    const scoped = clientId.value ? clients.value.filter(c => c.id === clientId.value) : clients.value
    // 故意用预先加载而不是 el-table 的 lazy 回调：
    // 全库话术量很小（几十条），一次取回直接填 children 更可靠——
    // lazy 回调一旦签名或返回值处理有偏差，界面就会一直转圈且没有错误提示。
    // page_size 上限 100（超过后端 400），单机构超过 100 条需改为子列表分页。
    const pages = await Promise.all(scoped.map(client =>
      scripts.list<ScriptRow>({ page: 1, page_size: 100, client_id: client.id })
        .catch(() => ({ items: [] as ScriptRow[], total: 0 }))
    ))
    groupNodes.value = scoped.map((client, index) => ({
      rowKey: `c-${client.id}`,
      kind: 'client',
      clientId: client.id,
      clientName: client.name,
      count: pages[index].total,
      hasChildren: pages[index].items.length > 0,
      // 子行必须带唯一 rowKey：el-table 的 row-key 取的是 row.rowKey，
      // 缺失会让所有子行共用 undefined，展开状态互相串。
      children: pages[index].items.map(item => ({
        ...item, rowKey: `s-${item.id}`, kind: 'script' as const
      }))
    }))
  } catch {
    // 分组失败时保持空态，不伪造数据。
  } finally {
    groupLoading.value = false
  }
}

/** 展开/收起全部：children 已预加载，直接切换展开状态即可。 */
function expandAll(expand: boolean) {
  const table = tableRef.value
  if (!table) return
  groupNodes.value.forEach(node => table.toggleRowExpansion(node, expand))
}

async function refresh() {
  if (viewMode.value === 'group') await loadGroups()
  else await loadFlat()
}

function search() {
  // 搜索/筛选是跨机构的，分组视图下没有意义，自动切平铺并提示，避免结果"看起来没变化"。
  if (viewMode.value === 'group') {
    viewMode.value = 'flat'
    ElMessage.info('搜索已在平铺视图执行')
  }
  page.value = 1
  void loadFlat()
}

async function switchMode(mode: 'group' | 'flat') {
  if (viewMode.value === mode) return
  viewMode.value = mode
  page.value = 1
  await refresh()
}

function edit(row: ScriptRow | null) { selected.value = row; editing.value = true }

async function remove(row: ScriptRow) {
  try {
    await scripts.remove(row.id)
    ElMessage.success('话术已删除')
    if (viewMode.value === 'flat' && rows.value.length === 1 && page.value > 1) page.value--
    await refresh()
  } catch {
    // 删除失败保留列表供重试。
  }
}

async function audit(row: ScriptRow) {
  auditing.value = row.id
  auditScriptId.value = row.id
  try {
    result.value = await runAudit(row)
    resultOpen.value = true
    await refresh()
  } catch {
    // 请求失败绝不伪造审查结果。
  } finally {
    auditing.value = null
  }
}

function openArticle(codeValue: string, itemNo?: string | null) {
  articleCode.value = codeValue
  articleItemNo.value = itemNo ?? null
  articleOpen.value = true
}

function gotoAudits(scriptId: number) {
  resultOpen.value = false
  void router.push({ path: '/audits', query: { script_id: String(scriptId) } })
}

const label = (score: number) =>
  ({ '-1': '判定未完成', '0': '违规', '1': '轻微风险', '2': '合规' } as Record<string, string>)[String(score)] ?? '未知结果'
const alertType = (r: AuditResult) =>
  r.incomplete || r.score === -1 || r.score === 0 ? 'error' : r.score === 1 ? 'warning' : 'success'
const canAudit = computed(() => auditing.value === null)

onMounted(async () => {
  try {
    clients.value = await allClients()
    await loadGroups()
  } catch {
    // 机构接口失败时不白屏。
  }
})
</script>

<template>
  <div>
    <p class="muted">CONTENT LIBRARY / 话术管理</p>
    <h1>话术库</h1>
    <p class="muted">话术按机构归属，编号为「机构ID-话术ID」（如 9-46），可直接追溯到审查记录。</p>

    <el-card shadow="never">
      <div class="toolbar">
        <el-radio-group :model-value="viewMode" @change="switchMode($event as 'group' | 'flat')">
          <el-radio-button value="group">按机构分组</el-radio-button>
          <el-radio-button value="flat">平铺列表</el-radio-button>
        </el-radio-group>
        <el-input v-model="keyword" placeholder="按话术内容搜索" clearable style="width: 240px"
                  maxlength="500" @keyup.enter="search" @clear="search" />
        <el-select v-model="clientId" placeholder="全部机构" clearable filterable style="width: 190px"
                   @change="search">
          <el-option v-for="client in clients" :key="client.id" :label="`${client.id} · ${client.name}`"
                     :value="client.id" />
        </el-select>
        <el-button @click="search">搜索</el-button>
        <el-button type="primary" @click="edit(null)">新建话术</el-button>
        <!-- 商家素材通常是一整页文档，逐条手录不现实，因此提供批量导入入口 -->
        <el-button @click="importOpen = true">批量导入</el-button>
        <template v-if="viewMode === 'group'">
          <el-button @click="expandAll(true)">展开全部</el-button>
          <el-button @click="expandAll(false)">收起全部</el-button>
        </template>
      </div>

      <!-- 分组视图：机构 -> 话术，展开才加载 -->
      <el-table v-if="viewMode === 'group'" ref="tableRef" v-loading="groupLoading" :data="groupNodes"
                row-key="rowKey" :tree-props="{ children: 'children', hasChildren: 'hasChildren' }"
                class="script-table" empty-text="暂无机构或机构下暂无话术">
        <el-table-column label="机构 / 话术" min-width="330">
          <template #default="{ row }">
            <template v-if="row.kind === 'client'">
              <span class="client-code">{{ row.clientId }}</span>
              <span class="client-name">{{ row.clientName }}</span>
              <el-tag size="small" type="info" effect="plain" style="margin-left: 8px">
                {{ row.count === null ? '…' : `${row.count} 条话术` }}
              </el-tag>
            </template>
            <template v-else>
              <span class="script-code">{{ row.client_id }}-{{ row.id }}</span>
              <span class="clamp-2 inline">{{ row.content }}</span>
            </template>
          </template>
        </el-table-column>
        <el-table-column label="场景" width="110">
          <template #default="{ row }">{{ row.kind === 'client' ? '' : row.scene }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <template v-if="row.kind === 'script'">
              <el-tag v-if="row.status === 'audited'" type="primary" effect="light">已审查</el-tag>
              <el-tag v-else-if="row.status === 'pending'" type="info" effect="plain">未审查</el-tag>
              <el-tag v-else type="info">已归档</el-tag>
            </template>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">{{ row.kind === 'client' ? '' : row.created_at }}</template>
        </el-table-column>
        <el-table-column label="操作" width="250">
          <template #default="{ row }">
            <template v-if="row.kind === 'script'">
              <el-button link type="primary" @click="edit(row)">编辑</el-button>
              <el-popconfirm title="确定删除这条话术？" confirm-button-text="删除" cancel-button-text="取消"
                             @confirm="remove(row)">
                <template #reference><el-button link type="danger">删除</el-button></template>
              </el-popconfirm>
              <el-button link type="primary" :loading="auditing === row.id" :disabled="!canAudit"
                         @click="audit(row)">提交审查</el-button>
            </template>
          </template>
        </el-table-column>
        <el-table-column width="56" align="center">
          <template #default="{ row }">
            <el-tooltip v-if="row.kind === 'script' && row.status === 'audited'" content="查看审查记录" placement="left">
              <el-button link type="primary" class="goto" @click="gotoAudits(row.id)">›</el-button>
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table>

      <!-- 平铺视图：保留搜索与分页 -->
      <template v-else>
        <el-table v-loading="loading" :data="rows" class="script-table" empty-text="暂无话术，请先新建">
          <el-table-column label="编号" width="110">
            <template #default="{ row }"><span class="script-code">{{ code(row) }}</span></template>
          </el-table-column>
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
              <el-button link type="primary" :loading="auditing === row.id" :disabled="!canAudit"
                         @click="audit(row)">提交审查</el-button>
            </template>
          </el-table-column>
          <el-table-column width="56" align="center">
            <template #default="{ row }">
              <el-tooltip v-if="row.status === 'audited'" content="查看审查记录" placement="left">
                <el-button link type="primary" class="goto" @click="gotoAudits(row.id)">›</el-button>
              </el-tooltip>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
        </el-table>

        <el-pagination v-model:current-page="page" :page-size="20" :total="total"
                       layout="total, prev, pager, next" style="margin-top: 24px" @current-change="loadFlat" />
      </template>
    </el-card>

    <ScriptDialog v-model="editing" :clients="clients" :item="selected" @saved="refresh" />
    <ScriptImport v-model="importOpen" :clients="clients" @imported="refresh" />

    <el-dialog v-model="resultOpen" title="审查结果" width="760px">
      <template v-if="result">
        <el-alert :title="`${result.incomplete ? '判定未完成' : label(result.score)} · score=${result.score}`"
                  :type="alertType(result)" :closable="false" show-icon />
        <p class="muted" style="margin-top: 12px">命中条数：{{ result.hit_count }}</p>
        <el-table :data="result.hits" empty-text="无有效命中">
          <el-table-column prop="axis" label="风险轴" width="150" />
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
      <template #footer>
        <el-button @click="resultOpen = false">关闭</el-button>
        <el-button v-if="result" type="primary" @click="gotoAudits(auditScriptId)">
          查看该话术的审查记录 ›
        </el-button>
      </template>
    </el-dialog>

    <ArticleDrawer v-model="articleOpen" :code="articleCode" :item-no="articleItemNo" />
  </div>
</template>

<style scoped>
.toolbar { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; margin-bottom: 16px; }
.muted { color: var(--el-text-color-secondary); font-size: 13px; }
.item-hint { margin-left: 2px; color: var(--el-color-warning-dark-2); }
.goto { font-size: 20px; line-height: 1; font-weight: 700; }
.client-code { display: inline-block; min-width: 26px; font-weight: 700; color: var(--el-color-primary); }
.client-name { font-weight: 600; }
.script-code { display: inline-block; min-width: 56px; color: var(--el-color-primary);
  font-variant-numeric: tabular-nums; margin-right: 8px; }
.script-table :deep(.el-table__row) { height: 68px; }
.clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  line-height: 22px;
  max-height: 44px;
}
.clamp-2.inline { display: inline; -webkit-line-clamp: unset; max-height: none; }
</style>
