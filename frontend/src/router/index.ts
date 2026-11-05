import { createRouter, createWebHistory } from 'vue-router'
import { useAuth } from '../stores/auth'

/**
 * 一个前端工程、三套入口，服务端靠 `data_scope` 裁剪数据。
 *
 * 为什么不拆两个工程：话术列表、审查记录这些页面两端都在用，拆开就要各修一份，
 * 迟早出现"只改了一边"的不一致。
 *
 * 但**外壳必须是两套**：运营端是案卷（素净、高密度、逐条裁定），
 * 商家端是门面（象牙白、细金、两个功能区）。同一套 layout 里按角色 `v-if` 换样式，
 * 等于让一个组件承担两种设计意图，改一边就碰另一边——上一版越改越拉跨就是这么来的。
 *
 * 公开首页 `/` 不需要登录：来看的人第一个问题是"这东西管谁的什么事"，
 * 直接甩一个登录框等于把答案藏起来。
 */
const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: () => import('../views/public/Landing.vue') },
    { path: '/login', component: () => import('../views/auth/Login.vue') },
    {
      // 商家端：顶部横向栏 + 两个功能区，没有左侧菜单、没有待复核入口
      path: '/m',
      component: () => import('../layout/MerchantShell.vue'),
      redirect: '/m/check',
      children: [
        { path: 'check', component: () => import('../views/merchant/Check.vue'), meta: { title: '文案审核' } },
        { path: 'archive', component: () => import('../views/merchant/Archive.vue'), meta: { title: '我的档案' } }
      ]
    },
    {
      // 运营 / 平台端：沿用案纸风 MainLayout（左侧导航在这里是合理的，任务是长时间比对与裁定）
      path: '/',
      component: () => import('../layout/MainLayout.vue'),
      redirect: '/dashboard',
      children: [
        { path: '/dashboard', component: () => import('../views/dashboard/Dashboard.vue'), meta: { title: '工作台' } },
        { path: '/scripts', component: () => import('../views/script/ScriptList.vue'), meta: { title: '话术库' } },
        { path: '/audits', component: () => import('../views/audit/AuditList.vue'), meta: { title: '审查记录' } },
        { path: '/rules', component: () => import('../views/rule/RuleList.vue'), meta: { title: '规则库' } },
        { path: '/redteam', component: () => import('../views/redteam/RedTeam.vue'), meta: { title: '红队压测' } },
        { path: '/clients', component: () => import('../views/client/ClientList.vue'), meta: { title: '机构管理' } },
        { path: '/reviews', component: () => import('../views/review/ReviewQueue.vue'), meta: { title: '待复核' } },
        { path: '/sources', component: () => import('../views/source/SourceList.vue'), meta: { title: '素材档案' } }
      ]
    },
    // 旧商家路径不能 404：书签与上一版演示链接都在用，静默改到新壳
    { path: '/merchant', redirect: '/m/archive' },
    { path: '/merchant/check', redirect: '/m/check' },
    { path: '/merchant/scripts', redirect: '/m/archive' },
    { path: '/merchant/audits', redirect: '/m/archive' },
    { path: '/merchant/sources', redirect: '/m/archive' },
    // 「待复核」不是商家的活，旧链接一律回到档案页；后端接口与运营端队列都保留
    { path: '/merchant/reviews', redirect: '/m/archive' },
    { path: '/:pathMatch(.*)*', redirect: '/' }
  ]
})

const PUBLIC = ['/', '/login']

router.beforeEach(async to => {
  if (PUBLIC.includes(to.path)) return true
  if (!localStorage.getItem('token')) {
    useAuth().logout()
    // 未登录不直接甩到登录页：先回首页，让人知道这产品是干什么的
    return '/'
  }
  const auth = useAuth()
  if (!auth.user) {
    try {
      await auth.restore()
    } catch {
      return '/login'
    }
  }
  // 按角色守门：商家进不了平台页面，平台账号也不落到商家壳里——
  // 两边看到的菜单与接口权限本来就不一样，混进去只会看到半个后台
  const merchant = auth.user?.role === 'merchant'
  if (merchant && !to.path.startsWith('/m')) return '/m/check'
  if (!merchant && to.path.startsWith('/m')) return '/dashboard'
  return true
})

/**
 * 切页后清理遗留浮层。
 *
 * Element Plus 的弹窗/抽屉把遮罩 teleport 到 body；若某个弹窗在卸载瞬间仍是打开状态，
 * 遮罩可能留在 DOM 里盖住整页，表现就是"点哪里都没反应"。
 * 这里在路径真正变化时兜底清理，并解除 body 滚动锁定。
 */
router.afterEach((to, from) => {
  if (to.path === from.path) return
  document.querySelectorAll('.el-overlay').forEach(node => node.remove())
  document.body.style.overflow = ''
})

// 懒加载 chunk 失败（例如部署后旧入口指向已删除的文件）时至少留下可查的日志，
// 而不是停在空白页什么也不说。
router.onError(error => {
  console.error('[router] 导航失败', error)
})

export default router
