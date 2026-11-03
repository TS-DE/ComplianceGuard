<script setup lang="ts">
/**
 * 规则库：把「判定标准」当成数据展示出来，而不是藏在一堆 if-else 里。
 *
 * 这是本项目区别于「调个大模型接口」的地方，因此每一列都要可读：
 * 轴 / 法条 / 严重度 / 检测手段 / 版本 / 启用。
 * 其中「检测手段」决定这条轴是词库正则扫出来的，还是模型语义判出来的——
 * 用户必须能看见，否则没法解释「为什么这句查得出、那句查不出」。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { rules, type RuleRow } from '../../api/resource'

const rows = ref<RuleRow[]>([])
const page = ref(1)
const total = ref(0)
const loading = ref(false)
const toggling = ref<number | null>(null)
const detail = ref<RuleRow | null>(null)
const detailOpen = ref(false)

async function load() {
  loading.value = true
  try {
    const data = await rules.list<RuleRow>({ page: page.value, page_size: 50 })
    rows.value = data.items
    total.value = data.total
  } catch {
    // API 层已提示。
  } finally {
    loading.value = false
  }
}

async function toggle(row: RuleRow) {
  toggling.value = row.id
  try {
    await rules.update<RuleRow>(row.id, { enabled: !row.enabled })
    ElMessage.success(row.enabled ? '规则已停用' : '规则已启用')
    await load()
  } catch {
    // 失败时不改变本地状态，避免界面与库不一致。
  } finally {
    toggling.value = null
  }
}

function open(row: RuleRow) {
  detail.value = row
  detailOpen.value = true
}

const detectorText = (value: string | null) =>
  ({ keyword: '词库匹配', regex: '正则规则', semantic: '向量相似', llm_judge: '模型语义判定' } as Record<string, string>)[value ?? ''] ?? (value ?? '—')
const detectorTag = (value: string | null) => (value === 'llm_judge' ? 'warning' : 'success')
const exported = computed(() => rows.value.filter(row => row.exemptions?.length).length)

onMounted(load)
</script>

<template>
  <div>
    <p class="muted">RULE REGISTRY / 规则库</p>
    <h1>规则库</h1>
    <p class="muted">
      共 {{ total }} 条规则，其中 {{ exported }} 条带法定豁免清单。规则是数据不是代码：改规则走版本号递增，旧版本停用不删除。
    </p>

    <el-card shadow="never">
      <el-table v-loading="loading" :data="rows" empty-text="规则库为空">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="axis" label="规则轴" width="180" />
        <el-table-column prop="law_article" label="法条依据" min-width="230" show-overflow-tooltip />
        <el-table-column label="严重度" width="100">
          <template #default="{ row }">
            <el-tag :type="row.level === 'hard' ? 'danger' : 'info'" effect="plain" size="small">
              {{ row.level === 'hard' ? '一票否决' : '累计扣分' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="检测手段" width="130">
          <template #default="{ row }">
            <el-tag :type="detectorTag(row.detector)" effect="plain" size="small">{{ detectorText(row.detector) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="豁免" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.exemptions?.length" type="warning" size="small">{{ row.exemptions.length }} 项</el-tag>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="版本" width="80">
          <template #default="{ row }">v{{ row.version }}</template>
        </el-table-column>
        <el-table-column label="启用" width="90">
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'primary' : 'info'" :effect="row.enabled ? 'light' : 'plain'" size="small">
              {{ row.enabled ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160">
          <template #default="{ row }">
            <el-button link type="primary" @click="open(row)">详情</el-button>
            <el-button link :type="row.enabled ? 'danger' : 'success'"
                       :loading="toggling === row.id" @click="toggle(row)">
              {{ row.enabled ? '停用' : '启用' }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination v-model:current-page="page" :page-size="50" :total="total"
                     layout="total, prev, pager, next" style="margin-top: 24px" @current-change="load" />
    </el-card>

    <el-drawer v-model="detailOpen" title="规则详情" size="620px">
      <template v-if="detail">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="规则轴">{{ detail.axis }}</el-descriptions-item>
          <el-descriptions-item label="法条依据">{{ detail.law_article }}</el-descriptions-item>
          <el-descriptions-item label="严重度">{{ detail.level === 'hard' ? '一票否决' : '累计扣分' }}</el-descriptions-item>
          <el-descriptions-item label="检测手段">{{ detectorText(detail.detector) }}</el-descriptions-item>
          <el-descriptions-item label="版本">v{{ detail.version }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ detail.enabled ? '启用' : '停用' }}</el-descriptions-item>
        </el-descriptions>

        <h4>违规模式（判据）</h4>
        <pre class="block">{{ detail.pattern }}</pre>

        <template v-if="detail.example_bad">
          <h4>反例</h4>
          <pre class="block">{{ detail.example_bad }}</pre>
        </template>

        <template v-if="detail.exemptions?.length">
          <h4>法定豁免（{{ detail.exemptions.length }} 项）</h4>
          <el-table :data="detail.exemptions" size="small">
            <el-table-column prop="text" label="不适用情形" min-width="300" />
            <el-table-column prop="source" label="出处" width="220" />
          </el-table>
        </template>
      </template>
    </el-drawer>
  </div>
</template>

<style scoped>
.muted { color: var(--el-text-color-secondary); font-size: 13px; }
h4 { margin: 18px 0 8px; font-size: 14px; font-weight: 600; }
.block { margin: 0; white-space: pre-wrap; word-break: break-word; font-family: inherit;
  font-size: 13px; line-height: 1.8; background: var(--el-fill-color-light); padding: 12px; border-radius: 6px; }
</style>
