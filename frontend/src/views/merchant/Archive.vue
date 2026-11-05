<script setup lang="ts">
/**
 * 商家端功能区二：我的档案。
 *
 * 两个标签而不是三个页面：商家查档案时的真实问题是"我递过什么"和"结果怎么样"，
 * 这两个问题在同一个上下文里来回看比来回切页面省事；
 * 而"今天查了多少"只是入口数字，不值得单独占一格菜单。
 *
 * 表格组件直接复用运营端的 SourceList / AuditList：数据裁剪在服务端
 * （`data_scope` 按机构过滤），前端不需要也不应该再自己判一次"我是商家少显示点"——
 * 那会把租户隔离做成界面层的事。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import AuditList from '../audit/AuditList.vue'
import SourceList from '../source/SourceList.vue'
import { audits as auditApi, dailyReport, type AuditRow, type DailyReport } from '../../api/resource'

const SOURCE_LABELS: Record<string, string> = {
  image: '海报图片', pdf_scan: '扫描件 PDF', pdf_text: 'PDF 文字层', docx: 'Word 文档',
  sheet: '表格', slides: 'PPT', audio: '录音', text: '文本/粘贴', no_material: '手工录入'
}

const router = useRouter()
const tab = ref<'materials' | 'history' | 'today'>('materials')
const report = ref<DailyReport | null>(null)
const recent = ref<AuditRow[]>([])
const loading = ref(false)

const today = () => {
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

const stats = computed(() => [
  { label: '今日审查', value: report.value?.total ?? 0, hint: '条' },
  { label: '需要修改', value: report.value?.violations ?? 0, hint: '命中硬违规', tone: 'hard' },
  { label: '可直接使用', value: report.value?.compliant ?? 0, hint: '未见违规', tone: 'ok' },
  { label: '判定未完成', value: report.value?.incomplete ?? 0, hint: '不当成合规', tone: 'pending' }
])
const sourceItems = computed(() => Object.entries(report.value?.by_source ?? {})
  .map(([key, count]) => ({ key, label: SOURCE_LABELS[key] ?? key, count })))

async function load() {
  loading.value = true
  try {
    report.value = await dailyReport(today())
    const page = await auditApi.list<AuditRow>({ page: 1, page_size: 5 })
    recent.value = page.items
  } catch {
    // 概览读不到不影响档案本身：宁可不显示数字，也不显示一个猜出来的数字
    report.value = null
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="archive">
    <div class="head">
      <div>
        <h2>我的档案</h2>
        <p class="m-muted">递过的材料、查过的话术与每一次结论，都在这里。</p>
      </div>
      <button class="go" @click="router.push('/m/check')">去检查新文案</button>
    </div>

    <div class="tabs" role="tablist">
      <button role="tab" :aria-selected="tab === 'materials'" :class="{ on: tab === 'materials' }"
              @click="tab = 'materials'">递过的材料</button>
      <button role="tab" :aria-selected="tab === 'history'" :class="{ on: tab === 'history' }"
              @click="tab = 'history'">查过的话术</button>
      <button role="tab" :aria-selected="tab === 'today'" :class="{ on: tab === 'today' }"
              @click="tab = 'today'">今日概览</button>
    </div>

    <!-- 表格本体复用运营端组件：裁剪在服务端做，这里不再按角色分支 -->
    <SourceList v-if="tab === 'materials'" class="pane" />
    <AuditList v-else-if="tab === 'history'" class="pane" />

    <div v-else class="pane today" v-loading="loading">
      <ul class="cards">
        <li v-for="item in stats" :key="item.label" :class="item.tone">
          <span class="num">{{ item.value }}</span>
          <span class="name">{{ item.label }}</span>
          <span class="m-muted">{{ item.hint }}</span>
        </li>
      </ul>

      <div v-if="sourceItems.length" class="block">
        <h4>今日结论来自哪些材料</h4>
        <p class="m-muted">「手工录入」表示这句话不是从上传文件里解析出来的。</p>
        <ul class="tags">
          <li v-for="item in sourceItems" :key="item.key">{{ item.label }} · {{ item.count }} 条</li>
        </ul>
      </div>

      <div class="block">
        <h4>最近五次结论</h4>
        <p v-if="!recent.length" class="m-muted">还没有审查记录。</p>
        <ul v-else class="list">
          <li v-for="row in recent" :key="row.id">
            <span class="m-quote ellipsis">{{ row.script_content || '—' }}</span>
            <span :class="['call', row.score === 0 ? 'hard' : row.score === 1 ? 'soft' : 'ok']">
              {{ row.incomplete || row.score === -1 ? '未完成' : row.score === 0 ? '违规' : row.score === 1 ? '疑似' : '合规' }}
            </span>
          </li>
        </ul>
      </div>
    </div>
  </section>
</template>

<style scoped>
.head { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--cg-m-s-4); }
.head h2 { margin-bottom: var(--cg-m-s-1); }
.head p { margin: 0; }
.go {
  border: 1px solid var(--cg-m-accent); background: transparent; color: var(--cg-m-accent);
  border-radius: var(--cg-m-radius); padding: var(--cg-m-s-2) var(--cg-m-s-4);
  font: inherit; cursor: pointer; transition: background var(--cg-m-fast), color var(--cg-m-fast);
}
.go:hover { background: var(--cg-m-accent); color: var(--cg-m-accent-ink); }

.tabs { display: flex; gap: var(--cg-m-s-4); margin: var(--cg-m-s-5) 0 var(--cg-m-s-4);
        border-bottom: 1px solid var(--cg-m-line); }
.tabs button {
  position: relative; border: 0; background: none; padding: var(--cg-m-s-2) 0 var(--cg-m-s-3);
  color: var(--cg-m-ink-2); font: inherit; cursor: pointer; transition: color var(--cg-m-fast);
}
.tabs button:hover { color: var(--cg-m-ink); }
.tabs button.on { color: var(--cg-m-ink); font-weight: 600; }
.tabs button.on::after { content: ''; position: absolute; left: 0; right: 0; bottom: -1px;
  height: 2px; background: var(--cg-m-accent); }

.pane { background: var(--cg-m-surface); border: 1px solid var(--cg-m-line);
        border-radius: var(--cg-m-radius-lg); padding: var(--cg-m-s-5); }
.today { display: flex; flex-direction: column; gap: var(--cg-m-s-5); }
.cards { list-style: none; display: grid; gap: var(--cg-m-s-3); margin: 0; padding: 0;
         grid-template-columns: repeat(4, 1fr); }
.cards li { border: 1px solid var(--cg-m-line); border-radius: var(--cg-m-radius);
            padding: var(--cg-m-s-4); display: flex; flex-direction: column; gap: 2px;
            background: var(--cg-m-surface-2); }
.cards .num { font-size: var(--cg-m-t-h2); font-weight: 600; font-variant-numeric: tabular-nums; }
.cards .name { font-size: var(--cg-m-t-aux); }
.cards li.hard .num { color: var(--cg-m-hard); }
.cards li.soft .num { color: var(--cg-m-soft); }
.cards li.pending .num { color: var(--cg-m-pending); }
.block h4 { margin-bottom: var(--cg-m-s-2); }
.tags, .list { list-style: none; margin: 0; padding: 0; }
.tags { display: flex; flex-wrap: wrap; gap: var(--cg-m-s-2); }
.tags li { border: 1px solid var(--cg-m-line); border-radius: var(--cg-m-radius-sm);
           padding: 2px var(--cg-m-s-2); font-size: var(--cg-m-t-micro); color: var(--cg-m-ink-2); }
.list li { display: flex; align-items: center; gap: var(--cg-m-s-3);
           padding: var(--cg-m-s-2) 0; border-bottom: 1px solid var(--cg-m-line); }
.list li:last-child { border-bottom: 0; }
.ellipsis { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.call { font-size: var(--cg-m-t-micro); padding: 2px var(--cg-m-s-2); border-radius: var(--cg-m-radius-sm); }
.call.hard { color: var(--cg-m-hard); background: var(--cg-m-hard-bg); }
.call.soft { color: var(--cg-m-soft); background: var(--cg-m-soft-bg); }
.call.ok { color: var(--cg-m-ok); background: var(--cg-m-ok-bg); }

@media (max-width: 1100px) {
  .cards { grid-template-columns: repeat(2, 1fr); }
  .head { flex-direction: column; }
}
</style>
