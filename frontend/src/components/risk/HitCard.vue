<script setup lang="ts">
/**
 * 命中卡：一条违规证据的完整交代——片段、法条原文、理由、等级。
 *
 * 为什么坚持四件事一起给（这是产品的立身之处）：
 * 商家收到"这条不合规"只会回一句"凭什么"。只有把**他原话里的那几个字**和
 * **法条原文**并排放着，结论才可核对；引不出法条的命中后端已经作废（铁律 4），
 * 所以这里出现的一定是带条号的证据，不留"只有 ID 和一个分数"的空卡。
 *
 * props 只给一条拍平后的 HitView（ISP），不把整个 audit row 塞进来：
 * 钻 `row.hits_json[0].evidence[1]` 这类链式访问在页面里出现一次，
 * 后端结构一变就要改三个页面。
 */
import RiskBadge from './RiskBadge.vue'
import type { HitView } from '../../utils/risk'

const props = defineProps<{
  hit: HitView
  /** 该命中是否被选中（右侧列表与原文高亮联动时用） */
  active?: boolean
  /** 原文上下文：命中前后各若干字，由调用方从原文切片传入 */
  contextBefore?: string
  contextAfter?: string
  /** 法条原文（来自 /law/article），没有就只显示条号，不编造正文 */
  lawText?: string | null
  lawLoading?: boolean
}>()

const emit = defineEmits<{
  (event: 'locate', hit: HitView): void
  (event: 'load-law', hit: HitView): void
}>()
</script>

<template>
  <article class="card" :class="{ active: props.active }">
    <header>
      <RiskBadge :state="props.hit.severity === 'hard' ? 'hard' : 'soft'"
                 :note="props.hit.downgraded ? '已降级' : undefined" />
      <span class="axis">{{ props.hit.axisLabel }}</span>
      <button class="link" @click="emit('locate', props.hit)">定位原文</button>
    </header>

    <p class="law">
      <button class="lawbtn" @click="emit('load-law', props.hit)">
        {{ props.hit.lawArticle }}<span v-if="props.hit.itemNo" class="item">{{ props.hit.itemNo }}</span>
      </button>
      <span v-if="props.hit.detector" class="det">{{ props.hit.detector }}</span>
    </p>

    <p v-if="props.lawLoading" class="cg-muted">正在取法条原文…</p>
    <blockquote v-else-if="props.lawText" class="quote law-text">{{ props.lawText }}</blockquote>

    <p class="quote-block">
      <span v-if="props.contextBefore" class="ctx">{{ props.contextBefore }}</span>
      <mark :class="props.hit.severity === 'hard' ? 'mark-hard' : 'mark-soft'">{{ props.hit.quote }}</mark>
      <span v-if="props.contextAfter" class="ctx">{{ props.contextAfter }}</span>
    </p>

    <p v-if="props.hit.reason" class="reason">{{ props.hit.reason }}</p>
    <p v-if="props.hit.downgradeReason" class="downgrade">
      降级说明：{{ props.hit.downgradeReason }}
    </p>
  </article>
</template>

<style scoped>
.card {
  background: var(--cg-sheet);
  border: var(--cg-line);
  border-radius: var(--cg-radius);
  padding: var(--cg-s-3);
  transition: border-color .16s ease, background .16s ease;
}
.card.active { border-color: var(--cg-accent); background: var(--cg-accent-soft); }
header { display: flex; align-items: center; gap: var(--cg-s-2); }
.axis { font-weight: 650; font-size: var(--cg-t-body); }
.link {
  margin-left: auto; border: none; background: none; cursor: pointer;
  color: var(--cg-accent); font-size: var(--cg-t-aux); padding: 0;
}
.law { margin: var(--cg-s-2) 0 0; display: flex; align-items: baseline; gap: var(--cg-s-2); }
.lawbtn {
  border: none; background: none; padding: 0; cursor: pointer; text-align: left;
  color: var(--cg-ink); font-weight: 600; font-size: var(--cg-t-aux);
  border-bottom: 1px solid var(--cg-rule-strong);
}
.item { color: var(--cg-soft); margin-left: 4px; }
.det { font-size: 11px; color: var(--cg-ink-mute); font-family: var(--cg-font-num); }
/* 引文与法条原文用衬线：视觉上就把"证据"和"界面"分开，这是本产品的核心区分 */
.quote {
  margin: var(--cg-s-2) 0 0; padding: var(--cg-s-2) var(--cg-s-3);
  border-left: 3px solid var(--cg-rule-strong);
  font-family: var(--cg-font-quote); font-size: var(--cg-t-body); line-height: var(--cg-lh-quote);
  background: var(--cg-margin); color: var(--cg-ink);
}
.quote-block { margin: var(--cg-s-3) 0 0; font-family: var(--cg-font-quote); line-height: var(--cg-lh-quote); }
.ctx { color: var(--cg-ink-mute); }
mark { padding: 1px 2px; border-radius: 2px; color: var(--cg-ink); }
.mark-hard { background: var(--cg-hard-bg); box-shadow: inset 0 -2px 0 var(--cg-hard); }
.mark-soft { background: var(--cg-soft-bg); box-shadow: inset 0 -2px 0 var(--cg-soft); }
.reason { margin: var(--cg-s-2) 0 0; font-size: var(--cg-t-aux); color: var(--cg-ink-soft); line-height: 1.7; }
.downgrade {
  margin: var(--cg-s-2) 0 0; font-size: var(--cg-t-aux); color: var(--cg-soft);
  background: var(--cg-soft-bg); padding: 6px 8px; border-radius: var(--cg-radius);
}
</style>
