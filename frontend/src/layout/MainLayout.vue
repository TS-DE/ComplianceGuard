<script setup lang="ts">
/**
 * 应用外壳：按角色渲染导航，并兜住 Element Plus 浮层残留问题。
 *
 * 这一版换了视觉语言（依据见 frontend/README.md 的设计说明），三个选择都是刻意的：
 * 1) 导航不用图标库。要图标得新增 @element-plus/icons-vue，而本轮只允许加 ECharts 与 diff；
 *    审查工具的导航靠文字就够辨认，于是改用标题首字作字标（monogram），
 *    比通用图标更贴"案卷"气质，也少一个依赖。
 * 2) 顶栏只显示页面标题，不再重复一句英文小标——原来那里和页面里的 h1 说的是同一件事。
 * 3) 层级靠 1px 边线与留白表达，卡片不带阴影；证据型界面里阴影只会分散注意力。
 *    侧栏也从深色块改成纸白＋边线：深色导航在任何后台都一样，而本产品的主语是文本证据。
 *
 * 保留两处老逻辑（它们是踩过坑才加上的，不能随换皮一起丢）：
 * · `go()` 显式跳转而不依赖 el-menu 的 router 模式：静默无反应最难查；
 * · router-view :key="route.path"：切页必重建，避免上一个页面的弹窗状态残留。
 */
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuth } from '../stores/auth'

interface MenuItem { path: string; title: string; hint?: string }

const auth = useAuth()
const router = useRouter()
const route = useRoute()

// 这个壳现在**只服务运营/平台端**：商家端换成 MerchantShell（顶部横向栏 + 两个功能区）。
// 商家菜单在这里整块删掉，而不是"按角色隐藏几项"——同一个侧栏两套条目，
// 迟早出现改了一边忘了另一边；而且"待复核"本来就不是商家的活。
const PLATFORM_MENUS: MenuItem[] = [
  { path: '/dashboard', title: '工作台' },
  { path: '/scripts', title: '话术库' },
  { path: '/audits', title: '审查记录' },
  { path: '/reviews', title: '待复核', hint: '人工' },
  { path: '/rules', title: '规则库' },
  { path: '/redteam', title: '红队压测', hint: '体检' },
  { path: '/clients', title: '机构管理' },
  { path: '/sources', title: '素材档案', hint: '原文件' }
]

const menus = computed(() => PLATFORM_MENUS)
const roleText = computed(() => '平台管理端')
const initial = computed(() => (auth.user?.username ?? '·').slice(0, 1).toUpperCase())

/** 字标：先剥掉"我的/机构/素材"这类前缀再取首字，否则四个菜单都长成"我"。 */
function glyph(item: MenuItem): string {
  const stripped = item.title.replace(/^(我的|机构|素材|待|红队|规则|话术|审查|文案)/, '')
  return (stripped || item.title).slice(0, 1)
}

function go(index: string) {
  if (index === route.path) return
  void router.push(index).catch(() => {
    window.alert('页面跳转失败，请刷新后重试')
  })
}

function toAuth() {
  void router.push('/login')
}

function logout() {
  auth.logout()
  void router.replace('/login')
}
function onUserCommand(command: string) {
  if (command === 'logout') logout()
}
</script>

