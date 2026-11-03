import { createRouter, createWebHistory } from 'vue-router'
import { useAuth } from '../stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: () => import('../views/auth/Login.vue') },
    {
      path: '/',
      component: () => import('../layout/MainLayout.vue'),
      redirect: '/dashboard',
      children: [
        { path: '/dashboard', component: () => import('../views/dashboard/Dashboard.vue'), meta: { title: '工作台' } },
        { path: '/scripts', component: () => import('../views/script/ScriptList.vue'), meta: { title: '话术库' } },
        { path: '/audits', component: () => import('../views/audit/AuditList.vue'), meta: { title: '审查记录' } },
        { path: '/rules', component: () => import('../views/rule/RuleList.vue'), meta: { title: '规则库' } },
        { path: '/redteam', component: () => import('../views/redteam/RedTeam.vue'), meta: { title: '红队压测' } },
        { path: '/clients', component: () => import('../views/client/ClientList.vue'), meta: { title: '机构管理' } }
      ]
    },
    { path: '/:pathMatch(.*)*', redirect: '/dashboard' }
  ]
})

router.beforeEach(async to => {
  if (to.path === '/login') return true
  if (!localStorage.getItem('token')) { useAuth().logout(); return '/login' }
  if (!useAuth().user) {
    try { await useAuth().restore() } catch { return '/login' }
  }
  return true
})

export default router
