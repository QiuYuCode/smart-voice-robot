<template>
  <div class="log-panel">
    <div class="log-toolbar">
      <select v-model="lines" class="log-select" @change="fetchLogs">
        <option :value="100">100 行</option>
        <option :value="200">200 行</option>
        <option :value="500">500 行</option>
        <option :value="1000">1000 行</option>
      </select>
      <select v-model="since" class="log-select" @change="fetchLogs">
        <option value="">全部</option>
        <option value="10 min ago">近 10 分钟</option>
        <option value="1 hour ago">近 1 小时</option>
        <option value="today">今天</option>
        <option value="boot">本次启动</option>
      </select>
      <label class="auto-refresh">
        <input type="checkbox" v-model="autoRefresh" />
        自动刷新
      </label>
      <button type="button" class="btn-refresh" :disabled="loading" @click="fetchLogs">
        {{ loading ? '…' : '刷新' }}
      </button>
    </div>

    <div v-if="error" class="log-error">{{ error }}</div>

    <pre
      ref="logRef"
      class="log-view"
      :class="{ loading }"
    ><code v-html="highlightedLog" /></pre>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'

const lines = ref(200)
const since = ref('')
const autoRefresh = ref(true)
const loading = ref(false)
const error = ref('')
const logText = ref('')
const unit = ref('smart-voice-robot.service')
const logRef = ref(null)

let timer = null

function escapeHtml(s) {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

function lineClass(line) {
  if (/\b(ERROR|CRITICAL|FATAL)\b/i.test(line) || /失败|错误/i.test(line)) return 'err'
  if (/\b(WARNING|WARN)\b/i.test(line)) return 'warn'
  if (/\b(INFO)\b/i.test(line)) return 'info'
  if (/\b(DEBUG)\b/i.test(line)) return 'dbg'
  return ''
}

const highlightedLog = computed(() => {
  if (!logText.value) return '<span class="dim">加载中…</span>'
  return logText.value
    .split('\n')
    .map((line) => {
      const cls = lineClass(line)
      const html = escapeHtml(line)
      return cls ? `<span class="line ${cls}">${html}</span>` : `<span class="line">${html}</span>`
    })
    .join('\n')
})

async function fetchJson(url) {
  const res = await fetch(url)
  const text = await res.text()
  const trimmed = text.trimStart()
  if (trimmed.startsWith('<!') || trimmed.startsWith('<html')) {
    throw new Error('接口返回 HTML，请确认 main.py 监控服务已启动')
  }
  const data = text ? JSON.parse(text) : {}
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`)
  return data
}

async function fetchLogs() {
  loading.value = true
  error.value = ''
  try {
    const params = new URLSearchParams({ lines: String(lines.value) })
    if (since.value) params.set('since', since.value)
    const data = await fetchJson(`/api/service/logs?${params}`)
    unit.value = data.unit || unit.value
    logText.value = data.text || ''
    await nextTick()
    if (logRef.value) {
      logRef.value.scrollTop = logRef.value.scrollHeight
    }
  } catch (e) {
    error.value = e.message || '加载日志失败'
    logText.value = ''
  } finally {
    loading.value = false
  }
}

function setupTimer() {
  clearInterval(timer)
  if (autoRefresh.value) {
    timer = setInterval(fetchLogs, 3000)
  }
}

watch(autoRefresh, setupTimer)

onMounted(() => {
  fetchLogs()
  setupTimer()
})

onUnmounted(() => {
  clearInterval(timer)
})
</script>

<style scoped>
.log-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.log-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  background: var(--elevated);
}

.log-select {
  padding: 4px 8px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  font-size: 10px;
  font-family: var(--font-mono);
}

.auto-refresh {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 10px;
  color: var(--text-dim);
  cursor: pointer;
  user-select: none;
}

.auto-refresh input {
  accent-color: var(--cyan);
}

.btn-refresh {
  margin-left: auto;
  padding: 4px 10px;
  border-radius: 6px;
  border: 1px solid var(--cyan);
  background: rgba(0, 200, 255, 0.1);
  color: var(--cyan);
  font-size: 10px;
  font-weight: 600;
  cursor: pointer;
}

.btn-refresh:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.log-error {
  padding: 8px 10px;
  font-size: 11px;
  color: #ff4066;
  background: rgba(255, 64, 102, 0.08);
  border-bottom: 1px solid rgba(255, 64, 102, 0.2);
  flex-shrink: 0;
}

.log-view {
  flex: 1;
  margin: 0;
  padding: 8px 10px;
  overflow: auto;
  font-family: var(--font-mono);
  font-size: 10px;
  line-height: 1.45;
  color: var(--text-dim);
  background: #060b12;
  white-space: pre-wrap;
  word-break: break-all;
}

.log-view.loading {
  opacity: 0.65;
}

.log-view :deep(.line) {
  display: block;
}

.log-view :deep(.line.err) { color: #ff4066; }
.log-view :deep(.line.warn) { color: #ffa726; }
.log-view :deep(.line.info) { color: #c5d8ea; }
.log-view :deep(.line.dbg) { color: #5e7a92; }
.log-view :deep(.dim) { color: #5e7a92; }
</style>
