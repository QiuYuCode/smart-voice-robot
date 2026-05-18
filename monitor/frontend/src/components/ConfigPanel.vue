<template>
  <div class="config-panel">
    <div v-if="loading" class="state-box">
      <div class="spinner" />
      <span>加载配置中...</span>
    </div>
    <div v-else-if="loadError" class="state-box error">
      <span class="state-icon">✕</span>
      <span>{{ loadError }}</span>
      <button class="btn-retry" @click="loadAll">重试</button>
    </div>
    <template v-else>
      <Transition name="toast">
        <div v-if="toast.show" class="toast" :class="toast.type">
          {{ toast.message }}
        </div>
      </Transition>

      <div class="config-toolbar">
        <div class="mode-tabs">
          <button
            type="button"
            class="mode-btn"
            :class="{ active: mode === 'form' }"
            @click="mode = 'form'"
          >表单</button>
          <button
            type="button"
            class="mode-btn"
            :class="{ active: mode === 'yaml' }"
            @click="switchToYaml"
          >YAML</button>
        </div>
        <span class="yaml-path" :title="yamlPath">{{ shortPath(yamlPath) }}</span>
      </div>

      <!-- 表单模式 -->
      <div v-show="mode === 'form'" class="config-sections">
        <section
          v-for="sec in sections"
          :key="sec.id"
          class="cfg-section"
        >
          <div class="cfg-section-title">
            <span class="cfg-section-icon">{{ sec.icon }}</span>
            {{ sec.title }}
          </div>
          <div class="cfg-grid">
            <div
              v-for="field in sec.fields"
              :key="field.key"
              class="cfg-field"
              :class="{ 'cfg-field-full': isFullWidth(field) }"
            >
              <label class="cfg-label">
                {{ field.label }}
                <span v-if="field.hint" class="cfg-hint">{{ field.hint }}</span>
              </label>

              <select
                v-if="field.type === 'select'"
                v-model="form[field.key]"
                class="cfg-select"
              >
                <option v-for="opt in field.options" :key="opt" :value="opt">{{ opt }}</option>
              </select>

              <label v-else-if="field.type === 'boolean'" class="toggle">
                <input type="checkbox" v-model="form[field.key]" />
                <span class="toggle-track" />
              </label>

              <textarea
                v-else-if="field.type === 'textarea' || field.type === 'json'"
                v-model="form[field.key]"
                class="cfg-textarea"
                :rows="field.rows || (field.type === 'json' ? 6 : 4)"
                :spellcheck="field.type !== 'json'"
              />

              <input
                v-else-if="field.type === 'number'"
                v-model.number="form[field.key]"
                class="cfg-input"
                type="number"
                :min="field.min"
                :max="field.max"
                :step="field.step ?? 1"
              />

              <input
                v-else
                v-model="form[field.key]"
                class="cfg-input"
                type="text"
              />
            </div>
          </div>
        </section>
      </div>

      <!-- YAML 模式 -->
      <div v-show="mode === 'yaml'" class="yaml-editor-wrap">
        <textarea
          v-model="yamlContent"
          class="yaml-editor"
          spellcheck="false"
          placeholder="# config.yaml"
        />
      </div>

      <div class="config-actions">
        <button type="button" class="btn-reset" @click="mode === 'form' ? loadAll() : loadYaml()">
          重置
        </button>
        <button
          type="button"
          class="btn-restart-only"
          :disabled="saving"
          title="不保存，仅 systemctl restart"
          @click="restartServiceOnly"
        >
          重启服务
        </button>
        <button
          type="button"
          class="btn-save"
          :disabled="saving"
          @click="mode === 'form' ? saveForm() : saveYaml()"
        >
          <span v-if="saving" class="btn-spinner" />
          {{ saving ? '保存中...' : '保存并生效' }}
        </button>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import fallbackSections from '../configFormSchema.json'

const API_HINT = '请通过 main.py 启动监控（默认 :8765），并重启进程以加载最新 API；开发模式需同时运行 main.py。'

