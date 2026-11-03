<script setup lang="ts">
/**
 * 机构管理：话术的归属主数据，删机构会被后端 409 拦（名下还有话术时）。
 *
 * 这里保留后端原样错误提示，而不是前端先算一遍——冲突判断属于业务规则，
 * 前端复刻一份迟早会与后端漂移。
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { clients, type ClientRow } from '../../api/resource'

const rows = ref<ClientRow[]>([])
const page = ref(1)
const total = ref(0)
const loading = ref(false)
const dialogOpen = ref(false)
const saving = ref(false)
const editing = ref<ClientRow | null>(null)
const form = reactive({ name: '', industry: 'medical_beauty', contact: '', plan: 'free' })

async function load() {
  loading.value = true
  try {
    const data = await clients.list<ClientRow>({ page: page.value, page_size: 20 })
    rows.value = data.items
    total.value = data.total
  } catch {
    // API 层已提示。
  } finally {
    loading.value = false
  }
}

function open(row: ClientRow | null) {
  editing.value = row
  form.name = row?.name ?? ''
  form.industry = row?.industry ?? 'medical_beauty'
  form.contact = row?.contact ?? ''
  form.plan = row?.plan ?? 'free'
  dialogOpen.value = true
}

async function save() {
  if (!form.name.trim()) { ElMessage.warning('机构名称必填'); return }
  saving.value = true
  try {
    const payload = { name: form.name.trim(), industry: form.industry, contact: form.contact || null, plan: form.plan }
    if (editing.value) await clients.update<ClientRow>(editing.value.id, payload)
    else await clients.create<ClientRow>(payload)
    ElMessage.success(editing.value ? '机构已更新' : '机构已创建')
    dialogOpen.value = false
    await load()
  } catch {
    // 冲突时后端返回 409 与具体原因，由 API 层弹出。
  } finally {
    saving.value = false
  }
}

async function remove(row: ClientRow) {
  try {
    await clients.remove(row.id)
    ElMessage.success('机构已删除')
    if (rows.value.length === 1 && page.value > 1) page.value--
    await load()
  } catch {
    // 名下有话术时后端返回 409，界面保持原状。
  }
}

onMounted(load)
</script>

<template>
  <div>
    <p class="muted">TENANTS / 机构管理</p>
    <h1>机构管理</h1>
    <p class="muted">话术按机构归属；机构下仍有话术时不允许删除。</p>

    <el-card shadow="never">
      <div class="toolbar">
        <el-button type="primary" @click="open(null)">新建机构</el-button>
      </div>

      <el-table v-loading="loading" :data="rows" empty-text="暂无机构">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="name" label="机构名称" min-width="200" />
        <el-table-column prop="industry" label="行业" width="150" />
        <el-table-column prop="contact" label="联系方式" min-width="160">
          <template #default="{ row }">{{ row.contact || '—' }}</template>
        </el-table-column>
        <el-table-column prop="plan" label="套餐" width="100" />
        <el-table-column prop="created_at" label="创建时间" min-width="170" />
        <el-table-column label="操作" width="150">
          <template #default="{ row }">
            <el-button link type="primary" @click="open(row)">编辑</el-button>
            <el-popconfirm title="确定删除该机构？" confirm-button-text="删除" cancel-button-text="取消"
                           @confirm="remove(row)">
              <template #reference><el-button link type="danger">删除</el-button></template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination v-model:current-page="page" :page-size="20" :total="total"
                     layout="total, prev, pager, next" style="margin-top: 24px" @current-change="load" />
    </el-card>

    <el-dialog v-model="dialogOpen" :title="editing ? '编辑机构' : '新建机构'" width="480px">
      <el-form label-width="90px">
        <el-form-item label="机构名称" required>
          <el-input v-model="form.name" maxlength="80" placeholder="如：某某医疗美容门诊部" />
        </el-form-item>
        <el-form-item label="行业">
          <el-input v-model="form.industry" maxlength="40" />
        </el-form-item>
        <el-form-item label="联系方式">
          <el-input v-model="form.contact" maxlength="120" />
        </el-form-item>
        <el-form-item label="套餐">
          <el-select v-model="form.plan" style="width: 100%">
            <el-option label="免费版" value="free" />
            <el-option label="专业版" value="pro" />
            <el-option label="企业版" value="enterprise" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogOpen = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.toolbar { display: flex; gap: 12px; margin-bottom: 16px; }
.muted { color: var(--el-text-color-secondary); font-size: 13px; }
</style>
