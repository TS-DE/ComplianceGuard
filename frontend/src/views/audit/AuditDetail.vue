<script setup lang="ts">
/**
 * 审查记录详情抽屉：把一次审查的「分数为什么是这个分数」摊开给人看。
 *
 * 三个不可省略的点：
 * 1) incomplete 必须红色单列——判定未完成绝不能被读成「合规」。
 * 2) 每条命中都要能追到条文（复用 ArticleDrawer），否则「可解释」只到条号为止。
 * 3) 成本为 null 时显示「未计价」，不能显示 0 元（0 元等于宣称免费）。
 */
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { rewriteAudit, type AuditRow, type Hit } from '../../api/resource'
import ArticleDrawer from '../law/ArticleDrawer.vue'

const props = defineProps<{ modelValue: boolean; row: AuditRow | null }>()
const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'rewritten'): void
}>()

const rewriting = ref(false)
const articleOpen = ref(false)
const articleCode = ref<string | null>(null)
const articleItemNo = ref<string | null>(null)

const label = (score: number) =>
  ({ '-1': '判定未完成', '0': '违规', '1': '轻微风险', '2': '合规' } as Record<string, string>)[String(score)] ?? '未知'
const hits = (row: AuditRow | null): Hit[] => row?.hits_json ?? []

function openArticle(hit: Hit) {
  articleCode.value = hit.law_article
  articleItemNo.value = hit.item_no ?? null
  articleOpen.value = true
}

async function doRewrite() {
  if (!props.row) return
  rewriting.value = true
  try {
    const result = await rewriteAudit(props.row.id)
    if (result.rewrite_passed) ElMessage.success('改写稿已通过二次审查')
    else ElMessage.warning('改写稿未通过二次审查，已保留原文供人工复核')
    emit('rewritten')
  } catch {
    // 失败不改写、不伪造结果。
  } finally {
    rewriting.value = false
  }
}
</script>

<template>
  <el-drawer :model-value="modelValue" size="680px" title="审查详情"
             @update:model-value="emit('update:modelValue', $event)">
    <template v-if="row">
      <el-alert
        :title="`${row.incomplete ? '判定未完成（不计入合规）' : label(row.score)} · score=${row.score}`"
        :type="row.incomplete || row.score === -1 || row.score === 0 ? 'error' : row.score === 1 ? 'warning' : 'success'"
        :closable="false" show-icon
      />

      <el-descriptions :column="2" border size="small" style="margin-top: 14px">
        <el-descriptions-item label="记录 ID">{{ row.id }}</el-descriptions-item>
        <el-descriptions-item label="话术 ID">{{ row.script_id }}</el-descriptions-item>
        <el-descriptions-item label="命中条数">{{ row.hit_count }}</el-descriptions-item>
        <el-descriptions-item label="模型">{{ row.model ?? '—' }}</el-descriptions-item>
        <el-descriptions-item label="耗时">{{ row.latency_ms }} ms</el-descriptions-item>
        <el-descriptions-item label="成本">
          <span v-if="row.cost === null" class="unpriced">未计价（缺单价）</span>
          <span v-else>{{ row.cost }} 元</span>
        </el-descriptions-item>
        <el-descriptions-item label="Token">
          {{ row.prompt_tokens }} / {{ row.completion_tokens }}
        </el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ row.created_at }}</el-descriptions-item>
      </el-descriptions>

      <h4>命中明细（{{ hits(row).length }}）</h4>
      <el-table :data="hits(row)" empty-text="无有效命中" size="small">
        <el-table-column prop="axis" label="风险轴" width="150" />
        <el-table-column label="法条依据" width="210">
          <template #default="{ row: hit }">
            <el-link type="primary" :underline="false" @click="openArticle(hit)">
              {{ hit.law_article }}
              <span v-if="hit.item_no" class="item-hint">{{ hit.item_no.slice(hit.item_no.indexOf('条') + 1) }}</span>
            </el-link>
          </template>
        </el-table-column>
        <el-table-column prop="quote" label="原文引文" min-width="220" />
      </el-table>

      <template v-if="row.rewritten_text">
        <h4>改写稿
          <el-tag v-if="row.rewrite_passed" type="success" size="small">二次审查通过</el-tag>
          <el-tag v-else type="danger" size="small">二次审查未通过</el-tag>
        </h4>
        <pre class="rewritten">{{ row.rewritten_text }}</pre>
      </template>

      <div class="actions">
        <el-button type="primary" :loading="rewriting" @click="doRewrite">生成合规改写稿</el-button>
        <span class="muted">改写后会重新走一遍完整审查，未通过不会标记为合规。</span>
      </div>
    </template>
    <el-empty v-else description="未选择记录" />

    <ArticleDrawer v-model="articleOpen" :code="articleCode" :item-no="articleItemNo" />
  </el-drawer>
</template>

<style scoped>
h4 { margin: 18px 0 10px; font-size: 14px; font-weight: 600; display: flex; align-items: center; gap: 8px; }
.item-hint { margin-left: 2px; color: var(--el-color-warning-dark-2); }
.unpriced { color: var(--el-color-warning-dark-2); }
.muted { color: var(--el-text-color-secondary); font-size: 12px; }
.rewritten { margin: 0; white-space: pre-wrap; word-break: break-word; font-family: inherit; font-size: 13px;
  line-height: 1.8; background: var(--el-fill-color-light); padding: 12px; border-radius: 6px; }
.actions { margin-top: 20px; display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
</style>
