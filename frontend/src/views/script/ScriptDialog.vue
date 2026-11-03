<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { scripts, type Client, type ScriptRow } from '../../api/resource'
const props = defineProps<{ modelValue: boolean; clients: Client[]; item: ScriptRow | null }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean]; saved: [] }>()
const form = reactive({ client_id: undefined as number | undefined, scene: '', content: '' })
const formRef = ref<FormInstance>(), busy = ref(false)
watch(() => props.modelValue, open => {
  if (open) { form.client_id = props.item?.client_id; form.scene = props.item?.scene ?? ''; form.content = props.item?.content ?? ''; formRef.value?.clearValidate() }
})
// 前端设置保守输入上限，避免长文本误粘贴；不是后端已声明的最大长度。
const rules: FormRules = { client_id: [{ required: true, message: '请选择机构', trigger: 'change' }], scene: [{ max: 50, message: '场景最多50字符', trigger: 'blur' }], content: [{ required: true, whitespace: true, message: '请输入话术内容', trigger: 'blur' }, { max: 10000, message: '本页面最多输入10000字符', trigger: 'blur' }] }
async function save() {
  if (!await formRef.value?.validate().catch(() => false) || !form.client_id) return
  busy.value = true
  try { const data = { client_id: form.client_id, scene: form.scene || null, content: form.content }
    if (props.item) await scripts.update(props.item.id, data); else await scripts.create(data)
    ElMessage.success('话术已保存'); emit('saved'); emit('update:modelValue', false)
  } catch { /* 失败保留表单，错误由API层统一提示。 */ } finally { busy.value = false }
}
</script>
<template><el-dialog :model-value="modelValue" :title="item ? '编辑话术' : '新建话术'" width="620px" :close-on-click-modal="false" @update:model-value="emit('update:modelValue', $event)">
<el-form ref="formRef" :model="form" :rules="rules" label-position="top"><el-form-item label="所属机构" prop="client_id"><el-select v-model="form.client_id" filterable placeholder="请选择机构"><el-option v-for="client in clients" :key="client.id" :label="client.name" :value="client.id"/></el-select></el-form-item><el-form-item label="业务场景" prop="scene"><el-select v-model="form.scene" filterable allow-create default-first-option clearable><el-option v-for="scene in ['双眼皮','热玛吉','美白','祛斑','植发']" :key="scene" :label="scene" :value="scene"/></el-select></el-form-item><el-form-item label="话术内容" prop="content"><el-input v-model="form.content" type="textarea" :rows="7" maxlength="10000" show-word-limit placeholder="录入需要审查的原始话术"/></el-form-item></el-form>
<template #footer><el-button @click="emit('update:modelValue', false)">取消</el-button><el-button type="primary" :loading="busy" @click="save">保存</el-button></template></el-dialog></template>
