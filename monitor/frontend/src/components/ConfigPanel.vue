<template>
  <div class="config-panel">
    <div v-if="loading" class="state-box">
      <div class="spinner" />
      <span>加载配置中...</span>
    </div>
    <div v-else-if="loadError" class="state-box error">
      <span class="state-icon">✕</span>
      <span>{{ loadError }}</span>
      <button class="btn-retry" @click="loadConfig">重试</button>
    </div>
    <template v-else>
      <!-- 保存状态提示 -->
      <Transition name="toast">
        <div v-if="toast.show" class="toast" :class="toast.type">
          {{ toast.message }}
        </div>
      </Transition>

      <div class="config-sections">
        <!-- 基础模式 -->
        <section class="cfg-section">
          <div class="cfg-section-title">
            <span class="cfg-section-icon">⬡</span> 基础模式
          </div>
          <div class="cfg-grid">
            <ConfigField
              label="唤醒模式"
              hint="software=软件KWS / hardware=硬件唤醒板"
            >
              <select v-model="form.wake_mode" class="cfg-select">
                <option value="software">software</option>
                <option value="hardware">hardware</option>
              </select>
            </ConfigField>
            <ConfigField label="ASR 后端" hint="local=本地 / iflytek_cloud=讯飞云">
              <select v-model="form.asr_backend" class="cfg-select">
                <option value="local">local</option>
                <option value="iflytek_cloud">iflytek_cloud</option>
              </select>
            </ConfigField>
            <ConfigField label="TTS 后端" hint="local=本地 / iflytek_cloud=讯飞云">
              <select v-model="form.tts_backend" class="cfg-select">
                <option value="local">local</option>
                <option value="iflytek_cloud">iflytek_cloud</option>
              </select>
            </ConfigField>
            <ConfigField label="LLM 规划器" hint="启用后支持多步自然语言指令">
              <label class="toggle">
                <input type="checkbox" v-model="form.use_llm_planner" />
                <span class="toggle-track" />
              </label>
            </ConfigField>
          </div>
        </section>

        <!-- LLM 设置 -->
        <section class="cfg-section">
          <div class="cfg-section-title">
            <span class="cfg-section-icon">◈</span> LLM 设置
          </div>
          <div class="cfg-grid">
            <ConfigField label="LLM 提供商" hint="ollama / openai / deepseek / anthropic">
              <select v-model="form.llm_provider" class="cfg-select">
                <option value="ollama">ollama</option>
                <option value="openai">openai</option>
                <option value="deepseek">deepseek</option>
                <option value="anthropic">anthropic</option>
              </select>
            </ConfigField>
            <ConfigField label="LLM 模型">
              <input v-model="form.llm_model" class="cfg-input" placeholder="qwen2.5:0.5b" />
            </ConfigField>
            <ConfigField label="Base URL" hint="Ollama 地址，在线模型留空">
              <input v-model="form.llm_base_url" class="cfg-input" placeholder="http://localhost:11434" />
            </ConfigField>
            <ConfigField label="请求超时 (秒)">
              <input v-model.number="form.llm_request_timeout" class="cfg-input" type="number" min="1" max="60" step="0.5" />
            </ConfigField>
          </div>
          <ConfigField label="系统提示词" full>
            <textarea v-model="form.llm_system_prompt" class="cfg-textarea" rows="4" />
          </ConfigField>
        </section>

        <!-- 音频 & 对话 -->
        <section class="cfg-section">
          <div class="cfg-section-title">
            <span class="cfg-section-icon">◎</span> 音频 & 对话
          </div>
          <div class="cfg-grid">
            <ConfigField label="TTS 语速" hint="1.0=正常，1.2=稍快">
              <input v-model.number="form.tts_speed" class="cfg-input" type="number" min="0.5" max="2.0" step="0.1" />
            </ConfigField>
            <ConfigField label="TTS 音量" hint="1.0=原始音量">
              <input v-model.number="form.tts_volume" class="cfg-input" type="number" min="0.1" max="3.0" step="0.1" />
            </ConfigField>
            <ConfigField label="对话超时 (秒)" hint="无活动后回到待机">
              <input v-model.number="form.dialog_timeout" class="cfg-input" type="number" min="5" max="60" step="1" />
            </ConfigField>
            <ConfigField label="最大对话历史轮">
              <input v-model.number="form.llm_max_history" class="cfg-input" type="number" min="2" max="30" step="1" />
            </ConfigField>
          </div>
        </section>

        <!-- 系统 -->
        <section class="cfg-section">
          <div class="cfg-section-title">
            <span class="cfg-section-icon">⚙</span> 系统
          </div>
          <div class="cfg-grid">
            <ConfigField label="Tick 间隔 (秒)" hint="主循环心跳">
              <input v-model.number="form.tick_interval" class="cfg-input" type="number" min="0.01" max="0.5" step="0.01" />
            </ConfigField>
            <ConfigField label="日志级别">
              <select v-model="form.log_level" class="cfg-select">
                <option>DEBUG</option>
                <option>INFO</option>
                <option>WARNING</option>
                <option>ERROR</option>
              </select>
            </ConfigField>
            <ConfigField label="启动提示音">
              <label class="toggle">
                <input type="checkbox" v-model="form.startup_sound_enabled" />
                <span class="toggle-track" />
              </label>
            </ConfigField>
            <ConfigField label="推理设备">
              <select v-model="form.onnx_provider" class="cfg-select">
                <option value="cpu">cpu</option>
                <option value="cuda">cuda</option>
              </select>
            </ConfigField>
          </div>
        </section>
      </div>

      <!-- 操作按钮 -->
      <div class="config-actions">
        <button class="btn-reset" @click="loadConfig">重置</button>
        <button class="btn-save" :disabled="saving" @click="saveConfig">
          <span v-if="saving" class="btn-spinner" />
          {{ saving ? '保存中...' : '应用配置' }}
        </button>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'

