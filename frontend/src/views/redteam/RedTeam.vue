<script setup lang="ts">
/**
 * 红队压测：让「攻击智能体」生成擦边话术，再由「裁判智能体」判定，
 * 最后回答一个业务真正关心的问题——这套判定到底漏掉了什么。
 *
 * 两点刻意设计：
 * 1) 明确告知成本与耗时（一次 16 条约 2–3 分钟、约 0.13 元），
 *    避免用户以为点了没反应又重复点。
 * 2) 历史 run 只在本机 localStorage 保留最近几条；查看仍走服务端接口，
 *    所以换机器或清缓存不会伪造出「历史结果」。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  allClients, runRedTeam, redTeamGaps, REDTEAM_AXES,
  type Client, type RedTeamGaps
} from '../../api/resource'
import RedTeamResult from './RedTeamResult.vue'

const HISTORY_KEY = 'cg.redteam.runs'
const clients = ref<Client[]>([])
const clientId = ref<number>()
const scene = ref('双眼皮')
const axes = ref<string[]>(REDTEAM_AXES.map(axis => axis.value))
const running = ref(false)
const loadingGaps = ref(false)
const gaps = ref<RedTeamGaps | null>(null)
const runIdInput = ref('')
const history = ref<{ runId: string; at: string; generated: number }[]>([])

const estimate = computed(() => axes.value.length * 3 + 4)

function loadHistory() {
  try {
    const raw = localStorage.getItem(HISTORY_KEY)
    history.value = raw ? JSON.parse(raw) as { runId: string; at: string; generated: number }[] : []
  } catch {
    history.value = []
  }
}

function pushHistory(runId: string, generated: number) {
  const next = [
    { runId, at: new Date().toLocaleString(), generated },
    ...history.value.filter(item => item.runId !== runId)
  ].slice(0, 8)
  history.value = next
  localStorage.setItem(HISTORY_KEY, JSON.stringify(next))
}

async function startRun() {
  if (!clientId.value) { ElMessage.warning('请先选择机构'); return }
  if (!scene.value.trim()) { ElMessage.warning('请填写场景'); return }
  if (!axes.value.length) { ElMessage.warning('至少选择一个目标轴'); return }
  running.value = true
  gaps.value = null
  try {
    const result = await runRedTeam(clientId.value, scene.value.trim(), axes.value)
    ElMessage.success(`压测完成，生成 ${result.generated} 条样本`)
    pushHistory(result.run_id, result.generated)
    runIdInput.value = result.run_id
    await loadGaps(result.run_id)
  } catch {
    // 失败不写历史、不伪造结果；API 层已提示。
  } finally {
    running.value = false
  }
}

async function loadGaps(runId: string) {
  const id = runId.trim()
  if (!id) { ElMessage.warning('请输入 run_id'); return }
  loadingGaps.value = true
  try {
    gaps.value = await redTeamGaps(id)
  } catch {
    // 不存在或失败时保持上一次结果不变，避免误导。
  } finally {
    loadingGaps.value = false
  }
}

onMounted(async () => {
  loadHistory()
  try {
    clients.value = await allClients()
    if (clients.value.length) clientId.value = clients.value[0].id
  } catch {
    // 机构接口失败不白屏。
  }
})
</script>

<template>
  <div>
    <p class="muted">RED TEAM / 红队压测</p>
    <h1>红队压测</h1>
    <p class="muted">
      攻击智能体按目标轴生成递进话术（low / mid / high + 1 条合规对照），裁判智能体逐条判定，
      产出漏杀与误杀清单。
    </p>

    <el-card shadow="never">
      <div class="form">
        <el-form label-width="88px" class="form-inner">
          <el-form-item label="机构">
            <el-select v-model="clientId" filterable placeholder="选择机构" style="width: 260px">
              <el-option v-for="client in clients" :key="client.id"
                         :label="`${client.id} · ${client.name}`" :value="client.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="场景">
            <el-input v-model="scene" maxlength="50" style="width: 260px" placeholder="如 双眼皮 / 热玛吉" />
          </el-form-item>
          <el-form-item label="目标轴">
            <el-checkbox-group v-model="axes">
              <el-checkbox v-for="axis in REDTEAM_AXES" :key="axis.value" :value="axis.value">
                {{ axis.label }}
              </el-checkbox>
            </el-checkbox-group>
          </el-form-item>
        </el-form>

        <div class="actions">
          <el-button type="primary" :loading="running" @click="startRun">
            {{ running ? '生成与判定中，约 2-3 分钟…' : '开始压测' }}
          </el-button>
          <span class="muted">
            本次将生成约 {{ estimate }} 条样本（{{ axes.length }} 轴 × 3 档 + 4 条对照），
            预计 2–3 分钟、约 0.13 元。
          </span>
        </div>
      </div>
    </el-card>

    <el-card shadow="never" style="margin-top: 16px">
      <div class="lookup">
        <el-input v-model="runIdInput" placeholder="输入 run_id 查看历史结果" style="width: 420px"
                  clearable @keyup.enter="loadGaps(runIdInput)" />
        <el-button :loading="loadingGaps" @click="loadGaps(runIdInput)">查看</el-button>
      </div>
      <div v-if="history.length" class="history">
        <span class="muted">最近：</span>
        <el-tag v-for="item in history" :key="item.runId" class="hist-tag" effect="plain"
                @click="runIdInput = item.runId; loadGaps(item.runId)">
          {{ item.runId }} · {{ item.generated }} 条
        </el-tag>
      </div>
    </el-card>

    <div v-loading="loadingGaps" style="margin-top: 16px">
      <RedTeamResult v-if="gaps" :data="gaps" />
      <el-empty v-else description="尚无压测结果，选择机构与目标轴后开始" />
    </div>
  </div>
</template>

<style scoped>
.muted { color: var(--el-text-color-secondary); font-size: 13px; }
.form { display: flex; flex-direction: column; gap: 8px; }
.form-inner { max-width: 760px; }
.actions { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; padding-left: 8px; }
.lookup { display: flex; gap: 12px; align-items: center; }
.history { margin-top: 12px; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.hist-tag { cursor: pointer; }
</style>
