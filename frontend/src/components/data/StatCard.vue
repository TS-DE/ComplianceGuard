<script setup lang="ts">
/**
 * 统计数字块：一个数字 + 它的口径说明。
 *
 * 强制要求 `caption`：只给"12"没有意义，必须说清这 12 是什么、时间窗、含不含未完成。
 * 本项目的数字全部来自 SQL 聚合（A5 铁律：模型不造数），展示层也不能把它糊成结论。
 */
const props = defineProps<{
  label: string
  value: string | number
  caption?: string
  tone?: 'neutral' | 'hard' | 'soft' | 'pending' | 'ok'
}>()

const toneVar: Record<string, string> = {
  neutral: 'var(--cg-ink)', hard: 'var(--cg-hard)', soft: 'var(--cg-soft)',
  pending: 'var(--cg-pending)', ok: 'var(--cg-ok)'
}
</script>

<template>
  <div class="stat">
    <p class="label">{{ props.label }}</p>
    <p class="value" :style="{ color: toneVar[props.tone ?? 'neutral'] }">{{ props.value }}</p>
    <p class="cap">{{ props.caption || ' ' }}</p>
  </div>
</template>

<style scoped>
.stat {
  background: var(--cg-sheet);
  border: var(--cg-line);
  border-radius: var(--cg-radius);
  padding: var(--cg-s-3);
  min-width: 0;
}
.label { margin: 0; font-size: var(--cg-t-aux); color: var(--cg-ink-mute); }
.value {
  margin: var(--cg-s-2) 0 0; font-size: var(--cg-t-display); line-height: 1;
  font-weight: 700; font-variant-numeric: tabular-nums;
}
.cap { margin: 6px 0 0; font-size: 11px; color: var(--cg-ink-mute); min-height: 15px; line-height: 1.5; }
</style>
