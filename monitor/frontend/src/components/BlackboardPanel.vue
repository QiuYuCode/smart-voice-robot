<template>
  <div class="bb-panel">
    <div v-if="!entries.length" class="empty-state">
      <span class="empty-icon">◻</span>
      <span>黑板为空</span>
    </div>
    <div v-else class="bb-list">
      <div
        v-for="[key, val] in entries"
        :key="key"
        class="bb-row"
      >
        <span class="bb-key" :title="key">{{ shortKey(key) }}</span>
        <span class="bb-val" :class="valClass(val)">{{ formatVal(val) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  data: { type: Object, default: () => ({}) },
})

const entries = computed(() =>
  Object.entries(props.data).filter(([k]) => k.startsWith('/dialog/'))
)

function shortKey(k) {
  return k.replace('/dialog/', '')
}

function formatVal(v) {
  if (v === null || v === undefined) return 'null'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

function valClass(v) {
  if (v === null || v === undefined) return 'val-null'
  if (v === true)  return 'val-true'
  if (v === false) return 'val-false'
  if (typeof v === 'number') return 'val-num'
  return 'val-str'
}
</script>

<style scoped>
.bb-panel {
  height: 100%;
  overflow-y: auto;
  padding: 8px 0;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-dim);
  gap: 8px;
  font-size: 12px;
}

.empty-icon {
  font-size: 24px;
  opacity: 0.3;
}

.bb-list {
  padding: 0 4px;
}

.bb-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 6px;
  transition: background 0.15s;
}

.bb-row:hover {
  background: rgba(255, 255, 255, 0.03);
}

.bb-key {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-dim);
  min-width: 110px;
  max-width: 120px;
  flex-shrink: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.bb-val {
  font-family: var(--font-mono);
  font-size: 11px;
  word-break: break-all;
  flex: 1;
}

.val-null   { color: var(--text-dim); font-style: italic; }
.val-true   { color: #00e07a; }
.val-false  { color: #ff4066; }
.val-num    { color: #ffa726; }
.val-str    { color: var(--text); }
</style>
