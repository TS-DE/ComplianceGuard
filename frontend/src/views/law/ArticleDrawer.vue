<script setup lang="ts">
/**
 * 法条追溯抽屉：精确到「条下的某一项」，而不是甩出整条或整部法规。
 *
 * 设计取舍（依据实际使用反馈）：
 * 1) 用户点的是「第五条(五)」，就把第（五）项单独呈现并标明位置；
 *    给整条第 5 条的九项、或整部 10 条，都是噪声。
 * 2) 整条全文保留为**默认折叠**的次要入口——需要看上下文时能展开，不打断主信息。
 * 3) 只读本地法规归档（后端不查向量库、不调模型），随手点开不产生费用。
 */
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { lawArticle, type LawArticle } from '../../api/resource'

const props = defineProps<{ modelValue: boolean; code: string | null; itemNo?: string | null }>()
const emit = defineEmits<{ (e: 'update:modelValue', value: boolean): void }>()

const data = ref<LawArticle | null>(null)
const loading = ref(false)
const showFull = ref(false)

async function load(code: string, itemNo?: string | null) {
  loading.value = true
  data.value = null
  showFull.value = false
  try {
    data.value = await lawArticle(code, itemNo)
  } catch (error) {
    // 接口层已弹错，这里保持空态，绝不伪造条文内容。
    ElMessage.warning(error instanceof Error ? error.message : '条文加载失败')
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.modelValue, props.code, props.itemNo] as const,
  ([open, code, itemNo]) => {
    if (open && code && (!data.value || data.value.code !== code || data.value.item_no !== (itemNo ?? null))) {
      void load(code, itemNo)
    }
    if (!open) data.value = null
  },
  { immediate: true }
)

/** 「第五条(五)」-> 「第（五）项」；无项号时退化为整条。 */
const itemLabel = (value: string | null): string => {
  if (!value) return ''
  const matched = value.match(/[（(]([一二三四五六七八九十]+)[）)]/)
  return matched ? `第（${matched[1]}）项` : ''
}
</script>

<template>
  <el-drawer :model-value="modelValue" size="560px" @update:model-value="emit('update:modelValue', $event)">
    <template #header>
      <div class="head">
        <span class="title">{{ data ? `《${data.doc}》第 ${data.article_no} 条` : '法条原文' }}</span>
        <el-tag v-if="data?.item_no" size="small" type="warning">{{ itemLabel(data.item_no) }}</el-tag>
      </div>
    </template>

    <div v-loading="loading" class="body">
      <template v-if="data">
        <p class="muted">来源归档：{{ data.source }}</p>

        <section class="focus">
          <h4>{{ data.item_text ? '命中项原文' : '命中条文原文' }}</h4>
          <pre>{{ data.item_text || data.article_text }}</pre>
        </section>

        <el-collapse v-if="data.item_text" v-model="showFull" class="full">
          <el-collapse-item :name="true">
            <template #title>展开该条全文（上下文）</template>
            <pre class="muted-text">{{ data.article_text }}</pre>
          </el-collapse-item>
        </el-collapse>
      </template>
      <el-empty v-else-if="!loading" description="未能加载该条文" />
    </div>
  </el-drawer>
</template>

<style scoped>
.head { display: flex; align-items: center; gap: 10px; }
.title { font-size: 15px; font-weight: 600; }
.body { display: flex; flex-direction: column; gap: 14px; }
.muted { color: var(--el-text-color-secondary); font-size: 12px; margin: 0; }
h4 { margin: 0 0 8px; font-size: 14px; font-weight: 600; }
.focus {
  border: 1px solid var(--el-color-warning-light-5);
  background: var(--el-color-warning-light-9);
  border-radius: 6px;
  padding: 14px;
}
pre { margin: 0; white-space: pre-wrap; word-break: break-word; font-family: inherit; font-size: 14px; line-height: 1.8; }
.full :deep(.el-collapse-item__header) { font-size: 13px; color: var(--el-text-color-regular); }
.muted-text { font-size: 13px; color: var(--el-text-color-regular); }
</style>
