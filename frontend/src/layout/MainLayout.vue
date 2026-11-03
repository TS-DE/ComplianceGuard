<script setup lang="ts">
import { useAuth } from '../stores/auth'
import { useRouter, useRoute } from 'vue-router'
const auth = useAuth(), router = useRouter(), route = useRoute()
const menus = [['dashboard','工作台'],['scripts','话术库'],['audits','审查记录'],['rules','规则库'],['redteam','红队压测'],['clients','机构管理']]
function logout() { auth.logout(); void router.replace('/login') }
</script>
<template>
  <div class="shell"><aside><div class="brand">CG <span>ComplianceGuard</span></div><p class="caption">营销合规 · 风险可追溯</p>
    <el-menu router :default-active="route.path" background-color="#132a40" text-color="#bccbdd" active-text-color="#67dbc6">
      <el-menu-item v-for="[path,title] in menus" :key="path" :index="`/${path}`">{{ title }} <small v-if="path !== 'scripts'">建设中</small></el-menu-item>
    </el-menu><div class="aside-footer">合规风险辅助平台 / D5-a</div></aside>
    <section><header><span>{{ route.meta.title }}</span><div>{{ auth.user?.username }} <el-button text @click="logout">退出登录</el-button></div></header>
      <main><router-view /></main><footer>本系统输出为合规风险辅助提示，不构成法律意见</footer></section></div>
</template>
<style scoped>
.shell{display:flex;min-height:100vh}aside{width:240px;background:#132a40;color:white;padding:28px 16px;position:relative}.brand{font-size:23px;font-weight:750;color:#67dbc6}.brand span{font-size:16px;color:white}.caption{font-size:12px;color:#8ca0b8;margin-bottom:42px}.el-menu{border:none}.el-menu-item{border-radius:8px;margin:8px 0}small{margin-left:auto;font-size:10px;opacity:.6}.aside-footer{position:absolute;bottom:28px;font-size:11px;color:#8ca0b8}section{flex:1;min-width:0}header{height:72px;background:white;border-bottom:1px solid #e6ebf1;display:flex;align-items:center;justify-content:space-between;padding:0 32px}main{padding:28px 32px}footer{padding:20px 32px;color:#79899c;font-size:12px}@media(max-width:760px){aside{width:160px}.brand span{display:none}main{padding:16px}}
</style>
