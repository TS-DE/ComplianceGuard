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
import { auditFeedback, lawArticle, rewriteAudit } from '../../../api/resource'
import { isCanceled } from '../../../api/http'
// 类型声明在本文件第一个 script 块里，Vue 会把两块合成一个模块，不需要自己 import 自己
import type { HitRender, ResultRow, RewriteState } from './types'

const props = defineProps<{ rows: ResultRow[]; activeKey: string | null }>()
const emit = defineEmits<{ (event: 'locate', key: string | null): void }>()

const law = reactive<Record<string, string | null>>({})
const lawBusy = reactive<Record<string, boolean>>({})
const rewrites = reactive<Record<number, RewriteState>>({})
// 反馈按 audit 记录存（audits.feedback），所以控件挂在**整条结论**上而不是每个命中卡上：
// 挂在命中上会给出"我可以逐条推翻"的假暗示，而后端根本没有 per-hit 反馈这回事
const votes = reactive<Record<number, 'useful' | 'not_useful' | null>>({})
const voteBusy = reactive<Record<number, boolean>>({})

async function vote(row: ResultRow, pick: 'useful' | 'not_useful') {
  if (!row.auditId || voteBusy[row.scriptId]) return
  voteBusy[row.scriptId] = true
  try {
    const saved = await auditFeedback(row.auditId, pick)
    votes[row.scriptId] = saved.feedback as 'useful' | 'not_useful'
  } catch {
    votes[row.scriptId] = null      // 没存上就说没存上，不能显示"已记录"
  } finally {
    voteBusy[row.scriptId] = false
  }
}

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
  state.elapsed = 0
  // 改写是这条链路上最容易长时间不返回的一步（实测出现过十分钟级别），
  // 所以它必须能停、必须显示已经等了多久，并且停了以后还能再来一次。
  const controller = new AbortController()
  state.cancel = () => controller.abort()
  const timer = setInterval(() => { state.elapsed = (state.elapsed ?? 0) + 1 }, 1000)
  try {
    const result = await rewriteAudit(row.auditId, controller.signal) as {
      rewritten_text?: string; rewrite_passed?: boolean | null
      recheck?: { score?: number }
    }
    state.before = row.text
    state.after = result.rewritten_text ?? ''
    state.passed = result.rewrite_passed ?? null
    state.recheckScore = result.recheck?.score ?? null
    if (!result.rewritten_text) state.error = '模型没有给出改写稿，未做二次过审'
  } catch (error: unknown) {
    // 取消和失败要分开说：把"我自己点了停止"报成"改写失败"，
    // 用户会得到一个系统坏了的假结论
    if (isCanceled(error)) state.error = '已停止等待，可重新点击改写'
    else state.error = error instanceof Error ? error.message : '改写失败'
  } finally {
    clearInterval(timer)
    state.cancel = null
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
          <!-- 溯源写成纯文本：点它曾经是"定位原文"那个多余步骤，
               现在点任意命中就自动滚过去，不需要再让用户多做一次动作 -->
          <span class="ref" :title="row.ref ? '这句话在素材里的位置' : '没有素材来源，位置未知'">
            {{ row.ref || '位置未知' }}
          </span>
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

        <div class="vote">
          <span class="m-muted">这条判得怎么样？</span>
          <button :class="{ on: votes[row.scriptId] === 'useful' }"
                  :disabled="!row.auditId || voteBusy[row.scriptId]"
                  @click="vote(row, 'useful')">有用</button>
          <button :class="{ on: votes[row.scriptId] === 'not_useful' }"
                  :disabled="!row.auditId || voteBusy[row.scriptId]"
                  @click="vote(row, 'not_useful')">没用</button>
          <span class="muted-note">{{ votes[row.scriptId] ? '已记录，可改' : '不选也不影响判定' }}</span>
        </div>

        <div v-if="row.hits.length" class="actions">
          <button class="adopt" :disabled="!row.auditId || rewrites[row.scriptId]?.busy"
                  @click="adopt(row)">
            {{ rewrites[row.scriptId]?.busy
               ? `改写并二次过审中…已 ${rewrites[row.scriptId]?.elapsed ?? 0} 秒`
               : '采纳改写建议（含二次过审）' }}
          </button>
          <button v-if="rewrites[row.scriptId]?.busy" class="stop"
                  @click="rewrites[row.scriptId]?.cancel?.()">停止等待</button>
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
/* 纯文本，不是按钮：它曾经是"定位原文"那一步，点命中已经会自动滚过去 */
.ref { font-size: var(--cg-t-aux); color: var(--cg-ink-mute); }
.vote { display: flex; align-items: center; gap: var(--cg-s-2); margin-top: var(--cg-s-2); }
.vote button {
  /* --cg-line 是边框简写（1px solid 颜色），不能再套一层 `1px solid var(--cg-line)`：
     那会展开成 `1px solid 1px solid #…`，浏览器直接丢掉整条声明 */
  border: var(--cg-line); background: transparent; cursor: pointer;
  border-radius: var(--cg-radius); padding: 2px var(--cg-s-2); font-size: var(--cg-t-micro);
  color: var(--cg-ink-soft); transition: border-color var(--cg-m-fast), color var(--cg-m-fast);
}
.vote button:hover:not(:disabled) { border-color: var(--cg-accent); color: var(--cg-ink); }
.vote button.on { border-color: var(--cg-accent); color: var(--cg-accent); font-weight: 600; }
.vote button:disabled { opacity: .5; cursor: not-allowed; }
.muted-note { font-size: var(--cg-t-micro); color: var(--cg-ink-mute); }
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
/* 停止等待是次要动作：描边而不填色，避免和主按钮抢注意力 */
.stop { align-self: flex-start; border: 1px solid var(--cg-line); background: transparent;
        color: var(--cg-ink-2); padding: 6px 10px; font: inherit; cursor: pointer; }
.diff { margin-top: var(--cg-s-2); }
.empty { padding: var(--cg-s-5) 0; text-align: center; }
</style>
