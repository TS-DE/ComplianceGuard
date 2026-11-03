<script setup lang="ts">
/**
 * 法条追溯抽屉：点击命中条文后「直达该法规并定位到对应条文」。
 *
 * 只读法规归档（后端不查向量库、不调模型），所以用户可以随手点开核对，
 * 不会产生费用。上半区固定展示命中条原文，下半区给出该法规全部条文并
 * 自动滚动高亮，保证「有上下文、能定位」，而不是甩一根孤立条文。
 */
import { nextTick, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { lawArticle, type LawArticle } from '../../api/resource'

const props = defineProps<{ modelValue: boolean; code: string | null }>()
const emit = defineEmits<{ (e: 'update:modelValue', value: boolean): void }>()

const data = ref<LawArticle | null>(null)
const loading = ref(false)
const listRef = ref<HTMLElement | null>(null)

async function load(code: string) {
  loading.value = true
  data.value = null
  try {
    data.value = await lawArticle(code)
    // 等列表渲染出来再滚动，否则拿不到目标节点。
    await nextTick()
    const target = listRef.value?.querySelector<HTMLElement>('[data-active="true"]')
    target?.scrollIntoView({ block: 'center' })
  } catch (error) {
    // 接口层已弹错；这里保留空态，不能伪造条文内容。
    ElMessage.warning(error instanceof Error ? error.message : '条文加载失败')
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.modelValue, props.code] as const,
  ([open, code]) => {
    if (open && code && (!data.value || data.value.code !== code)) void load(code)
    if (!open) data.value = null
  },
  { immediate: true }
)
</script>

<template>
  <el-drawer
    :model-value="modelValue"
    :title="data ? `${data.doc} · 第 ${data.article_no} 条` : '法条原文'"
    size="620px"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div v-loading="loading" class="body">
      <template v-if="data">
        <p class="tag-line">
          <el-tag size="small" type="primary">{{ data.doc }}</el-tag>
          <span class="muted">来源归档：{{ data.source }}</span>
        </p>

        <section class="article-current">
          <h4>命中条文原文</h4>
          <pre>{{ data.text }}</pre>
        </section>

        <section class="article-list">
          <h4>《{{ data.doc }}》全部条文（{{ data.articles.length }} 条）</h4>
          <div ref="listRef" class="scroller">
            <article
              v-for="row in data.articles"
              :key="row.code"
              :data-active="row.code === data.code"
              :class="['item', { active: row.code === data.code }]"
            >
              <p class="no">{{ row.code }}</p>
              <pre>{{ row.text }}</pre>
            </article>
          </div>
        </section>
      </template>
      <el-empty v-else-if="!loading" description="未能加载该条文" />
    </div>
  </el-drawer>
</template>

<style scoped>
.body { display: flex; flex-direction: column; gap: 16px; height: 100%; }
.tag-line { display: flex; align-items: center; gap: 10px; margin: 0; }
.muted { color: var(--el-text-color-secondary); font-size: 12px; }
h4 { margin: 0 0 8px; font-size: 14px; font-weight: 600; }
.article-current { border: 1px solid var(--el-color-primary-light-7); background: var(--el-color-primary-light-9); border-radius: 6px; padding: 12px; }
pre { margin: 0; white-space: pre-wrap; word-break: break-word; font-family: inherit; font-size: 13px; line-height: 1.7; }
.article-list { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.scroller { flex: 1; overflow-y: auto; border: 1px solid var(--el-border-color-lighter); border-radius: 6px; padding: 8px; }
.item { padding: 10px 12px; border-radius: 4px; border-left: 3px solid transparent; }
.item + .item { margin-top: 4px; }
.item .no { margin: 0 0 4px; font-size: 12px; color: var(--el-text-color-secondary); }
.item.active { background: var(--el-color-warning-light-9); border-left-color: var(--el-color-warning); }
.item.active .no { color: var(--el-color-warning-dark-2); font-weight: 600; }
</style>
