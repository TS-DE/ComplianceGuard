import { createRouter, createWebHistory } from 'vue-router'
import { useAuth } from '../stores/auth'
const router = createRouter({ history: createWebHistory(), routes: [
  { path: '/login', component: () => import('../views/auth/Login.vue') },
  { path: '/layout', component: () => import('../layout/MainLayout.vue'), children: [
    { path: '/scripts', component: () => import('../views/script/ScriptList.vue'), meta: { title: '话术库' } },
    ...[['dashboard','工作台'],['audits','审查记录'],['rules','规则库'],['redteam','红队压测'],['clients','机构管理']].map(([path,title]) => ({ path: `/${path}`, component: () => import('../views/dashboard/Placeholder.vue'), meta: { title } }))
  ] },
  { path: '/', redirect: '/dashboard' }, { path: '/:pathMatch(.*)*', redirect: '/dashboard' }
] })
router.beforeEach(async to => {
  if (to.path === '/login') return true
  if (!localStorage.getItem('token')) { useAuth().logout(); return '/login' }
  if (!useAuth().user) {
    try { await useAuth().restore() } catch { return '/login' }
  }
  return true
})
export default router