const mode = ref('form')
const loading = ref(false)
const loadError = ref('')
const saving = ref(false)
const yamlPath = ref('config.yaml')
const yamlContent = ref('')
const sections = ref([])
const fieldMeta = ref({})

const form = reactive({})

const toast = reactive({ show: false, message: '', type: 'success' })

function showToast(message, type = 'success', duration = 2800) {
  toast.message = message
  toast.type = type
  toast.show = true
  setTimeout(() => { toast.show = false }, duration)
}

function restartToastMessage(restart) {
  if (!restart?.scheduled) return ''
  const unit = restart.unit || 'smart-voice-robot.service'
  return `，约 1 秒后重启 ${unit}`
}

function shortPath(p) {
  if (!p) return 'config.yaml'
  const parts = p.split(/[/\\]/)
  return parts.length > 2 ? `…/${parts.slice(-2).join('/')}` : p
}

function isFullWidth(field) {
  return field.type === 'textarea' || field.type === 'json'
    || ['llm_system_prompt', 'planner_system_prompt', 'vlm_system_prompt', 'mimo_tts_style'].includes(field.key)
}

function fillFormFromData(data) {
  for (const [key, meta] of Object.entries(fieldMeta.value)) {
    const raw = data[key]
    if (meta.type === 'json') {
      form[key] = raw === undefined ? '' : JSON.stringify(raw, null, 2)
    } else if (meta.type === 'boolean') {
      form[key] = Boolean(raw)
    } else {
      form[key] = raw ?? ''
    }
  }
}

function buildPayload() {
  const payload = {}
  for (const [key, meta] of Object.entries(fieldMeta.value)) {
    if (!(key in form)) continue
    let val = form[key]
    if (meta.type === 'json') {
      if (typeof val === 'string') {
        const trimmed = val.trim()
        if (!trimmed) {
          payload[key] = meta.emptyValue ?? {}
          continue
        }
        try {
          val = JSON.parse(trimmed)
        } catch (e) {
          throw new Error(`${meta.label || key} JSON 无效: ${e.message}`)
        }
      }
    }
    payload[key] = val
  }
  return payload
}

async function fetchJson(url, options) {
  const res = await fetch(url, options)
  const text = await res.text()
  const ct = (res.headers.get('content-type') || '').toLowerCase()
  const trimmed = text.trimStart()
  if (!ct.includes('json') && (trimmed.startsWith('<!') || trimmed.startsWith('<html'))) {
    throw new Error(`接口返回了 HTML 而非 JSON。${API_HINT}`)
  }
  let data
  try {
    data = text ? JSON.parse(text) : {}
  } catch {
    throw new Error(`JSON 解析失败 (HTTP ${res.status})。${API_HINT}`)
  }
  if (!res.ok) {
    throw new Error(data.error || `HTTP ${res.status}`)
  }
  return data
}

function applySections(secList) {
  sections.value = secList
  const map = {}
  for (const sec of secList) {
    for (const f of sec.fields || []) {
      map[f.key] = f
    }
  }
  fieldMeta.value = map
}

async function loadMeta() {
  try {
    const meta = await fetchJson('/api/config/meta')
    yamlPath.value = meta.yaml_path || 'config.yaml'
    applySections(meta.sections || [])
  } catch (e) {
    // 旧版监控服务无 /api/config/meta 时，使用内置表单结构
    if (String(e.message).includes('404') || String(e.message).includes('API 不存在')) {
      applySections(fallbackSections)
      return
    }
    throw e
  }
}

async function loadConfigValues() {
  const data = await fetchJson('/api/config')
  if (data.error) throw new Error(data.error)
  fillFormFromData(data)
}

async function loadYaml() {
  try {
    const data = await fetchJson('/api/config/yaml')
    yamlPath.value = data.path || yamlPath.value
    yamlContent.value = data.content ?? ''
  } catch (e) {
    if (String(e.message).includes('404') || String(e.message).includes('API 不存在')) {
      yamlContent.value = '# 当前监控服务版本不支持 YAML 直编，请重启 main.py 后重试\n'
      return
    }
    throw e
  }
}

