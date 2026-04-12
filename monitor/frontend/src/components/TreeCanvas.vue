<template>
  <div class="tree-wrap" ref="wrapRef">
    <!-- 空状态 -->
    <div v-if="!tree" class="tree-empty">
      <div class="empty-icon">⬡</div>
      <p>等待行为树数据...</p>
    </div>

    <template v-else>
      <!-- 缩放控件 -->
      <div class="zoom-controls">
        <button class="zoom-btn" title="放大" @click="zoomIn">+</button>
        <span class="zoom-label">{{ Math.round(scale * 100) }}%</span>
        <button class="zoom-btn" title="缩小" @click="zoomOut">−</button>
        <button class="zoom-btn" title="重置" @click="resetView">⊙</button>
      </div>

      <!-- 可缩放/拖拽容器 -->
      <div
        class="pan-layer"
        @wheel.prevent="onWheel"
        @mousedown="onMouseDown"
        @mousemove="onMouseMove"
        @mouseup="onMouseUp"
        @mouseleave="onMouseUp"
        :style="{ cursor: dragging ? 'grabbing' : 'grab' }"
      >
        <!-- 变换层 -->
        <div
          class="transform-layer"
          :style="transformStyle"
        >
          <!-- SVG 连线层 -->
          <svg
            class="tree-svg"
            :width="canvasW"
            :height="canvasH"
            :viewBox="`0 0 ${canvasW} ${canvasH}`"
          >
            <defs>
              <filter id="glow-blue" x="-20%" y="-20%" width="140%" height="140%">
                <feGaussianBlur stdDeviation="2.5" result="blur" />
                <feMerge>
                  <feMergeNode in="blur" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>
            <path
              v-for="(edge, i) in edges"
              :key="i"
              :d="edgePath(edge)"
              fill="none"
              :stroke="edgeColor(edge.status)"
              stroke-width="1.5"
              stroke-opacity="0.6"
              :filter="edge.status === 'RUNNING' ? 'url(#glow-blue)' : ''"
            />
          </svg>

          <!-- 节点卡片层 -->
          <div
            class="tree-canvas"
            :style="{ width: canvasW + 'px', height: canvasH + 'px' }"
          >
            <div
              v-for="item in layout"
              :key="item.node.id"
              class="ncard"
              :class="item.node.status"
              :style="{ left: item.x + 'px', top: item.y + 'px' }"
            >
              <div class="ncard-head">
                <span class="status-dot" />
                <span class="ncard-name" :title="item.node.name">{{ item.node.name }}</span>
              </div>
              <div class="ncard-foot">
                <span class="ncard-type">{{ item.node.type }}</span>
                <span class="ncard-badge">{{ item.node.status }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'

const props = defineProps({
  tree: { type: Object, default: null },
})

// ── 节点卡片尺寸 & 间距 ─────────────────────────────────
const NW = 120   // 节点宽度（紧凑以容纳更多叶节点）
const NH = 56    // 节点高度
const GX = 8     // 水平间距
const GY = 72    // 垂直间距（加大，改善纵向空间感）
const PAD = 24

// ── 缩放/拖拽状态 ───────────────────────────────────────
const wrapRef = ref(null)
const scale = ref(1)
const tx = ref(0)
const ty = ref(0)

const SCALE_MIN = 0.2
const SCALE_MAX = 2.5
const SCALE_STEP = 0.12

let dragging = ref(false)
let dragStartX = 0
let dragStartY = 0
let dragStartTx = 0
let dragStartTy = 0

const transformStyle = computed(() => ({
  transform: `translate(${tx.value}px, ${ty.value}px) scale(${scale.value})`,
  transformOrigin: '0 0',
}))

function clampScale(s) {
  return Math.min(SCALE_MAX, Math.max(SCALE_MIN, s))
}

function zoomAt(clientX, clientY, factor) {
  const rect = wrapRef.value?.getBoundingClientRect()
  if (!rect) return
  const ox = clientX - rect.left
  const oy = clientY - rect.top
  const newScale = clampScale(scale.value * factor)
  const ratio = newScale / scale.value
  tx.value = ox - (ox - tx.value) * ratio
  ty.value = oy - (oy - ty.value) * ratio
  scale.value = newScale
}

function onWheel(e) {
  const factor = e.deltaY < 0 ? (1 + SCALE_STEP) : (1 - SCALE_STEP)
  zoomAt(e.clientX, e.clientY, factor)
}

function onMouseDown(e) {
  if (e.button !== 0) return
  dragging.value = true
  dragStartX = e.clientX
  dragStartY = e.clientY
  dragStartTx = tx.value
  dragStartTy = ty.value
}

function onMouseMove(e) {
  if (!dragging.value) return
  tx.value = dragStartTx + (e.clientX - dragStartX)
  ty.value = dragStartTy + (e.clientY - dragStartY)
}

function onMouseUp() {
  dragging.value = false
}

function zoomIn()  { zoomAt(wrapRef.value ? wrapRef.value.clientWidth/2 : 0, wrapRef.value ? wrapRef.value.clientHeight/2 : 0, 1 + SCALE_STEP * 2) }
function zoomOut() { zoomAt(wrapRef.value ? wrapRef.value.clientWidth/2 : 0, wrapRef.value ? wrapRef.value.clientHeight/2 : 0, 1 - SCALE_STEP * 2) }

// 自动将整棵树缩放居中到视口
// 策略：优先高度适配，宽度超出时允许横向平移；最小缩放 35%
function fitToView() {
  const wrap = wrapRef.value
  if (!wrap || !layout.value.length) return
  const cw = canvasW.value
  const ch = canvasH.value
  const vw = wrap.clientWidth
  const vh = wrap.clientHeight

  const scaleByW = (vw * 0.92) / cw
  const scaleByH = (vh * 0.88) / ch
  // 优先完整显示整棵树；如果比例太小则设置最低可读缩放
  const fitted = Math.min(scaleByW, scaleByH)
  const newScale = clampScale(Math.max(fitted, 0.35))

  scale.value = newScale
  // 水平居中（超出视口时从左边开始，用户可横向拖拽）
  tx.value = Math.max(16, (vw - cw * newScale) / 2)
  // 垂直居中（树比视口矮时居中，否则从顶部留边距）
  ty.value = Math.max(20, (vh - ch * newScale) / 2)
}

function resetView() {
  fitToView()
}

// 树变化时自动适配视图
watch(() => props.tree, async (newTree) => {
  if (!newTree) return
  await nextTick()
  fitToView()
}, { flush: 'post' })

// ── 布局算法 ─────────────────────────────────────────────

function leafCount(node) {
  if (!node.children?.length) return 1
  return node.children.reduce((s, c) => s + leafCount(c), 0)
}

function buildLayout(node, depth, offsetX, out) {
  const lc = leafCount(node)
  const span = lc * (NW + GX) - GX
  const x = offsetX + (span - NW) / 2
  const y = PAD + depth * (NH + GY)
  const item = { node, x, y }
  out.push(item)
  if (node.children?.length) {
    let cx = offsetX
    for (const child of node.children) {
      buildLayout(child, depth + 1, cx, out)
      cx += leafCount(child) * (NW + GX)
    }
  }
  return item
}

function buildEdges(root, layoutMap) {
  const result = []
  function walk(node) {
    if (!node.children) return
    for (const child of node.children) {
      const p = layoutMap[node.id]
      const c = layoutMap[child.id]
      if (p && c) {
        result.push({
          x1: p.x + NW / 2, y1: p.y + NH,
          x2: c.x + NW / 2, y2: c.y,
          status: node.status,
        })
      }
      walk(child)
    }
  }
  walk(root)
  return result
}

// ── 计算属性 ─────────────────────────────────────────────

const layout = computed(() => {
  if (!props.tree) return []
  const out = []
  buildLayout(props.tree, 0, PAD, out)
  return out
})

const layoutMap = computed(() => {
  const m = {}
  layout.value.forEach(item => { m[item.node.id] = item })
  return m
})

const edges = computed(() => {
  if (!props.tree) return []
  return buildEdges(props.tree, layoutMap.value)
})

const canvasW = computed(() => {
  if (!layout.value.length) return 600
  return Math.max(...layout.value.map(i => i.x)) + NW + PAD * 2
})

const canvasH = computed(() => {
  if (!layout.value.length) return 400
  return Math.max(...layout.value.map(i => i.y)) + NH + PAD * 2
})

// ── 辅助函数 ─────────────────────────────────────────────

const STATUS_COLORS = {
  RUNNING: '#4f9eff',
  SUCCESS: '#00e07a',
  FAILURE: '#ff4066',
  INVALID: '#1c2e40',
}

function edgeColor(status) {
  return STATUS_COLORS[status] ?? '#1c2e40'
}

function edgePath(edge) {
  // 贝塞尔曲线控制点：纵向偏移量基于 GY
  const cpOffset = GY * 0.5
  return `M${edge.x1},${edge.y1} C${edge.x1},${edge.y1 + cpOffset} ${edge.x2},${edge.y2 - cpOffset} ${edge.x2},${edge.y2}`
}
</script>

<style scoped>
.tree-wrap {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  user-select: none;
}

/* ── 空状态 ── */
.tree-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-dim);
  gap: 12px;
}

