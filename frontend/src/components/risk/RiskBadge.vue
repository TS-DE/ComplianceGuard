<script setup lang="ts">
/**
 * 风险态标签：系统里唯一表达"这条结论是什么性质"的视觉件。
 *
 * 为什么只认 state 而不认 score 数字（LSP）：
 * 页面若各自写 `score === 0 ? '违规' : ...`，就会有人漏掉 -1，
 * 把"判定未完成"染成绿色——本项目最贵的一类错。
 * 颜色一律走 token 变量，组件里不写色值，改配色只改 tokens.css。
 */
import { computed } from 'vue'
import { RISK_META, riskState, type RiskState } from '../../utils/risk'

const props = defineProps<{
  /** 直接给态（列表已算好时用） */
  state?: RiskState
  /** 或者给判定原始值，组件自己换算，保证口径只有一份 */
  score?: number
  incomplete?: boolean | null
  error?: string | null
  /** 追加命中标注，如"已二次过审通过" */
  note?: string
  plain?: boolean
}>()

const meta = computed(() => props.state
  ? RISK_META[props.state]
  : riskState({ score: props.score ?? -1, incomplete: props.incomplete, error: props.error }))
</script>

<template>
  <span class="badge" :class="{ plain: props.plain }"
        :style="{ color: meta.color, background: props.plain ? 'transparent' : meta.bg,
                  borderColor: meta.color }">
    <i class="dot" :style="{ background: meta.color }" />{{ meta.label }}
    <em v-if="props.note" class="note">{{ props.note }}</em>
  </span>
</template>

<style scoped>
.badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 1px 9px 1px 7px;
  border: 1px solid;
  border-radius: var(--cg-radius-pill);
  font-size: var(--cg-t-aux);
  line-height: 1.7;
  font-weight: 600;
  white-space: nowrap;
}
.badge.plain { border-color: transparent; }
.dot { width: 6px; height: 6px; border-radius: 50%; flex: none; }
.note { font-style: normal; font-weight: 400; opacity: .75; margin-left: 4px; }
</style>
