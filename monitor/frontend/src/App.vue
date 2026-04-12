<template>
  <div class="app">
    <!-- ── Header ── -->
    <header class="header">
      <div class="logo">
        <span class="logo-hex">⬡</span>
        <span class="logo-text">Robot <em>Monitor</em></span>
      </div>

      <div class="header-center">
        <div class="active-node" v-if="activeNodeName">
          <span class="active-node-dot" :class="activeNodeStatus" />
          <span class="active-node-label">{{ activeNodeName }}</span>
          <span class="active-node-status" :class="activeNodeStatus">{{ activeNodeStatus }}</span>
        </div>
      </div>

      <div class="header-right">
        <div class="metric-chip">
          <span class="chip-label">Tick</span>
          <span class="chip-val">{{ tick || '—' }}</span>
        </div>
        <div class="metric-chip">
          <span class="chip-label">FPS</span>
          <span class="chip-val">{{ fps }}</span>
        </div>
        <div class="metric-chip" v-if="metrics.audio?.asr_ms !== undefined">
          <span class="chip-label">ASR</span>
          <span class="chip-val">{{ metrics.audio.asr_ms }}ms</span>
        </div>
        <div class="conn-badge" :class="connected ? 'conn-ok' : 'conn-err'">
          <span class="conn-dot" />
          {{ connected ? '已连接' : '连接中...' }}
        </div>
      </div>
    </header>

    <!-- ── Main ── -->
    <div class="main">
      <!-- 左侧：行为树 -->
      <section class="tree-section">
        <div class="section-bar">
          <span class="section-title">行为树</span>
          <span class="node-count" v-if="nodeCount > 0">{{ nodeCount }} 个节点</span>
        </div>
        <div class="tree-body">
          <TreeCanvas :tree="tree" />
        </div>
      </section>

      <!-- 右侧：侧边面板 -->
      <aside class="sidebar">
        <!-- Tab 导航 -->
        <div class="tabs">
          <button
            v-for="tab in TAB_LIST"
            :key="tab.id"
            class="tab-btn"
            :class="{ active: activeTab === tab.id }"
            @click="activeTab = tab.id"
          >
            <span class="tab-icon">{{ tab.icon }}</span>
            <span class="tab-label">{{ tab.label }}</span>
            <span
              v-if="tab.badge"
              class="tab-badge"
            >{{ tab.badge }}</span>
          </button>
        </div>

        <!-- Tab 内容 -->
        <div class="tab-body">
          <Transition name="fade" mode="out-in">
            <BlackboardPanel
              v-if="activeTab === 'bb'"
              :data="blackboard"
              :key="'bb'"
            />
            <ConversationPanel
              v-else-if="activeTab === 'chat'"
              :messages="conversation"
              :key="'chat'"
            />
            <ConfigPanel
              v-else-if="activeTab === 'config'"
              :key="'config'"
            />
          </Transition>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useWebSocket } from './composables/useWebSocket.js'
import TreeCanvas from './components/TreeCanvas.vue'
import BlackboardPanel from './components/BlackboardPanel.vue'
import ConversationPanel from './components/ConversationPanel.vue'
import ConfigPanel from './components/ConfigPanel.vue'

const { connected, tick, fps, tree, blackboard, conversation, metrics } = useWebSocket()

const activeTab = ref('bb')

const TAB_LIST = computed(() => [
  { id: 'bb',     icon: '◻', label: '黑板',   badge: bbCount.value || null },
  { id: 'chat',   icon: '◎', label: '对话',   badge: conversation.value.length || null },
  { id: 'config', icon: '⚙', label: '配置',   badge: null },
])

const bbCount = computed(() =>
  Object.keys(blackboard.value).filter(k => k.startsWith('/dialog/')).length
)

// 找到当前 RUNNING 或最后一个非 INVALID 节点
function findActiveNode(node) {
  if (!node) return null
  if (node.status === 'RUNNING') return node
  if (node.children) {
    for (const child of node.children) {
      const found = findActiveNode(child)
      if (found) return found
    }
  }
  return null
}

function countNodes(node) {
  if (!node) return 0
  return 1 + (node.children?.reduce((s, c) => s + countNodes(c), 0) ?? 0)
}

const activeNode = computed(() => findActiveNode(tree.value))
const activeNodeName = computed(() => activeNode.value?.name ?? '')
const activeNodeStatus = computed(() => activeNode.value?.status ?? 'INVALID')
const nodeCount = computed(() => countNodes(tree.value))
</script>

<style>
/* ── 全局 CSS 变量 ── */
:root {
  --bg:          #060b12;
  --surface:     #0b1422;
  --elevated:    #101d2e;
  --border:      #1c2e40;
  --text:        #c5d8ea;
  --text-dim:    #5e7a92;
  --cyan:        #00c8ff;
  --green:       #00e07a;
  --red:         #ff4066;
  --amber:       #ffa726;
  --blue:        #4f9eff;

  --font-ui:   'Plus Jakarta Sans', -apple-system, sans-serif;
  --font-mono: 'JetBrains Mono', 'Consolas', monospace;
}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html, body { height: 100%; }

body {
  background: var(--bg);
  color: var(--text);
  font-family: var(--font-ui);
  font-size: 13px;
  -webkit-font-smoothing: antialiased;
}

/* ── 滚动条 ── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #2a4a60; }
</style>

<style scoped>
.app {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
  background: var(--bg);
}

/* ── Header ── */
.header {
  height: 48px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  flex-shrink: 0;
  gap: 12px;
  position: relative;
}

