<script setup lang="ts">
import { useRoute } from 'vue-router'
const route = useRoute()
</script>
<template><el-card shadow="never"><p class="muted">COMPLIANCE WORKSPACE</p><h1>{{ route.meta.title }}</h1><el-empty description="建设中 · 本模块将在 D5-b/D5-c 完成"/><router-link to="/scripts">前往话术库 →</router-link></el-card></template>
