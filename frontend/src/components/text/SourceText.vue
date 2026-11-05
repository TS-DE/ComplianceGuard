<script setup lang="ts">
/**
 * 原文视图：整篇解析文本 + 命中标记 + 双向定位。
 *
 * 这块存在的理由就是一句用户抱怨：切分预览把内容按标点切碎后，
 * "我只能一条条对着找，不知道它在原文哪个位置"。
 * 所以左栏必须是**整篇原文**，而不是碎片列表；命中位置由调用方算好传进来
 * （见 utils/locate），组件自己不做任何"猜位置"的事。
 *
 * 定位不到也要说：`unlocated` 的条目在顶部单独列出，
 * 而不是静默地不高亮——静默会让人以为原文里确实没有，那是双重误导。
 */
import { computed, nextTick, ref, watch } from 'vue'
import type { Mark } from './marks'

const props = defineProps<{
  text: string
  marks: Mark[]
  /** 当前选中的命中 key，变了就滚过去并加深 */
  activeKey?: string | null
  /** 定位失败的条目文本，必须显式列出来 */
  unlocated?: string[]
  titleHint?: string | null
}>()

const emit = defineEmits<{ (event: 'pick', key: string): void }>()

const host = ref<HTMLElement | null>(null)

/** 把原文按标记切成片段，按位置排序；重叠的标记保留先出现的（同一段不套两层色）。 */
const segments = computed(() => {
  const ordered = [...props.marks].sort((a, b) => a.start - b.start)
  const out: { text: string; mark?: Mark }[] = []
  let cursor = 0
  for (const mark of ordered) {
    if (mark.start < cursor) continue
    if (mark.start > cursor) out.push({ text: props.text.slice(cursor, mark.start) })
    out.push({ text: props.text.slice(mark.start, mark.end), mark })
    cursor = mark.end
  }
  if (cursor < props.text.length) out.push({ text: props.text.slice(cursor) })
  return out
})

watch(() => props.activeKey, async key => {
  if (!key) return
  await nextTick()
  const node = host.value?.querySelector<HTMLElement>(`[data-key="${CSS.escape(key)}"]`)
  node?.scrollIntoView({ block: 'center', behavior: 'smooth' })
})
</script>

<template>
  <section class="pane">
    <header class="bar">
      <h3>原文</h3>
      <span class="cg-muted">{{ props.text.length.toLocaleString() }} 字</span>
    </header>

    <p v-if="props.titleHint" class="topic">
      <span class="cg-muted">主题线索（解析首行摘录，非模型提炼）</span>
      <strong>{{ props.titleHint }}</strong>
    </p>
    <p v-else class="cg-muted topic">主题识别未启用：解析结果里没有可作标题的首行</p>

    <p v-if="props.unlocated?.length" class="warn">
      以下命中在原文里定位失败，只列片段不给位置（给错位置比不给更坏）：
      <b>{{ props.unlocated.join('、') }}</b>
    </p>

    <div ref="host" class="scroll">
      <template v-for="(seg, index) in segments" :key="index">
        <mark v-if="seg.mark" :data-key="seg.mark.key" :class="[seg.mark.severity,
              { on: seg.mark.key === props.activeKey }]" @click="emit('pick', seg.mark.key)">
          {{ seg.text }}
        </mark>
        <span v-else>{{ seg.text }}</span>
      </template>
      <span v-if="!segments.length" class="cg-muted">（原文为空）</span>
    </div>
  </section>
</template>

<style scoped>
.pane { display: flex; flex-direction: column; min-height: 0; height: 100%;
  background: var(--cg-sheet); border: var(--cg-line); border-radius: var(--cg-radius); }
.bar { display: flex; align-items: baseline; gap: var(--cg-s-2); padding: var(--cg-s-2) var(--cg-s-3);
  border-bottom: var(--cg-line); }
.bar h3 { margin: 0; font-size: var(--cg-t-body); font-weight: 650; }
.topic { margin: var(--cg-s-3) var(--cg-s-3) 0; display: flex; flex-direction: column; gap: 2px; }
.topic strong { font-family: var(--cg-font-quote); font-size: 15px; font-weight: 600; }
.warn { margin: var(--cg-s-2) var(--cg-s-3) 0; padding: 6px 8px; font-size: var(--cg-t-aux);
  color: var(--cg-pending); background: var(--cg-pending-bg); border-radius: var(--cg-radius); }
.scroll {
  flex: 1; min-height: 0; overflow-y: auto; padding: var(--cg-s-3);
  font-family: var(--cg-font-quote); font-size: 15px; line-height: var(--cg-lh-quote);
  white-space: pre-wrap; word-break: break-word; color: var(--cg-ink);
}
mark { border: none; padding: 1px 2px; border-radius: 2px; cursor: pointer; transition: box-shadow .16s ease; }
mark.hard { background: var(--cg-hard-bg); box-shadow: inset 0 -2px 0 var(--cg-hard); }
mark.soft { background: var(--cg-soft-bg); box-shadow: inset 0 -2px 0 var(--cg-soft); }
mark.pending { background: var(--cg-pending-bg); box-shadow: inset 0 -2px 0 var(--cg-pending); }
/* 切分边界：只描边不上语义色，避免预览阶段看起来像"已经判过" */
mark.piece { background: transparent; box-shadow: inset 0 0 0 1px var(--cg-rule-strong); cursor: pointer; }
mark.piece.on { background: var(--cg-sheet); }
mark.on { outline: 2px solid var(--cg-accent); outline-offset: 1px; }
</style>