.empty-icon {
  font-size: 40px;
  opacity: 0.3;
  animation: spin 8s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

.tree-empty p {
  font-size: 13px;
  font-family: var(--font-mono);
}

/* ── 缩放控件 ── */
.zoom-controls {
  position: absolute;
  bottom: 14px;
  right: 14px;
  z-index: 20;
  display: flex;
  align-items: center;
  gap: 4px;
  background: rgba(11, 20, 34, 0.88);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 4px 6px;
  backdrop-filter: blur(6px);
}

.zoom-btn {
  width: 24px;
  height: 24px;
  border: none;
  background: transparent;
  color: var(--text-dim);
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: color 0.15s, background 0.15s;
}

.zoom-btn:hover {
  color: var(--cyan);
  background: rgba(0, 200, 255, 0.08);
}

.zoom-label {
  font-size: 11px;
  font-family: var(--font-mono);
  color: var(--text-dim);
  min-width: 36px;
  text-align: center;
}

/* ── 拖拽层 ── */
.pan-layer {
  width: 100%;
  height: 100%;
  overflow: hidden;
  position: relative;
}

/* ── 变换层（scale + translate 在此应用）── */
.transform-layer {
  position: absolute;
  top: 0;
  left: 0;
  will-change: transform;
}

/* ── SVG 连线层 ── */
.tree-svg {
  position: absolute;
  top: 0;
  left: 0;
  pointer-events: none;
  overflow: visible;
}

/* ── 节点卡片层 ── */
.tree-canvas {
  position: relative;
}

/* ── 节点卡片 ── */
.ncard {
  position: absolute;
  width: v-bind('NW + "px"');
  height: v-bind('NH + "px"');
  border-radius: 8px;
  border: 1px solid var(--border);
  padding: 7px 10px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  transition: border-color 0.2s, background 0.2s, box-shadow 0.2s;
  cursor: default;
  background: var(--surface);
  pointer-events: auto;
}

.ncard:hover {
  transform: scale(1.06);
  z-index: 10;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.5);
}