// 内联 ConfigField 子组件
const ConfigField = {
  props: {
    label: String,
    hint: String,
    full: Boolean,
  },
  template: `
    <div class="cfg-field" :class="{ 'cfg-field-full': full }">
      <label class="cfg-label">
        {{ label }}
        <span v-if="hint" class="cfg-hint">{{ hint }}</span>
      </label>
      <slot />
    </div>
  `,
}

// ---- 状态 ----
const loading = ref(false)
const loadError = ref('')
const saving = ref(false)
const form = reactive({})

const toast = reactive({ show: false, message: '', type: 'success' })

function showToast(message, type = 'success') {
  toast.message = message
  toast.type = type
  toast.show = true
  setTimeout(() => { toast.show = false }, 2500)
}

// 可编辑字段白名单（不暴露 API key）
const EDITABLE_FIELDS = [
  'wake_mode', 'asr_backend', 'tts_backend', 'use_llm_planner',
  'llm_provider', 'llm_model', 'llm_base_url', 'llm_request_timeout',
  'llm_system_prompt', 'llm_max_history',
  'tts_speed', 'tts_volume', 'dialog_timeout',
  'tick_interval', 'log_level',
  'startup_sound_enabled', 'onnx_provider',
]

async function loadConfig() {
  loading.value = true
  loadError.value = ''
  try {
    const res = await fetch('/api/config')
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    EDITABLE_FIELDS.forEach(key => {
      if (key in data) form[key] = data[key]
    })
  } catch (e) {
    loadError.value = `配置加载失败：${e.message}`
  } finally {
    loading.value = false
  }
}

async function saveConfig() {
  saving.value = true
  try {
    const payload = {}
    EDITABLE_FIELDS.forEach(key => {
      if (key in form) payload[key] = form[key]
    })
    const res = await fetch('/api/config', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    showToast('配置已应用（重启生效部分设置）', 'success')
  } catch (e) {
    showToast(`保存失败：${e.message}`, 'error')
  } finally {
    saving.value = false
  }
}

onMounted(loadConfig)
</script>

<style scoped>
.config-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
}

/* ---- 状态 ---- */
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
  width: 24px; height: 24px;
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
  transition: background 0.15s;
}

.btn-retry:hover { background: rgba(255, 64, 102, 0.1); }

/* ---- Toast ---- */
.toast {
  position: absolute;
  top: 8px;
  left: 50%;
  transform: translateX(-50%);
  padding: 6px 16px;
  border-radius: 20px;
  font-size: 11px;
  font-weight: 600;
  z-index: 100;
  white-space: nowrap;
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

/* ---- Sections ---- */
.config-sections {
  flex: 1;
  overflow-y: auto;
  padding: 6px 12px 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.cfg-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

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

.cfg-section-icon { font-size: 12px; opacity: 0.8; }

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

.cfg-field-full {
  grid-column: 1 / -1;
}

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
  color: var(--border-active, #2a4a60);
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
  transition: border-color 0.15s;
}

.cfg-input:focus,
.cfg-select:focus {
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
  line-height: 1.5;
  transition: border-color 0.15s;
}

.cfg-textarea:focus {
  border-color: var(--cyan);
  box-shadow: 0 0 0 2px rgba(0, 200, 255, 0.1);
}

/* ---- Toggle ---- */
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

/* ---- Actions ---- */
.config-actions {
  display: flex;
  gap: 8px;
  padding: 10px 12px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}

.btn-reset {
  flex: 0 0 auto;
  padding: 7px 14px;
  border-radius: 7px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-dim);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s;
}

.btn-reset:hover {
  border-color: var(--text-dim);
  color: var(--text);
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
  transition: background 0.15s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.btn-save:hover:not(:disabled) {
  background: rgba(0, 200, 255, 0.22);
}

.btn-save:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-spinner {
  width: 12px;
  height: 12px;
  border: 2px solid rgba(0, 200, 255, 0.3);
  border-top-color: var(--cyan);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
</style>
