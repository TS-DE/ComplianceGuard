<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { allClients, scripts, runAudit, type Client, type ScriptRow, type AuditResult } from '../../api/resource'
import ScriptDialog from './ScriptDialog.vue'
const rows = ref<ScriptRow[]>([]), clients = ref<Client[]>([]), page = ref(1), total = ref(0), keyword = ref(''), clientId = ref<number>()
const loading = ref(false), editing = ref(false), selected = ref<ScriptRow | null>(null), auditing = ref<number | null>(null), result = ref<AuditResult | null>(null), resultOpen = ref(false)
async function load() {
  loading.value = true
  try { const data = await scripts.list<ScriptRow>({ page: page.value, page_size: 20, client_id: clientId.value, q: keyword.value || undefined }); rows.value = data.items; total.value = data.total } catch { /* API层显示错误。 */ } finally { loading.value = false }
}
function search() { page.value = 1; void load() }
function edit(row: ScriptRow | null) { selected.value = row; editing.value = true }
async function remove(row: ScriptRow) {
  try { await scripts.remove(row.id); ElMessage.success('话术已删除'); if (rows.value.length === 1 && page.value > 1) page.value--; await load() } catch { /* 保留列表供重试。 */ }
}
async function audit(row: ScriptRow) {
  auditing.value = row.id
  try { result.value = await runAudit(row); resultOpen.value = true; await load() } catch { /* 请求失败不伪造审查结果。 */ } finally { auditing.value = null }
}
onMounted(async () => { try { clients.value = await allClients(); await load() } catch { /* 机构接口失败时也不白屏。 */ } })
const label = (score: number) => ({ '-1':'判定未完成', '0':'违规', '1':'轻微风险', '2':'合规' })[String(score)] ?? '未知结果'
</script>
<template><div><p class="muted">CONTENT LIBRARY / 话术管理</p><h1>话术库</h1><p class="muted">统一管理营销原文，提交审查后查看风险与证据。</p>
<el-card shadow="never"><div class="toolbar"><el-input v-model="keyword" placeholder="按话术内容搜索" clearable style="width:260px" maxlength="500" @keyup.enter="search" @clear="search"/><el-select v-model="clientId" placeholder="全部机构" clearable filterable style="width:200px" @change="search"><el-option v-for="client in clients" :key="client.id" :label="client.name" :value="client.id"/></el-select><el-button @click="search">搜索</el-button><el-button type="primary" @click="edit(null)">新建话术</el-button></div>
<el-table v-loading="loading" :data="rows" empty-text="暂无话术，请先新建"><el-table-column prop="id" label="ID" width="70"/><el-table-column label="机构" min-width="130"><template #default="{ row }">{{ clients.find(c => c.id === row.client_id)?.name ?? `机构 #${row.client_id}` }}</template></el-table-column><el-table-column prop="scene" label="场景" width="100"/><el-table-column label="话术内容" min-width="240"><template #default="{ row }"><el-tooltip :content="row.content" :disabled="row.content.length <= 40"><span>{{ row.content.length > 40 ? row.content.slice(0,40) + '…' : row.content }}</span></el-tooltip></template></el-table-column><el-table-column label="状态" width="100"><template #default="{ row }"><el-tag>{{ row.status === 'pending' ? '待审查' : row.status === 'audited' ? '已审查' : '已归档' }}</el-tag></template></el-table-column><el-table-column prop="created_at" label="创建时间" min-width="170"/><el-table-column label="操作" width="250"><template #default="{ row }"><el-button link type="primary" @click="edit(row)">编辑</el-button><el-popconfirm title="确定删除这条话术？" confirm-button-text="删除" cancel-button-text="取消" @confirm="remove(row)"><template #reference><el-button link type="danger">删除</el-button></template></el-popconfirm><el-button link type="primary" :loading="auditing === row.id" :disabled="auditing !== null" @click="audit(row)">提交审查</el-button></template></el-table-column></el-table>
<el-pagination v-model:current-page="page" :page-size="20" :total="total" layout="total, prev, pager, next" style="margin-top:24px" @current-change="load"/></el-card>
<ScriptDialog v-model="editing" :clients="clients" :item="selected" @saved="load"/>
<el-dialog v-model="resultOpen" title="审查结果" width="760px"><template v-if="result"><el-alert :title="`${result.incomplete ? '判定未完成' : label(result.score)} · score=${result.score}`" :type="result.score === -1 || result.incomplete || result.score === 0 ? 'error' : result.score === 1 ? 'warning' : 'success'" :closable="false"/><p>命中条数：{{ result.hit_count }}</p><el-table :data="result.hits" empty-text="无有效命中"><el-table-column prop="axis" label="风险轴"/><el-table-column prop="law_article" label="法条依据"/><el-table-column prop="quote" label="原文引文"/></el-table><p class="muted">{{ result.disclaimer || '本系统输出为合规风险辅助提示，不构成法律意见' }}</p></template></el-dialog>
</div></template>
