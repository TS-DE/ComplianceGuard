<script setup lang="ts">
/**
 * 检查结果表：一批话术审完后的结论区。
 *
 * 单独成组件是因为宿主页面（文案检查）已经装了"喂素材 + 切分 + 勾选"这套状态，
 * 再把结果表塞进去会撑到一个没人敢改的文件；违规明细的展开逻辑也在这里闭环。
 */
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { axisLabel, type BatchAuditItem, type Hit } from '../../api/resource'

const props = defineProps<{ items: BatchAuditItem[] }>()

const router = useRouter()
const expanded = ref<number | null>(null)

/** 未完成与失败都必须显式露出来：把它们混进"合规"是这套系统最不能犯的错。 */
const verdict = (item: BatchAuditItem) =>
  item.error ? '失败'
    : item.incomplete || item.score === -1 ? '判定未完成'
      : ({ '0': '违规', '1': '疑似违规', '2': '合规' } as Record<string, string>)[String(item.score)] ?? '未知'
const tagType = (item: BatchAuditItem) =>
  item.error || item.incomplete || item.score === -1 || item.score === 0 ? 'danger'
    : item.score === 1 ? 'warning' : 'success'
const label = (axis: string) => axisLabel(axis)
const hitList = (item: BatchAuditItem): Hit[] => item.hits ?? []
</script>

<template>
  <el-card shadow="never" class="card">
    <h3>检查结果</h3>
    <el-table :data="props.items" size="small" empty-text="无结果">
      <el-table-column label="话术" min-width="220">
        <template #default="{ row }">
          <span class="ellipsis" :title="String(row.script_id)">#{{ row.script_id }}</span>
        </template>
      </el-table-column>
      <el-table-column label="结论" width="130">
        <template #default="{ row }"><el-tag :type="tagType(row)" effect="light">{{ verdict(row) }}</el-tag></template>
      </el-table-column>
      <el-table-column label="命中" width="80">
        <template #default="{ row }">{{ row.error ? '—' : row.hit_count }}</template>
      </el-table-column>
      <el-table-column label="耗时" width="100">
        <template #default="{ row }">{{ row.error ? '—' : `${row.latency_ms} ms` }}</template>
      </el-table-column>
      <el-table-column label="说明" min-width="240">
        <template #default="{ row }">
          <span v-if="row.error" class="err">{{ row.error }}</span>
          <el-button v-else-if="row.hit_count" link type="primary"
                     @click="expanded = expanded === row.script_id ? null : row.script_id">
            {{ expanded === row.script_id ? '收起' : '查看违规明细' }}
          </el-button>
          <span v-else class="muted">未发现违规</span>
        </template>
      </el-table-column>
    </el-table>

    <div v-for="row in props.items" :key="`d-${row.script_id}`">
      <div v-if="expanded === row.script_id" class="detail">
        <div v-for="(hit, i) in hitList(row)" :key="i" class="hit">
          <p class="hit-head">
            <el-tag size="small" :type="hit.downgraded ? 'warning' : 'danger'" effect="light">
              {{ label(hit.axis) }}
            </el-tag>
            <el-tag v-if="hit.downgraded" size="small" type="warning" effect="plain">已降级</el-tag>
            <span class="law">{{ hit.law_article }}<span v-if="hit.item_no" class="law"> {{ hit.item_no }}</span></span>
          </p>
          <p class="quote">原文：{{ hit.quote }}</p>
          <p v-if="hit.reason" class="reason">理由：{{ hit.reason }}</p>
          <p v-if="hit.downgrade_reason" class="downgrade">分级：{{ hit.downgrade_reason }}</p>
        </div>
      </div>
    </div>

    <p class="muted note">本系统输出为合规风险辅助提示，不构成法律意见，也不能替代《医疗广告审查证明》的行政前置审查。</p>

    <el-button style="margin-top: 4px" @click="router.push('/merchant/audits')">到审查历史查看完整记录</el-button>
    <el-button style="margin-top: 4px" @click="router.push('/merchant/sources')">看这批素材的原始档案</el-button>
  </el-card>
</template>

<style scoped>
.muted { color: var(--el-text-color-secondary); font-size: 13px; }
h3 { margin: 0 0 8px; font-size: 15px; }
.card { margin-top: 16px; }
.note { margin: 12px 0 0; }
.ellipsis { display: inline-block; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; vertical-align: bottom; }
.err { color: var(--el-color-danger); font-size: 12px; }
.detail { margin-top: 8px; border: 1px solid var(--el-border-color-lighter); border-radius: 6px; padding: 12px; }
.hit { padding: 8px 0; border-bottom: 1px dashed var(--el-border-color-lighter); }
.hit:last-child { border-bottom: none; }
.hit-head { margin: 0 0 6px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.downgrade { margin: 4px 0 0; font-size: 12px; line-height: 1.6; color: var(--el-color-warning-dark-2); }
.law { font-size: 12px; color: var(--el-text-color-secondary); }
.quote { margin: 0 0 4px; font-size: 13px; line-height: 1.6; }
.reason { margin: 0; font-size: 12px; line-height: 1.6; color: var(--el-text-color-regular); }
</style>