async function loadAll() {
  loading.value = true
  loadError.value = ''
  try {
    await loadMeta()
    await Promise.all([loadConfigValues(), loadYaml()])
  } catch (e) {
    loadError.value = `配置加载失败：${e.message}`
  } finally {
    loading.value = false
  }
}

async function switchToYaml() {
  mode.value = 'yaml'
  try {
    await loadYaml()
  } catch (e) {
    showToast(`YAML 加载失败：${e.message}`, 'error')
  }
}

async function saveForm() {
  saving.value = true
  try {
    const payload = buildPayload()
    const data = await fetchJson('/api/config', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const n = Object.keys(data.applied || {}).length
    const rej = (data.rejected || []).length
    if (rej > 0) {
      showToast(`已保存 ${n} 项，${rej} 项被拒绝`, 'error')
    } else {
      showToast(
        `已写入 config.yaml（${n} 项）${restartToastMessage(data.restart)}`,
        'success',
        data.restart?.scheduled ? 5000 : 2800,
      )
    }
    await loadYaml()
  } catch (e) {
    showToast(e.message || '保存失败', 'error')
  } finally {
    saving.value = false
  }
}

async function restartServiceOnly() {
  saving.value = true
  try {
    const data = await fetchJson('/api/service/restart', { method: 'POST' })
    if (data.restart?.scheduled) {
      showToast(`正在重启 ${data.restart.unit || 'smart-voice-robot.service'}…`, 'success', 5000)
    } else {
      showToast(data.restart?.reason || '未调度重启', 'error')
    }
  } catch (e) {
    showToast(e.message || '重启失败', 'error')
  } finally {
    saving.value = false
  }
}

async function saveYaml() {
  saving.value = true
  try {
    const data = await fetchJson('/api/config/yaml', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: yamlContent.value, restart: true }),
    })
    showToast(
      `YAML 已保存${restartToastMessage(data.restart)}`,
      'success',
      data.restart?.scheduled ? 5000 : 2800,
    )
    await loadConfigValues()
  } catch (e) {
    showToast(e.message || 'YAML 保存失败', 'error')
  } finally {
    saving.value = false
  }
}

onMounted(loadAll)
</script>

<style scoped>
.config-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
}

.state-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 10px;
  color: var(--text-dim);
  font-size: 12px;
}

