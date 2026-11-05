<script setup lang="ts">
/**
 * 对外首页（公开，不需要登录）。
 *
 * 统筹方那条要求点得很准：**首页不该是登录页**。登录页只回答"你是谁"，
 * 而来看的人第一个问题是"这东西管谁的什么事、我能信到什么程度"。
 * 所以这里先讲清三件事：适用行业、判定的依据是什么、以及它明确不做什么。
 * 免责声明不是装饰，是这个产品能不能被正经对待的前提，所以放在首屏而不是塞在页脚。
 */
import { RouterLink } from 'vue-router'

const points = [
  { title: '先说依据', body: '每条命中都带法条原文与你的原话引文，引不出法条的判定直接作废。' },
  { title: '再说边界', body: '只管广告法域的表述合规：绝对化用语、功效与安全保证、前后对比、容貌焦虑等 11 条轴。' },
  { title: '最后说清不做', body: '不出法律意见，不替代《医疗广告审查证明》的行政前置审查，不判涉政涉黄内容。' }
]
</script>

<template>
  <div class="merchant-shell landing">
    <header class="bar">
      <span class="mark" aria-hidden="true">医</span>
      <strong>ComplianceGuard</strong>
      <RouterLink class="ghost" to="/login">登录</RouterLink>
    </header>

    <section class="hero">
      <p class="kicker">医美 · 口腔 机构适用</p>
      <h1>把要发的话术贴进来，<br>先看清哪里会被罚。</h1>
      <p class="lede">
        支持直接上传海报、PDF、Word、表格、PPT 与录音：系统解析出逐条话术，
        对照《广告法》《医疗美容广告执法指南》等依据给出命中条款、原文引文与风险等级。
      </p>
      <div class="cta">
        <RouterLink class="solid" to="/login">开始自查</RouterLink>
        <span class="m-muted">需要机构账号；未注册可在登录页注册。</span>
      </div>
    </section>

    <section class="points">
      <article v-for="point in points" :key="point.title">
        <h3>{{ point.title }}</h3>
        <p>{{ point.body }}</p>
      </article>
    </section>

    <footer class="foot">
      <p>
        本工具输出为合规风险辅助提示，<strong>不构成法律意见</strong>，
        也不能替代《医疗广告审查证明》的行政前置审查。判定未完成时会明确标为"未完成"，
        <strong>不会当成合规放行</strong>。
      </p>
    </footer>
  </div>
</template>

<style scoped>
.landing { display: flex; flex-direction: column; }
.bar {
  display: flex; align-items: center; gap: var(--cg-m-s-3);
  padding: var(--cg-m-s-4) var(--cg-m-s-8);
  border-bottom: 1px solid var(--cg-m-line); background: var(--cg-m-surface);
}
.bar strong { font-size: var(--cg-m-t-h4); }
.mark {
  width: 28px; height: 28px; border-radius: var(--cg-m-radius);
  border: 1px solid var(--cg-m-accent); color: var(--cg-m-accent);
  display: grid; place-items: center; font-size: var(--cg-m-t-aux); font-weight: 600;
}
.ghost {
  margin-left: auto; text-decoration: none; color: var(--cg-m-ink-2);
  border: 1px solid var(--cg-m-line); border-radius: var(--cg-m-radius);
  padding: var(--cg-m-s-1) var(--cg-m-s-3); font-size: var(--cg-m-t-aux);
  transition: border-color var(--cg-m-fast), color var(--cg-m-fast);
}
.ghost:hover { border-color: var(--cg-m-accent); color: var(--cg-m-ink); }

.hero { padding: var(--cg-m-s-8) var(--cg-m-s-8) var(--cg-m-s-6); max-width: 860px; }
.kicker {
  margin: 0 0 var(--cg-m-s-3); color: var(--cg-m-accent);
  font-size: var(--cg-m-t-aux); letter-spacing: .08em;
}
.hero h1 {
  margin: 0 0 var(--cg-m-s-4); font-size: var(--cg-m-t-display);
  line-height: 1.25; letter-spacing: -.01em; font-weight: 600;
}
.lede { margin: 0 0 var(--cg-m-s-5); font-size: var(--cg-m-t-body); color: var(--cg-m-ink-2); }
.cta { display: flex; align-items: center; gap: var(--cg-m-s-4); flex-wrap: wrap; }
.solid {
  text-decoration: none; background: var(--cg-m-accent); color: var(--cg-m-accent-ink);
  border-radius: var(--cg-m-radius); padding: var(--cg-m-s-2) var(--cg-m-s-5);
  font-size: var(--cg-m-t-body); transition: filter var(--cg-m-fast);
}
.solid:hover { filter: brightness(.94); }

.points {
  display: grid; gap: var(--cg-m-s-4); grid-template-columns: repeat(3, 1fr);
  padding: 0 var(--cg-m-s-8) var(--cg-m-s-8);
}
.points article {
  background: var(--cg-m-surface); border: 1px solid var(--cg-m-line);
  border-radius: var(--cg-m-radius-lg); padding: var(--cg-m-s-5);
  box-shadow: var(--cg-m-shadow);
}
.points h3 { margin-bottom: var(--cg-m-s-2); }
.points p { margin: 0; color: var(--cg-m-ink-2); font-size: var(--cg-m-t-aux); }

.foot {
  margin-top: auto; padding: var(--cg-m-s-5) var(--cg-m-s-8) var(--cg-m-s-8);
  border-top: 1px solid var(--cg-m-line); background: var(--cg-m-surface-2);
}
.foot p { margin: 0; font-size: var(--cg-m-t-micro); color: var(--cg-m-ink-2); max-width: 780px; }
.foot strong { color: var(--cg-m-ink); }

@media (max-width: 1100px) {
  .hero, .points, .foot, .bar { padding-left: var(--cg-m-s-5); padding-right: var(--cg-m-s-5); }
  .points { grid-template-columns: 1fr; }
}
</style>
