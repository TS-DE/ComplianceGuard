<script setup lang="ts">
/**
 * 改写前后对比：原文 vs 改写稿，词级差异。
 *
 * 为什么用 jsdiff 而不是自己写 LCS：差异算法容易写错且错得安静
 * （少标一个词没人会发现），这类轮子不该自己造。
 * 用 `diffWordsWithSpace` 而不是按字符切：中文按字切会把"保证"和"保证做完"
 * 拆成一堆单字噪声，词级差异才读得出"改了哪一句"。
 *
 * 法律边界：这里输出的是**内部使用建议**，不是合规结论——
 * 组件把这句话常驻在角标上，避免商家把改写稿当成"已通过审查"。
 */
import { computed } from 'vue'
// jsdiff v8+ 自带类型声明；这里只用到 words 级差异
import { diffWordsWithSpace } from 'diff'
import RiskBadge from '../risk/RiskBadge.vue'

const props = defineProps<{
  before: string
  after: string
  /** 二次过审结果：true 通过 / false 未通过 / null 未复核 */
  passed?: boolean | null
  recheckScore?: number | null
}>()

type Segment = { text: string; kind: 'same' | 'added' | 'removed' }

const segments = computed<Segment[]>(() => diffWordsWithSpace(props.before, props.after)
  .map(part => ({
    text: part.value,
    kind: part.added ? 'added' : (part.removed ? 'removed' : 'same')
  })))

const verdict = computed<'ok' | 'hard' | null>(() =>
  (props.passed === null || props.passed === undefined) ? null : (props.passed ? 'ok' : 'hard'))
</script>

<template>
  <section class="diff">
    <header>
      <h4>改写建议 · 内部使用</h4>
      <RiskBadge v-if="verdict" :state="verdict"
                 :note="props.passed ? '已二次过审通过' : '二次过审仍未通过'" />
      <span v-else class="pending">未二次过审，不能当作已通过</span>
    </header>

    <p class="body">
      <template v-for="(seg, index) in segments" :key="index">
        <del v-if="seg.kind === 'removed'">{{ seg.text }}</del>
        <ins v-else-if="seg.kind === 'added'">{{ seg.text }}</ins>
        <span v-else>{{ seg.text }}</span>
      </template>
    </p>

    <footer>
      <span>改写稿不改变事实主张的强度——去掉的是断言，不是卖点。</span>
      <span v-if="props.recheckScore !== null && props.recheckScore !== undefined" class="score">
        复核 score={{ props.recheckScore }}
      </span>
    </footer>
  </section>
</template>

<style scoped>
.diff { background: var(--cg-sheet); border: var(--cg-line); border-radius: var(--cg-radius); padding: var(--cg-s-3); }
header { display: flex; align-items: center; gap: var(--cg-s-3); }
h4 { margin: 0; font-size: var(--cg-t-body); font-weight: 650; }
.pending { font-size: var(--cg-t-aux); color: var(--cg-pending); background: var(--cg-pending-bg); padding: 2px 8px; border-radius: var(--cg-radius); }
.body {
  margin: var(--cg-s-3) 0 0; font-family: var(--cg-font-quote);
  line-height: var(--cg-lh-quote); font-size: 15px; color: var(--cg-ink);
}
ins, del { text-decoration: none; border-radius: 2px; padding: 1px 2px; }
ins { background: var(--cg-ok-bg); color: var(--cg-ok); box-shadow: inset 0 -2px 0 var(--cg-ok); }
del { background: var(--cg-hard-bg); color: var(--cg-hard); text-decoration: line-through; }
footer {
  margin-top: var(--cg-s-3); padding-top: var(--cg-s-2); border-top: var(--cg-line);
  display: flex; justify-content: space-between; font-size: 11px; color: var(--cg-ink-mute);
}
.score { font-family: var(--cg-font-num); }
</style>