.ncard.RUNNING {
  background: rgba(79, 158, 255, 0.09);
  border-color: #4f9eff;
  box-shadow: 0 0 10px rgba(79, 158, 255, 0.2), inset 0 0 16px rgba(79, 158, 255, 0.04);
}

.ncard.SUCCESS {
  background: rgba(0, 224, 122, 0.07);
  border-color: #00e07a;
}

.ncard.FAILURE {
  background: rgba(255, 64, 102, 0.07);
  border-color: #ff4066;
}

.ncard.INVALID {
  background: var(--surface);
  border-color: var(--border);
}

.ncard-head {
  display: flex;
  align-items: center;
  gap: 6px;
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
  background: var(--text-dim);
  transition: background 0.2s;
}

.RUNNING .status-dot {
  background: #4f9eff;
  animation: pulse-dot 1.5s ease-in-out infinite;
}
.SUCCESS .status-dot { background: #00e07a; }
.FAILURE .status-dot { background: #ff4066; }
.INVALID .status-dot { background: var(--border); }

@keyframes pulse-dot {
  0%, 100% { box-shadow: 0 0 0 0 rgba(79, 158, 255, 0.6); }
  50%       { box-shadow: 0 0 0 5px rgba(79, 158, 255, 0); }
}

.ncard-name {
  font-size: 12px;
  font-weight: 600;
  font-family: var(--font-mono);
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
}

.ncard-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.ncard-type {
  font-size: 10px;
  color: var(--text-dim);
  font-family: var(--font-mono);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 80px;
}

.ncard-badge {
  font-size: 9px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 2px 5px;
  border-radius: 3px;
  font-family: var(--font-mono);
  flex-shrink: 0;
}

.RUNNING .ncard-badge { background: rgba(79,158,255,.18); color: #4f9eff; }
.SUCCESS .ncard-badge { background: rgba(0,224,122,.15);  color: #00e07a; }
.FAILURE .ncard-badge { background: rgba(255,64,102,.15); color: #ff4066; }
.INVALID .ncard-badge { background: rgba(94,122,146,.12); color: var(--text-dim); }
</style>