/* 顶部高亮线 */
.header::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 2px;
  background: linear-gradient(90deg, transparent, var(--cyan), transparent);
  opacity: 0.6;
}

.logo {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.logo-hex {
  font-size: 18px;
  color: var(--cyan);
  animation: hex-pulse 3s ease-in-out infinite;
}

@keyframes hex-pulse {
  0%, 100% { opacity: 1; text-shadow: 0 0 8px var(--cyan); }
  50%       { opacity: 0.6; text-shadow: none; }
}

.logo-text {
  font-size: 15px;
  font-weight: 700;
  color: var(--text);
  letter-spacing: 0.3px;
}

.logo-text em {
  font-style: normal;
  color: var(--cyan);
}

.header-center {
  flex: 1;
  display: flex;
  justify-content: center;
}

.active-node {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--elevated);
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 4px 12px;
}

.active-node-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}

.active-node-dot.RUNNING {
  background: var(--blue);
  animation: pulse-dot 1.5s ease-in-out infinite;
}
.active-node-dot.SUCCESS { background: var(--green); }
.active-node-dot.FAILURE { background: var(--red); }
.active-node-dot.INVALID { background: var(--border); }

@keyframes pulse-dot {
  0%, 100% { box-shadow: 0 0 0 0 rgba(79, 158, 255, 0.6); }
  50%       { box-shadow: 0 0 0 5px rgba(79, 158, 255, 0); }
}

.active-node-label {
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
}

.active-node-status {
  font-size: 9px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-family: var(--font-mono);
  padding: 1px 5px;
  border-radius: 3px;
}

.active-node-status.RUNNING { color: var(--blue); background: rgba(79, 158, 255, 0.15); }
.active-node-status.SUCCESS { color: var(--green); background: rgba(0, 224, 122, 0.12); }
.active-node-status.FAILURE { color: var(--red); background: rgba(255, 64, 102, 0.12); }
.active-node-status.INVALID { color: var(--text-dim); background: rgba(94, 122, 146, 0.1); }

.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.metric-chip {
  display: flex;
  align-items: center;
  gap: 5px;
  background: var(--elevated);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 3px 10px;
}

.chip-label {
  font-size: 10px;
  color: var(--text-dim);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.4px;
}

.chip-val {
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
  font-family: var(--font-mono);
}

.conn-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-weight: 600;
  padding: 4px 12px;
  border-radius: 16px;
  border: 1px solid;
}

.conn-badge.conn-ok {
  color: var(--green);
  border-color: rgba(0, 224, 122, 0.3);
  background: rgba(0, 224, 122, 0.07);
}

.conn-badge.conn-err {
  color: var(--text-dim);
  border-color: var(--border);
  background: transparent;
}

.conn-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
  flex-shrink: 0;
}

.conn-ok .conn-dot {
  animation: blink 2s ease-in-out infinite;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.3; }
}

/* ── Main layout ── */
.main {
  display: flex;
  flex: 1;
  overflow: hidden;
  gap: 0;
}

/* ── Tree section ── */
.tree-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
  /* 网格背景增加深度感 */
  background-image:
    linear-gradient(rgba(28, 46, 64, 0.3) 1px, transparent 1px),
    linear-gradient(90deg, rgba(28, 46, 64, 0.3) 1px, transparent 1px);
  background-size: 32px 32px;
  background-position: center center;
}

.section-bar {
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  border-bottom: 1px solid var(--border);
  background: rgba(11, 20, 34, 0.8);
  backdrop-filter: blur(4px);
  flex-shrink: 0;
}

.section-title {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.8px;
  color: var(--text-dim);
}

.node-count {
  font-size: 10px;
  color: var(--text-dim);
  font-family: var(--font-mono);
  background: var(--elevated);
  padding: 2px 8px;
  border-radius: 10px;
  border: 1px solid var(--border);
}

.tree-body {
  flex: 1;
  overflow: hidden;
}

/* ── Sidebar ── */
.sidebar {
  width: 320px;
  min-width: 320px;
  border-left: 1px solid var(--border);
  background: var(--surface);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.tabs {
  display: flex;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  background: var(--elevated);
}

.tab-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 10px 4px;
  border: none;
  background: transparent;
  color: var(--text-dim);
  font-size: 11px;
  font-weight: 600;
  font-family: var(--font-ui);
  cursor: pointer;
  position: relative;
  transition: color 0.15s;
}

.tab-btn::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 20%;
  right: 20%;
  height: 2px;
  background: var(--cyan);
  border-radius: 1px;
  opacity: 0;
  transition: opacity 0.15s;
}

.tab-btn:hover { color: var(--text); }

.tab-btn.active {
  color: var(--cyan);
}

.tab-btn.active::after {
  opacity: 1;
}

.tab-icon {
  font-size: 13px;
  line-height: 1;
}

.tab-label {
  letter-spacing: 0.3px;
}

.tab-badge {
  background: rgba(0, 200, 255, 0.15);
  color: var(--cyan);
  border-radius: 8px;
  font-size: 9px;
  font-weight: 700;
  padding: 1px 5px;
  min-width: 16px;
  text-align: center;
  font-family: var(--font-mono);
}

.tab-body {
  flex: 1;
  overflow: hidden;
  position: relative;
}

.tab-body > * {
  height: 100%;
}

/* ── Tab transition ── */
.fade-enter-active, .fade-leave-active {
  transition: opacity 0.15s, transform 0.15s;
}
.fade-enter-from {
  opacity: 0;
  transform: translateY(6px);
}
.fade-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}
</style>
