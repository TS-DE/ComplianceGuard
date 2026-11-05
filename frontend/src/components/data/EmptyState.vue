<script setup lang="ts">
/**
 * 空态：说明"这里为什么是空的"并给下一步动作。
 *
 * 空屏不是错误状态，是引导时机——本项目里最常见的空态是"还没有上传素材"，
 * 只写"暂无数据"等于把用户留在原地。所以 action 是可点的，不是装饰。
 */
const props = defineProps<{
  title: string
  hint?: string
  actionText?: string
}>()

const emit = defineEmits<{ (event: 'action'): void }>()
</script>

<template>
  <div class="empty">
    <p class="title">{{ props.title }}</p>
    <p v-if="props.hint" class="hint">{{ props.hint }}</p>
    <button v-if="props.actionText" class="cta" @click="emit('action')">{{ props.actionText }}</button>
  </div>
</template>

<style scoped>
.empty { padding: var(--cg-s-6) var(--cg-s-3); text-align: center; }
.title { margin: 0; font-size: var(--cg-t-h2); color: var(--cg-ink); font-weight: 600; }
.hint { margin: var(--cg-s-2) 0 var(--cg-s-3); font-size: var(--cg-t-aux); color: var(--cg-ink-mute); line-height: 1.7; }
.cta {
  border: 1px solid var(--cg-accent); background: var(--cg-accent); color: #fff;
  padding: 6px 14px; border-radius: var(--cg-radius); cursor: pointer; font-size: var(--cg-t-body);
}
.cta:hover { background: var(--cg-accent-ink); }
</style>
