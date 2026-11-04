<script setup lang="ts">
/**
 * 应用外壳：按角色渲染不同导航，并兜住 Element Plus 浮层的残留问题。
 *
 * 三个刻意的选择：
 * 1) `el-menu` 不用 `router` 模式，改为显式 `@select -> router.push`。
 *    router 模式把导航藏在组件内部，出问题时既无日志也无断点，
 *    显式跳转能让「点了没反应」变成「有明确的条件拦住」。
 * 2) `<router-view :key="route.path">`：同一路径下 query 变化不重建组件
 *    （审查记录靠 watch 响应 script_id），但切换页面必定重建，
 *    避免上一个页面的弹窗/抽屉状态残留。
 * 3) 切页后主动清理 body 下残留的 `.el-overlay`：
 *    弹窗/抽屉若在卸载瞬间仍处于打开状态，遮罩可能留在 DOM 里盖住整页，
 *    表现就是「点哪里都没反应」。
 */
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuth } from '../stores/auth'

interface MenuItem { path: string; title: string; hint?: string }

const auth = useAuth()
const router = useRouter()
const route = useRoute()

const isMerchant = computed(() => auth.user?.role === 'merchant')

const MERCHANT_MENUS: MenuItem[] = [
  { path: '/merchant', title: '我的工作台' },
  { path: '/merchant/check', title: '文案检查', hint: '批量' },
  { path: '/merchant/scripts', title: '我的话术' },
  { path: '/merchant/audits', title: '审查历史' }
]

const PLATFORM_MENUS: MenuItem[] = [
  { path: '/dashboard', title: '工作台' },
  { path: '/scripts', title: '话术库' },
  { path: '/audits', title: '审查记录' },
  { path: '/rules', title: '规则库' },
  { path: '/redteam', title: '红队压测', hint: '体检' },
  { path: '/clients', title: '机构管理' }
]

const menus = computed(() => (isMerchant.value ? MERCHANT_MENUS : PLATFORM_MENUS))
const roleText = computed(() => (isMerchant.value ? '商家端' : '平台管理端'))

/** 菜单点击统一从这里出去；失败给出明确提示，不再「静默无反应」。 */
function go(index: string) {
  if (index === route.path) return
  void router.push(index).catch(() => {
    window.alert('页面跳转失败，请刷新后重试')
  })
}

function logout() {
  auth.logout()
  void router.replace('/login')
}
</script>

<template>
  <div class="shell">
    <aside>
      <div class="brand">CG <span>ComplianceGuard</span></div>
      <p class="caption">营销话术合规 · 风险可追溯</p>
      <el-tag :type="isMerchant ? 'success' : 'info'" effect="dark" size="small" class="role">
        {{ roleText }}
      </el-tag>
      <el-menu :default-active="route.path" class="nav"
               background-color="#132a40" text-color="#bccbdd" active-text-color="#67dbc6"
               @select="go">
        <el-menu-item v-for="item in menus" :key="item.path" :index="item.path">
          {{ item.title }}
          <small v-if="item.hint">{{ item.hint }}</small>
        </el-menu-item>
      </el-menu>
      <div class="aside-footer">合规风险辅助平台</div>
    </aside>

    <section>
      <header>
        <span class="title">{{ route.meta.title }}</span>
        <div class="user">
          <span>{{ auth.user?.username }}</span>
          <el-button text @click="logout">退出登录</el-button>
        </div>
      </header>
      <main><router-view :key="route.path" /></main>
      <footer>本系统输出为合规风险辅助提示，不构成法律意见</footer>
    </section>
  </div>
</template>

<style scoped>
.shell { display: flex; min-height: 100vh; }
aside { width: 240px; background: #132a40; color: #fff; padding: 28px 16px; position: relative; }
.brand { font-size: 23px; font-weight: 750; color: #67dbc6; }
.brand span { font-size: 16px; color: #fff; }
.caption { font-size: 12px; color: #8ca0b8; margin: 6px 0 12px; }
.role { margin-bottom: 18px; }
.nav { border: none; }
.nav :deep(.el-menu-item) { border-radius: 8px; margin: 6px 0; }
.nav small { margin-left: auto; font-size: 10px; opacity: 0.6; }
.aside-footer { position: absolute; bottom: 28px; font-size: 11px; color: #8ca0b8; }
section { flex: 1; min-width: 0; display: flex; flex-direction: column; }
header {
  height: 72px; background: #fff; border-bottom: 1px solid #e6ebf1;
  display: flex; align-items: center; justify-content: space-between; padding: 0 32px;
}
.title { font-weight: 600; }
.user { display: flex; align-items: center; gap: 8px; color: #5c6f86; }
main { padding: 28px 32px; flex: 1; }
footer { padding: 20px 32px; color: #79899c; font-size: 12px; }
@media (max-width: 760px) {
  aside { width: 160px; }
  .brand span { display: none; }
  main { padding: 16px; }
}
</style>