.state-box.error { color: #ff4066; }
.state-icon { font-size: 20px; }

.spinner {
  width: 24px;
  height: 24px;
  border: 2px solid var(--border);
  border-top-color: var(--cyan);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

.btn-retry {
  margin-top: 4px;
  padding: 4px 12px;
  border-radius: 6px;
  border: 1px solid #ff4066;
  background: transparent;
  color: #ff4066;
  font-size: 11px;
  cursor: pointer;
}

.config-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px 4px;
  gap: 8px;
  flex-shrink: 0;
}

.mode-tabs {
  display: flex;
  gap: 4px;
  background: var(--elevated);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 2px;
}

.mode-btn {
  border: none;
  background: transparent;
  color: var(--text-dim);
  font-size: 11px;
  font-weight: 600;
  padding: 4px 12px;
  border-radius: 6px;
  cursor: pointer;
}

.mode-btn.active {
  background: rgba(0, 200, 255, 0.15);
  color: var(--cyan);
}

.yaml-path {
  font-size: 9px;
  font-family: var(--font-mono);
  color: var(--text-dim);
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.toast {
  position: absolute;
  top: 44px;
  left: 50%;
  transform: translateX(-50%);
  padding: 6px 14px;
  border-radius: 20px;
  font-size: 11px;
  font-weight: 600;
  z-index: 100;
  max-width: 90%;
  text-align: center;
  pointer-events: none;
}

.toast.success {
  background: rgba(0, 224, 122, 0.15);
  border: 1px solid rgba(0, 224, 122, 0.4);
  color: #00e07a;
}

.toast.error {
  background: rgba(255, 64, 102, 0.15);
  border: 1px solid rgba(255, 64, 102, 0.4);
  color: #ff4066;
}

.toast-enter-active, .toast-leave-active { transition: opacity 0.2s, transform 0.2s; }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translateX(-50%) translateY(-6px); }

.config-sections {
  flex: 1;
  overflow-y: auto;
  padding: 4px 12px 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.yaml-editor-wrap {
  flex: 1;
  min-height: 0;
  padding: 4px 12px 0;
  display: flex;
}

.yaml-editor {
  flex: 1;
  width: 100%;
  resize: none;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: #060b12;
  color: var(--text);
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1.45;
  padding: 10px;
  outline: none;
  tab-size: 2;
}

.yaml-editor:focus {
  border-color: var(--cyan);
  box-shadow: 0 0 0 2px rgba(0, 200, 255, 0.1);
}

.cfg-section { display: flex; flex-direction: column; gap: 8px; }

.cfg-section-title {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.8px;
  color: var(--cyan);
  display: flex;
  align-items: center;
  gap: 6px;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--border);
}

.cfg-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.cfg-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.cfg-field-full { grid-column: 1 / -1; }

.cfg-label {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.cfg-hint {
  font-size: 9px;
  text-transform: none;
  letter-spacing: 0;
  font-weight: 400;
  font-family: var(--font-mono);
  color: rgba(94, 122, 146, 0.7);
}

.cfg-input,
.cfg-select {
  width: 100%;
  padding: 5px 8px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--elevated);
  color: var(--text);
  font-size: 11px;
  font-family: var(--font-mono);
  outline: none;
}

.cfg-input:focus,
.cfg-select:focus,
.cfg-textarea:focus {
  border-color: var(--cyan);
  box-shadow: 0 0 0 2px rgba(0, 200, 255, 0.1);
}

.cfg-select {
  appearance: none;
  cursor: pointer;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%235e7a92'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 8px center;
  padding-right: 24px;
}

.cfg-textarea {
  width: 100%;
  padding: 7px 8px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--elevated);
  color: var(--text);
  font-size: 11px;
  font-family: var(--font-mono);
  resize: vertical;
  outline: none;
  line-height: 1.45;
}

.toggle {
  display: inline-flex;
  align-items: center;
  cursor: pointer;
  margin-top: 2px;
}

.toggle input { display: none; }

.toggle-track {
  width: 32px;
  height: 18px;
  background: var(--border);
  border-radius: 9px;
  position: relative;
  transition: background 0.2s;
}

.toggle-track::after {
  content: '';
  position: absolute;
  width: 12px;
  height: 12px;
  background: var(--text-dim);
  border-radius: 50%;
  top: 3px;
  left: 3px;
  transition: transform 0.2s, background 0.2s;
}

.toggle input:checked + .toggle-track {
  background: rgba(0, 200, 255, 0.25);
}

.toggle input:checked + .toggle-track::after {
  transform: translateX(14px);
  background: var(--cyan);
}

.config-actions {
  display: flex;
  gap: 6px;
  padding: 10px 12px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}

.btn-restart-only {
  flex: 0 0 auto;
  padding: 7px 10px;
  border-radius: 7px;
  border: 1px solid var(--amber, #ffa726);
  background: rgba(255, 167, 38, 0.08);
  color: #ffa726;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}

.btn-restart-only:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-reset {
  padding: 7px 14px;
  border-radius: 7px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-dim);
  font-size: 12px;
  cursor: pointer;
}

.btn-save {
  flex: 1;
  padding: 7px 14px;
  border-radius: 7px;
  border: 1px solid var(--cyan);
  background: rgba(0, 200, 255, 0.12);
  color: var(--cyan);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.btn-save:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-spinner {
  width: 12px;
  height: 12px;
  border: 2px solid rgba(0, 200, 255, 0.3);
  border-top-color: var(--cyan);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
</style>