<template>
  <div class="shell">
    <aside>
      <router-link class="brand" to="/">
        <span class="mark">CG</span><span class="word">ComplianceGuard</span>
      </router-link>
      <p class="caption">营销话术 · 合规审查</p>
      <el-menu :default-active="route.path" class="nav" @select="go">
        <el-menu-item v-for="item in menus" :key="item.path" :index="item.path">
          <span class="glyph">{{ glyph(item) }}</span>
          <span class="label">{{ item.title }}</span>
          <small v-if="item.hint">{{ item.hint }}</small>
        </el-menu-item>
      </el-menu>
      <div class="aside-foot">
        <p class="cg-disclaimer">本系统输出为合规风险辅助提示，不构成法律意见</p>
      </div>
    </aside>

    <section>
      <header>
        <h1>{{ route.meta.title || roleText }}</h1>
        <div class="user">
          <template v-if="auth.user">
            <el-dropdown trigger="click" @command="onUserCommand">
              <span class="who">
                <span class="avatar">{{ initial }}</span>
                <span class="name">{{ auth.user.username }}</span>
                <span class="role">{{ roleText }}</span>
              </span>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="logout">退出登录</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
          <el-button v-else type="primary" plain @click="toAuth">登录 / 注册</el-button>
        </div>
      </header>
      <main><router-view :key="route.path" /></main>
    </section>
  </div>
</template>

<style scoped>
.shell { display: flex; min-height: 100vh; background: var(--cg-paper); }

aside {
  width: 232px; flex: none; background: var(--cg-sheet); border-right: var(--cg-line);
  padding: var(--cg-s-4) 0 var(--cg-s-3); display: flex; flex-direction: column;
}
.brand { display: flex; align-items: baseline; gap: 8px; padding: 0 var(--cg-s-3); text-decoration: none; }
.mark { font-size: 20px; font-weight: 750; color: var(--cg-accent); }
.word { font-size: 13px; font-weight: 600; color: var(--cg-ink); }
.caption { margin: 4px 0 var(--cg-s-4); padding: 0 var(--cg-s-3); font-size: 11px; color: var(--cg-ink-mute); }

.nav { border: none; background: transparent; }
.nav :deep(.el-menu-item) {
  height: 40px; line-height: 40px; margin: 2px var(--cg-s-2); padding: 0 10px !important;
  border-radius: var(--cg-radius); color: var(--cg-ink-soft);
}
.nav :deep(.el-menu-item.is-active) {
  background: var(--cg-accent-soft); color: var(--cg-accent-ink); font-weight: 650;
  box-shadow: inset 2px 0 0 var(--cg-accent);
}
.nav :deep(.el-menu-item:hover) { background: var(--cg-margin); }
.glyph {
  width: 20px; height: 20px; margin-right: 10px; flex: none; font-size: 11px;
  border: 1px solid var(--cg-rule-strong); border-radius: var(--cg-radius);
  display: inline-flex; align-items: center; justify-content: center;
  color: var(--cg-ink-soft); background: var(--cg-paper);
}
.nav :deep(.is-active) .glyph { border-color: var(--cg-accent); background: var(--cg-sheet); color: var(--cg-accent-ink); }
.label { font-size: 13px; }
.nav small { margin-left: auto; font-size: 10px; color: var(--cg-ink-mute); }
.aside-foot { margin-top: auto; padding: var(--cg-s-3) var(--cg-s-3) 0; border-top: var(--cg-line); }

section { flex: 1; min-width: 0; display: flex; flex-direction: column; }
header {
  height: 60px; flex: none; background: var(--cg-sheet); border-bottom: var(--cg-line);
  display: flex; align-items: center; justify-content: space-between; padding: 0 var(--cg-s-5);
}
h1 { margin: 0; font-size: var(--cg-t-h1); font-weight: 650; }
.user { display: flex; align-items: center; gap: var(--cg-s-2); }
.who { display: flex; align-items: center; gap: 8px; }
.avatar {
  width: 26px; height: 26px; border-radius: 50%; background: var(--cg-accent); color: #fff;
  font-size: 12px; font-weight: 700; display: inline-flex; align-items: center; justify-content: center;
}
.name { font-size: 13px; font-weight: 600; color: var(--cg-ink); }
.role { font-size: 11px; color: var(--cg-ink-mute); }
main { padding: var(--cg-s-5); flex: 1; overflow-x: auto; }

@media (max-width: 1100px) {
  aside { width: 184px; }
  main { padding: var(--cg-s-3); }
  .word { display: none; }
}
</style>
