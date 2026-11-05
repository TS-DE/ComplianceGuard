<script setup lang="ts">
/**
 * 判定环：把一条审查结论画成一个可扫读的环。
 *
 * 刻意**不做成百分比环**：后端 score 的取值域是 -1/0/1/2（db_schema.md 的 CHECK 约束），
  * 把它渲染成"73 分"就是凭空造一个不存在的量表，属于编造数字。
 * 环的填充比例只表达"已判定的四档里有几档被踩到"这一件事：
 *   2 合规 → 满环青；1 轻微 → 三分之二赭黄；0 违规 → 三分之一朱红；-1 → 虚线灰环。
 * 中间写真实分值，旁边写人话，两个都在，免得只剩颜色让人猜。
 */
import { computed } from 'vue'
import { riskState } from '../../utils/risk'

const props = defineProps<{
  score: number
  incomplete?: boolean | null
  error?: string | null
  hitCount?: number
  size?: number
}>()

const meta = computed(() => riskState({ score: props.score, incomplete: props.incomplete, error: props.error }))
const side = computed(() => props.size ?? 96)
const radius = computed(() => (side.value - 10) / 2)
const circumference = computed(() => 2 * Math.PI * radius.value)
/** 已判定才有弧；未完成画整圈虚线（不能画成"0 弧"，那是"没问题"的暗示） */
const filled = computed(() => {
  if (props.error || props.incomplete || props.score === -1) return 1
  // 索引 (2 - score)：合规=满环，轻微=2/3，违规=1/3（越少越严重，环越空）
  return [1, 2 / 3, 1 / 3][Math.max(0, Math.min(2, 2 - props.score))] ?? 1
})
const dash = computed(() => `${circumference.value * filled.value} ${circumference.value}`)
</script>

<template>
  <div class="ring" :style="{ width: `${side}px`, height: `${side}px` }">
    <svg :width="side" :height="side" role="img" :aria-label="`${meta.label}，score=${props.score}`">
      <circle :cx="side / 2" :cy="side / 2" :r="radius" class="track"
              :stroke-dasharray="props.error || props.incomplete || props.score === -1 ? '3 4' : undefined" />
      <circle :cx="side / 2" :cy="side / 2" :r="radius" class="value"
              :style="{ stroke: meta.color }" :stroke-dasharray="dash"
              :transform="`rotate(-90 ${side / 2} ${side / 2})`" />
    </svg>
    <div class="core">
      <strong :style="{ color: meta.color }">{{ meta.label }}</strong>
      <span class="sub">{{ props.hitCount ?? 0 }} 处命中</span>
      <span class="raw">score={{ props.score }}</span>
    </div>
  </div>
</template>

<style scoped>
.ring { position: relative; display: inline-flex; align-items: center; justify-content: center; }
.track { fill: none; stroke: var(--cg-rule); stroke-width: 6; }
.value { fill: none; stroke-width: 6; stroke-linecap: butt; }
.core {
  position: absolute; inset: 0; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 1px; text-align: center;
}
.core strong { font-size: var(--cg-t-body); font-weight: 650; }
.sub { font-size: var(--cg-t-aux); color: var(--cg-ink-soft); }
.raw { font-size: 10px; color: var(--cg-ink-mute); font-family: var(--cg-font-num); }
</style>
