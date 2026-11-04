<script setup lang="ts">
/**
 * 登录 / 注册。
 *
 * 注册区分「商家」与「平台管理员」：
 * - 商家：需要填机构名称，注册时后端自动建机构并绑定，登录后进商家端；
 * - 管理员：不建机构，登录后进平台管理端。
 * 这样两端的入口是同一页，但落地页不同，避免商家看到平台级功能又点不动。
 */
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { useAuth } from '../../stores/auth'
import { register } from '../../api/auth'

const router = useRouter()
const auth = useAuth()
const mode = ref<'login' | 'register'>('login')
const busy = ref(false)
const formRef = ref<FormInstance>()

const form = reactive({
  username: '',
  password: '',
  role: 'merchant' as 'merchant' | 'admin',
  client_name: ''
})

const rules = computed<FormRules>(() => ({
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 50, message: '用户名 3–50 字符', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 128, message: '密码 6–128 字符', trigger: 'blur' }
  ],
  client_name: mode.value === 'register' && form.role === 'merchant'
    ? [{ required: true, message: '请填写机构名称', trigger: 'blur' },
       { max: 100, message: '不超过 100 字符', trigger: 'blur' }]
    : []
}))

async function submit() {
  if (!await formRef.value?.validate().catch(() => false)) return
  busy.value = true
  try {
    if (mode.value === 'register') {
      await register({
        username: form.username,
        password: form.password,
        role: form.role,
        client_name: form.role === 'merchant' ? form.client_name : null
      })
      ElMessage.success('注册成功')
    }
    await auth.signIn({ username: form.username, password: form.password })
    // 按角色落地：商家进商家端，其余进平台管理端。
    await router.replace(auth.user?.role === 'merchant' ? '/merchant' : '/dashboard')
  } catch {
    // API 层统一提示，避免重复弹窗。
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="login">
    <section class="intro">
      <div class="logo">CG / ComplianceGuard</div>
      <p>面向强监管营销的合规工作台</p>
      <h1>让每一句营销话术，<br>都有据可查。</h1>
      <p>话术管理 · 多轴审查 · 可追溯审计</p>
      <div class="note">
        商家可直接注册并上传自己的文案；平台管理员负责规则库、红队压测与全局审计。
      </div>
    </section>

    <section class="panel">
      <div class="box">
        <p class="muted">WELCOME TO YOUR WORKSPACE</p>
        <h2>{{ mode === 'login' ? '进入合规工作台' : '创建账号' }}</h2>
        <el-tabs v-model="mode">
          <el-tab-pane label="登录" name="login" />
          <el-tab-pane label="注册" name="register" />
        </el-tabs>

        <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent="submit">
          <el-form-item label="用户名" prop="username">
            <el-input v-model="form.username" autocomplete="username" maxlength="50" />
          </el-form-item>
          <el-form-item label="密码" prop="password">
            <el-input v-model="form.password" type="password" show-password
                      :autocomplete="mode === 'login' ? 'current-password' : 'new-password'" maxlength="128" />
          </el-form-item>

          <template v-if="mode === 'register'">
            <el-form-item label="账号类型">
              <el-radio-group v-model="form.role">
                <el-radio-button value="merchant">商家（自己机构）</el-radio-button>
                <el-radio-button value="admin">平台管理员</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item v-if="form.role === 'merchant'" label="机构名称" prop="client_name">
              <el-input v-model="form.client_name" maxlength="100" placeholder="如 某某医疗美容门诊部" />
            </el-form-item>
          </template>

          <el-button type="primary" native-type="submit" :loading="busy" class="submit">
            {{ mode === 'login' ? '登录' : '注册并登录' }}
          </el-button>
        </el-form>
        <p class="disclaimer">本系统输出为合规风险辅助提示，不构成法律意见</p>
      </div>
    </section>
  </div>
</template>

<style scoped>
.login { min-height: 100vh; display: grid; grid-template-columns: 1fr 1fr; }
.intro { background: #132a40; color: #eef6fc; padding: 64px 10%; display: flex; flex-direction: column; justify-content: center; }
.logo { font-size: 23px; font-weight: 700; color: #67dbc6; margin-bottom: 80px; }
.intro h1 { font-size: 42px; line-height: 1.6; }
.intro p, .note { color: #9fb4c9; line-height: 1.8; }
.note { margin-top: 70px; border-top: 1px solid #345064; padding-top: 24px; }
.panel { display: grid; place-items: center; padding: 40px; background: #fff; }
.box { width: 100%; max-width: 400px; }
h2 { font-size: 28px; }
.submit { width: 100%; height: 44px; margin-top: 12px; }
.disclaimer { font-size: 12px; color: #7e8a9a; margin-top: 40px; line-height: 1.8; }
@media (max-width: 760px) {
  .login { grid-template-columns: 1fr; }
  .intro { display: none; }
}
</style>
