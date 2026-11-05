<script setup lang="ts">
/**
 * 流程进度条：商家端"喂素材 → 核对切分 → 入库 → 看结论"是一条真顺序，
 * 所以这里用序号是合适的（不是装饰性的 01/02/03）。
 *
 * 每一步可点：主操作按钮不该被埋在页面底部，长文档滚到底才能点是原来的主要抱怨。
 */
const props = defineProps<{
  steps: { key: string; label: string }[]
  current: string
  done?: string[]
}>()

const emit = defineEmits<{ (event: 'go', key: string): void }>()
</script>

<template>
  <ol class="steps">
    <li v-for="(step, index) in props.steps" :key="step.key"
        :class="{ on: step.key === props.current, done: props.done?.includes(step.key) }">
      <button @click="emit('go', step.key)">
        <span class="idx">{{ index + 1 }}</span>{{ step.label }}
      </button>
    </li>
  </ol>
</template>

<style scoped>
.steps {
  display: flex; gap: 0; margin: 0; padding: 0; list-style: none;
  border: var(--cg-line); border-radius: var(--cg-radius); background: var(--cg-sheet);
  overflow: hidden;
}
.steps li { flex: 1; border-right: var(--cg-line); }
.steps li:last-child { border-right: none; }
button {
  width: 100%; display: flex; align-items: center; gap: 8px;
  padding: 10px var(--cg-s-3); border: none; background: none; cursor: pointer;
  font-size: var(--cg-t-aux); color: var(--cg-ink-soft); text-align: left;
}
.idx {
  width: 18px; height: 18px; flex: none; border-radius: 50%;
  border: 1px solid var(--cg-rule-strong); color: var(--cg-ink-mute);
  display: inline-flex; align-items: center; justify-content: center; font-size: 11px;
}
.on { background: var(--cg-accent-soft); }
.on button { color: var(--cg-accent-ink); font-weight: 650; }
.on .idx { border-color: var(--cg-accent); background: var(--cg-accent); color: #fff; }
.done .idx { border-color: var(--cg-ok); background: var(--cg-ok-bg); color: var(--cg-ok); }
@media (max-width: 1100px) {
  .steps { flex-direction: column; }
  .steps li { border-right: none; border-bottom: var(--cg-line); }
}
</style>
