<template>
  <div class="conv-panel" ref="panelRef">
    <div v-if="!messages.length" class="empty-state">
      <span class="empty-icon">💬</span>
      <span>暂无对话记录</span>
    </div>
    <TransitionGroup v-else name="msg" tag="div" class="msg-list">
      <div
        v-for="(msg, i) in messages"
        :key="i"
        class="msg"
        :class="msg.role"
      >
        <div class="msg-role">
          <span class="role-dot" />
          {{ msg.role === 'user' ? '用户' : '机器人' }}
        </div>
        <div class="msg-text">{{ msg.text }}</div>
      </div>
    </TransitionGroup>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'

const props = defineProps({
  messages: { type: Array, default: () => [] },
})

const panelRef = ref(null)

watch(
  () => props.messages.length,
  () => {
    nextTick(() => {
      if (panelRef.value) {
        panelRef.value.scrollTop = panelRef.value.scrollHeight
      }
    })
  }
)
</script>

<style scoped>
.conv-panel {
  height: 100%;
  overflow-y: auto;
  padding: 8px 4px;
  scroll-behavior: smooth;
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
  opacity: 0.5;
}

.msg-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.msg {
  padding: 8px 10px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid transparent;
}

.msg.user {
  border-color: rgba(79, 158, 255, 0.15);
  background: rgba(79, 158, 255, 0.04);
}

.msg.robot {
  border-color: rgba(0, 224, 122, 0.12);
  background: rgba(0, 224, 122, 0.03);
}

.msg-role {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  margin-bottom: 4px;
}

.user .msg-role { color: #4f9eff; }
.robot .msg-role { color: #00e07a; }

.role-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  flex-shrink: 0;
}

.user .role-dot { background: #4f9eff; }
.robot .role-dot { background: #00e07a; }

.msg-text {
  font-size: 12px;
  color: var(--text);
  line-height: 1.5;
}

/* Transition */
.msg-enter-active {
  animation: slide-up 0.25s ease;
}

@keyframes slide-up {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}
</style>
