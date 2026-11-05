<script setup lang="ts">
/**
 * 右栏：每条话术的判定结果 + 四件事齐全的命中卡 + 一键采纳改写。
 *
 * 为什么坚持"每条都带原文上下文和法条原文"：
 * 只显示 `#93` 和一个小切片，商家除了"信"没有别的选择，而这个产品卖的就是可核对。
 * 法条正文按需拉取（/law/article 只读本地归档，不花钱、不慢），不提前全量拉，
 * 一次检查 20 条会打出几十次无用的查询。
 */
import { reactive } from 'vue'
import HitCard from '../../../components/risk/HitCard.vue'
import RiskBadge from '../../../components/risk/RiskBadge.vue'
import DiffView from '../../../components/data/DiffView.vue'
import { lawArticle, rewriteAudit } from '../../../api/resource'
// 类型声明在本文件第一个 script 块里，Vue 会把两块合成一个模块，不需要自己 import 自己
import type { HitRender, ResultRow, RewriteState } from './types'

const props = defineProps<{ rows: ResultRow[]; activeKey: string | null }>()
const emit = defineEmits<{ (event: 'locate', key: string | null): void }>()

const law = reactive<Record<string, string | null>>({})
const lawBusy = reactive<Record<string, boolean>>({})
const rewrites = reactive<Record<number, RewriteState>>({})

async function loadLaw(hit: HitRender) {
  const key = `${hit.view.lawArticle}|${hit.view.itemNo ?? ''}`
  if (law[key] !== undefined || lawBusy[key]) return
  lawBusy[key] = true
  try {
    const found = await lawArticle(hit.view.lawArticle, hit.view.itemNo)
    // 有项就给该项正文，没有才给整条：只给整条会让商家自己去长文里找那句
    law[key] = found.item_text || found.article_text
  } catch {
    law[key] = null          // 取不到就只显示条号，绝不编造法条正文
  } finally {
    delete lawBusy[key]
  }
}

async function adopt(row: ResultRow) {
  if (!row.auditId) return
  const state = rewrites[row.scriptId] ?? (rewrites[row.scriptId] = {})
  if (state.busy) return
  state.busy = true
  state.error = null
  try {
    const result = await rewriteAudit(row.auditId) as {
      rewritten_text?: string; rewrite_passed?: boolean | null
      recheck?: { score?: number }
    }
    state.before = row.text
    state.after = result.rewritten_text ?? ''
    state.passed = result.rewrite_passed ?? null
    state.recheckScore = result.recheck?.score ?? null
    if (!result.rewritten_text) state.error = '模型没有给出改写稿，未做二次过审'
  } catch (error: unknown) {
    state.error = error instanceof Error ? error.message : '改写失败'
  } finally {
    state.busy = false
  }
}
</script>

<template>
  <div class="pane">
    <header class="bar">
      <h3>判定结果</h3>
      <span class="cg-muted">{{ props.rows.length }} 条 · 点条目可在原文里定位</span>
    </header>

    <div class="scroll">
      <article v-for="row in props.rows" :key="row.scriptId" class="row"
               :class="{ on: props.activeKey?.startsWith(`${row.scriptId}-`) }">
        <header class="head">
          <RiskBadge :score="row.score" :incomplete="row.incomplete" :error="row.error" />
          <button class="jump" @click="emit('locate', `${row.scriptId}-0`)">
            {{ row.ref || '位置未知' }}
          </button>
          <span class="src">{{ row.sourceLabel }}</span>
          <span v-if="row.latencyMs" class="ms">{{ row.latencyMs }} ms</span>
        </header>

        <p class="text">{{ row.text }}</p>
        <p v-if="row.error" class="err">{{ row.error }}</p>

        <HitCard v-for="hit in row.hits" :key="hit.key" :hit="hit.view"
                 :context-before="hit.context?.before" :context-after="hit.context?.after"
                 :law-text="law[`${hit.view.lawArticle}|${hit.view.itemNo ?? ''}`]"
                 :law-loading="lawBusy[`${hit.view.lawArticle}|${hit.view.itemNo ?? ''}`]"
                 :active="props.activeKey === hit.key"
                 @locate="emit('locate', hit.key)" @load-law="loadLaw(hit)" />

        <p v-if="row.unlocated.length" class="warn">
          {{ row.unlocated.length }} 处命中在原文里定位失败，未高亮：{{ row.unlocated.join('、') }}
        </p>

        <div v-if="row.hits.length" class="actions">
          <button class="adopt" :disabled="!row.auditId || rewrites[row.scriptId]?.busy"
                  @click="adopt(row)">
            {{ rewrites[row.scriptId]?.busy ? '改写并二次过审中…' : '采纳改写建议（含二次过审）' }}
          </button>
          <span class="cg-muted">改写稿是内部使用建议，不改变事实主张的强度</span>
        </div>

        <DiffView v-if="rewrites[row.scriptId]?.after" class="diff"
                  :before="rewrites[row.scriptId]!.before || row.text"
                  :after="rewrites[row.scriptId]!.after!"
                  :passed="rewrites[row.scriptId]!.passed"
                  :recheck-score="rewrites[row.scriptId]!.recheckScore" />
        <p v-else-if="rewrites[row.scriptId]?.error" class="err">{{ rewrites[row.scriptId]!.error }}</p>
      </article>

      <p v-if="!props.rows.length" class="cg-muted empty">还没有结果。</p>
    </div>
  </div>
</template>

<style scoped>
.pane { display: flex; flex-direction: column; min-height: 0; height: 100%;
  background: var(--cg-sheet); border: var(--cg-line); border-radius: var(--cg-radius); }
.bar { display: flex; align-items: baseline; gap: var(--cg-s-2); padding: var(--cg-s-2) var(--cg-s-3);
  border-bottom: var(--cg-line); }
.bar h3 { margin: 0; font-size: var(--cg-t-body); font-weight: 650; }
.scroll { flex: 1; min-height: 0; overflow-y: auto; padding: var(--cg-s-3);
  display: flex; flex-direction: column; gap: var(--cg-s-3); }
.row { display: flex; flex-direction: column; gap: var(--cg-s-2);
  padding-bottom: var(--cg-s-3); border-bottom: var(--cg-line); }
.row:last-child { border-bottom: none; }
.head { display: flex; align-items: center; gap: var(--cg-s-2); flex-wrap: wrap; }
.jump { border: none; background: none; padding: 0; cursor: pointer; font-size: var(--cg-t-aux);
  color: var(--cg-accent); border-bottom: 1px dashed var(--cg-accent); }
.src { font-size: 11px; color: var(--cg-ink-mute); }
.ms { margin-left: auto; font-size: 11px; color: var(--cg-ink-mute); font-family: var(--cg-font-num); }
.text { margin: 0; font-size: var(--cg-t-aux); color: var(--cg-ink-soft); }
.err { margin: 0; font-size: var(--cg-t-aux); color: var(--cg-hard); }
.warn { margin: 0; font-size: 11px; color: var(--cg-pending); background: var(--cg-pending-bg);
  padding: 6px 8px; border-radius: var(--cg-radius); }
.actions { display: flex; flex-direction: column; gap: 4px; }
.adopt { align-self: flex-start; border: 1px solid var(--cg-accent); background: var(--cg-accent);
  color: #fff; padding: 5px 12px; border-radius: var(--cg-radius); cursor: pointer; font-size: var(--cg-t-aux); }
.adopt:disabled { opacity: .55; cursor: progress; }
.diff { margin-top: var(--cg-s-2); }
.empty { padding: var(--cg-s-5) 0; text-align: center; }
</style>
