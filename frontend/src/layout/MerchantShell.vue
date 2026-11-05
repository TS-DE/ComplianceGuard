<script setup lang="ts">
/**
 * 商家端外壳（第二套 shell）。
 *
 * 三条硬要求都落在这里：
 * 1. **顶部横向栏**：品牌｜导航｜登录或头像（头像在右上角，不在左侧折叠区）；
 * 2. **没有左侧菜单**：商家只有两个功能区（文案审核 / 我的档案），
 *    把它们塞进侧栏折叠起来，等于让"我今天要办的事"变成要点两下才看见的东西；
 * 3. **没有"待复核"入口**：那是运营的活。这里连导航项都不出现——
 *    不是 disabled 给商家看，而是根本不给他看，避免"我提交的东西被别人审"的误解。
 *
 * 与 `MainLayout.vue`（运营端案纸风）是两套并存的 shell，不在一个组件里按角色换样式。
 */
import { computed } from 'vue'
import { RouterLink, RouterView } from 'vue-router'
import { useAuth } from '../stores/auth'

const auth = useAuth()
const zones = [
  { to: '/m/check', label: '文案审核', hint: '粘贴或上传素材，逐条看判定与改法' },
  { to: '/m/archive', label: '我的档案', hint: '递过的材料、查过的话术、结论的历史' }
]
const userLabel = computed(() => auth.user?.username ?? '')
// User 契约里只有 client_id，没有机构名：要显示名称得再拉一次 clients 接口。
// 这里不去偷偷猜一个名字，直接显示可核对的机构编号。
const clientLabel = computed(() =>
  auth.user?.client_id ? `机构 #${auth.user.client_id}` : '未绑定机构')
</script>

<template>
  <div class="merchant-shell">
    <header class="bar">
      <RouterLink class="brand" to="/m/check">
        <span class="mark" aria-hidden="true">医</span>
        <span class="brand-text">
          <strong>ComplianceGuard</strong>
          <em>医美 · 口腔 话术合规自查</em>
        </span>
      </RouterLink>

      <nav class="nav" aria-label="功能区">
        <RouterLink v-for="zone in zones" :key="zone.to" :to="zone.to"
                    class="nav-item" :title="zone.hint">
          {{ zone.label }}
        </RouterLink>
      </nav>

      <div class="side">
        <RouterLink v-if="!auth.user" to="/login" class="ghost">登录</RouterLink>
        <div v-else class="who">
          <span class="avatar" aria-hidden="true">{{ userLabel.slice(0, 1).toUpperCase() }}</span>
          <span class="who-text">
            <strong>{{ userLabel }}</strong>
            <em class="m-muted">{{ clientLabel }}</em>
          </span>
        </div>
      </div>
    </header>

    <!-- 免责声明在 shell 里挂一次：所有商家页面都看得到，不靠每个页面自己记得写 -->
    <p class="notice">
      本工具输出为合规风险辅助提示，<strong>不构成法律意见</strong>，
      也不能替代《医疗广告审查证明》的行政前置审查。
    </p>

    <main class="body">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.bar {
  display: flex; align-items: center; gap: var(--cg-m-s-6);
  padding: var(--cg-m-s-3) var(--cg-m-s-6);
  background: var(--cg-m-surface);
  border-bottom: 1px solid var(--cg-m-line);
  /* 顶栏粘住：商家在长原文里滚到第 8 屏时，仍要知道自己在哪个功能区 */
  position: sticky; top: 0; z-index: 10;
}
.brand { display: flex; align-items: center; gap: var(--cg-m-s-3); text-decoration: none; color: inherit; }
.mark {
  width: 30px; height: 30px; border-radius: var(--cg-m-radius);
  border: 1px solid var(--cg-m-accent); color: var(--cg-m-accent);
  display: grid; place-items: center; font-size: var(--cg-m-t-aux); font-weight: 600;
}
.brand-text { display: flex; flex-direction: column; line-height: 1.25; }
.brand-text strong { font-size: var(--cg-m-t-h4); letter-spacing: .01em; }
.brand-text em { font-style: normal; font-size: var(--cg-m-t-micro); color: var(--cg-m-ink-3); }

.nav { display: flex; gap: var(--cg-m-s-5); margin-left: auto; }
.nav-item {
  position: relative; padding: var(--cg-m-s-2) 0; text-decoration: none;
  color: var(--cg-m-ink-2); font-size: var(--cg-m-t-body);
  transition: color var(--cg-m-fast);
}
.nav-item:hover { color: var(--cg-m-ink); }
/* 当前区用一条金色细线标出，而不是整块底色：导航是骨架，不该抢内容的注意力 */
.nav-item.router-link-active { color: var(--cg-m-ink); font-weight: 600; }
.nav-item.router-link-active::after {
  content: ''; position: absolute; left: 0; right: 0; bottom: -2px;
  height: 2px; background: var(--cg-m-accent); border-radius: var(--cg-m-radius-sm);
}

.side { display: flex; align-items: center; gap: var(--cg-m-s-3); }
.ghost {
  text-decoration: none; color: var(--cg-m-ink-2);
  border: 1px solid var(--cg-m-line); border-radius: var(--cg-m-radius);
  padding: var(--cg-m-s-1) var(--cg-m-s-3); font-size: var(--cg-m-t-aux);
  transition: border-color var(--cg-m-fast), color var(--cg-m-fast);
}
.ghost:hover { border-color: var(--cg-m-accent); color: var(--cg-m-ink); }
.who { display: flex; align-items: center; gap: var(--cg-m-s-2); }
.avatar {
  width: 28px; height: 28px; border-radius: 50%;
  background: var(--cg-m-surface-2); border: 1px solid var(--cg-m-line);
  color: var(--cg-m-accent); display: grid; place-items: center;
  font-size: var(--cg-m-t-aux); font-weight: 600;
}
.who-text { display: flex; flex-direction: column; line-height: 1.2; }
.who-text strong { font-size: var(--cg-m-t-aux); }
.who-text em { font-style: normal; font-size: var(--cg-m-t-micro); }

.notice {
  margin: 0; padding: var(--cg-m-s-2) var(--cg-m-s-6);
  background: var(--cg-m-surface-2); color: var(--cg-m-ink-2);
  font-size: var(--cg-m-t-micro); border-bottom: 1px solid var(--cg-m-line);
}
.notice strong { color: var(--cg-m-ink); }
.body { padding: var(--cg-m-s-6); max-width: 1280px; margin: 0 auto; width: 100%; }

/* 1280 是统筹方给的硬底线：窄到这一步顶栏必须换行而不是横向溢出 */
@media (max-width: 1100px) {
  .bar { flex-wrap: wrap; gap: var(--cg-m-s-3) var(--cg-m-s-5); }
  .nav { margin-left: 0; order: 3; width: 100%; }
  .side { margin-left: auto; }
  .body { padding: var(--cg-m-s-4); }
}
</style>
