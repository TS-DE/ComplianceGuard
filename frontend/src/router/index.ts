import { createRouter, createWebHistory } from 'vue-router'
import { useAuth } from '../stores/auth'

/**
 * 平台端与商家端共用一套前端与一套接口，靠服务端的 `data_scope` 隔离数据。
 *
 * 为什么不拆两个前端工程：话术列表、审查详情这些页面两端都在用，
 * 拆开就要复制两份并各自维护；差异只在"看哪些菜单、能不能进平台级功能"，
 * 用一层路由判断就够，复制两份反而容易出现只改一边的不一致。
 */
const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: () => import('../views/auth/Login.vue') },
    {
      path: '/',
      component: () => import('../layout/MainLayout.vue'),
      redirect: '/dashboard',
      children: [
        // 平台侧
        { path: '/dashboard', component: () => import('../views/dashboard/Dashboard.vue'), meta: { title: '工作台' } },
        { path: '/scripts', component: () => import('../views/script/ScriptList.vue'), meta: { title: '话术库' } },
        { path: '/audits', component: () => import('../views/audit/AuditList.vue'), meta: { title: '审查记录' } },
        { path: '/rules', component: () => import('../views/rule/RuleList.vue'), meta: { title: '规则库' } },
        { path: '/redteam', component: () => import('../views/redteam/RedTeam.vue'), meta: { title: '红队压测' } },
        { path: '/clients', component: () => import('../views/client/ClientList.vue'), meta: { title: '机构管理' } },
        { path: '/sources', component: () => import('../views/source/SourceList.vue'), meta: { title: '素材档案' } },
        // 商家侧（复用话术库与审查记录组件，数据由服务端按机构裁剪）
        { path: '/merchant', component: () => import('../views/merchant/Portal.vue'), meta: { title: '我的工作台' } },
        { path: '/merchant/check', component: () => import('../views/merchant/Check.vue'), meta: { title: '文案检查' } },
        { path: '/merchant/scripts', component: () => import('../views/script/ScriptList.vue'), meta: { title: '我的话术' } },
        { path: '/merchant/audits', component: () => import('../views/audit/AuditList.vue'), meta: { title: '审查历史' } },
        { path: '/merchant/sources', component: () => import('../views/source/SourceList.vue'), meta: { title: '素材档案' } }
      ]
    },
    { path: '/:pathMatch(.*)*', redirect: '/dashboard' }
  ]
})

router.beforeEach(async to => {
  if (to.path === '/login') return true
  if (!localStorage.getItem('token')) {
    useAuth().logout()
    return '/login'
  }
  const auth = useAuth()
  if (!auth.user) {
    try {
      await auth.restore()
    } catch {
      return '/login'
    }
  }
  // 按角色守门：商家进不了平台级页面（规则库/红队/机构管理），
  // 平台账号也不该落到商家端，避免看到"半个后台"。
  const merchant = auth.user?.role === 'merchant'
  if (merchant && !to.path.startsWith('/merchant')) return '/merchant'
  if (!merchant && to.path.startsWith('/merchant')) return '/dashboard'
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
