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
        :class="{ dragging: isDragging }"
        @wheel.prevent="onWheel"
        @mousedown="onMouseDown"
        :style="{ cursor: isDragging ? 'grabbing' : 'grab' }"
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
              :stroke-width="1.5 * scale"
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
              :style="{
                left: item.x + 'px',
                top: item.y + 'px',
                width: layoutDims.nw + 'px',
                height: layoutDims.nh + 'px',
              }"
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
import { ref, computed, watch, nextTick, onUnmounted } from 'vue'

const props = defineProps({
  tree: { type: Object, default: null },
})

// ── 节点卡片基准尺寸（zoom=1）；缩放改布局尺寸而非 CSS scale，避免放大发糊 ──
const NW_BASE = 132
const NH_BASE = 58
const GX_BASE = 10
const GY_BASE = 72
const PAD_BASE = 24

// ── 缩放/拖拽状态 ───────────────────────────────────────
const wrapRef = ref(null)
const scale = ref(1)
const tx = ref(0)
const ty = ref(0)

const SCALE_MIN = 0.08
const SCALE_MAX = 5
const SCALE_STEP = 0.12

const isDragging = ref(false)
let dragStartX = 0
let dragStartY = 0
let dragStartTx = 0
let dragStartTy = 0
let lastStructureKey = ''

const layoutDims = computed(() => {
  const z = scale.value
  return {
    nw: NW_BASE * z,
    nh: NH_BASE * z,
    gx: GX_BASE * z,
    gy: GY_BASE * z,
    pad: PAD_BASE * z,
  }
})

// 仅平移；缩放由布局尺寸承担，文字/SVG 始终以真实像素渲染
const transformStyle = computed(() => ({
  transform: `translate(${tx.value}px, ${ty.value}px)`,
  '--z': String(scale.value),
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
  // 滚轮/触控板：按 delta 连续缩放，Ctrl+滚轮同样生效
  const factor = Math.exp(-e.deltaY * 0.002)
  zoomAt(e.clientX, e.clientY, factor)
}

function onDocumentMouseMove(e) {
  if (!isDragging.value) return
  tx.value = dragStartTx + (e.clientX - dragStartX)
  ty.value = dragStartTy + (e.clientY - dragStartY)
}

function endDrag() {
  if (!isDragging.value) return
  isDragging.value = false
  window.removeEventListener('mousemove', onDocumentMouseMove)
  window.removeEventListener('mouseup', endDrag)
}

function onMouseDown(e) {
  if (e.button !== 0) return
  e.preventDefault()
  isDragging.value = true
  dragStartX = e.clientX
  dragStartY = e.clientY
  dragStartTx = tx.value
  dragStartTy = ty.value
  window.addEventListener('mousemove', onDocumentMouseMove)
  window.addEventListener('mouseup', endDrag)
}

onUnmounted(endDrag)

function treeStructureKey(node) {
  if (!node) return ''
  const kids = (node.children || []).map(treeStructureKey).join('|')
  return `${node.id}:${kids}`
}

function zoomIn()  { zoomAt(wrapRef.value ? wrapRef.value.clientWidth/2 : 0, wrapRef.value ? wrapRef.value.clientHeight/2 : 0, 1 + SCALE_STEP * 2) }
function zoomOut() { zoomAt(wrapRef.value ? wrapRef.value.clientWidth/2 : 0, wrapRef.value ? wrapRef.value.clientHeight/2 : 0, 1 - SCALE_STEP * 2) }

// 自动将整棵树缩放居中到视口
// 策略：优先高度适配，宽度超出时允许横向平移；最小缩放 35%
function fitToView() {
  const wrap = wrapRef.value
  if (!wrap || !layout.value.length) return
  const vw = wrap.clientWidth
  const vh = wrap.clientHeight
  const z = scale.value || 1
  const baseW = canvasW.value / z
  const baseH = canvasH.value / z

  const scaleByW = (vw * 0.92) / baseW
  const scaleByH = (vh * 0.88) / baseH
  const fitted = Math.min(scaleByW, scaleByH)
  const newScale = clampScale(Math.max(fitted, 0.35))

  scale.value = newScale
  tx.value = Math.max(16, (vw - baseW * newScale) / 2)
  ty.value = Math.max(20, (vh - baseH * newScale) / 2)
}

function resetView() {
  fitToView()
}

// 仅在首次加载或树拓扑变化时自动适配，避免 tick 状态刷新重置用户缩放/平移
watch(() => props.tree, async (newTree, oldTree) => {
  if (!newTree) {
    lastStructureKey = ''
    return
  }
  const key = treeStructureKey(newTree)
  if (!oldTree || key !== lastStructureKey) {
    lastStructureKey = key
    await nextTick()
    fitToView()
  }
}, { flush: 'post' })

// ── 布局算法 ─────────────────────────────────────────────

function leafCount(node) {
  if (!node.children?.length) return 1
  return node.children.reduce((s, c) => s + leafCount(c), 0)
}

function buildLayout(node, depth, offsetX, out, dims) {
  const { nw, nh, gx, gy, pad } = dims
  const lc = leafCount(node)
  const span = lc * (nw + gx) - gx
  const x = offsetX + (span - nw) / 2
  const y = pad + depth * (nh + gy)
  const item = { node, x, y }
  out.push(item)
  if (node.children?.length) {
    let cx = offsetX
    for (const child of node.children) {
      buildLayout(child, depth + 1, cx, out, dims)
      cx += leafCount(child) * (nw + gx)
    }
  }
  return item
}

function buildEdges(root, layoutMap, dims) {
  const { nw, nh } = dims
  const result = []
  function walk(node) {
    if (!node.children) return
    for (const child of node.children) {
      const p = layoutMap[node.id]
      const c = layoutMap[child.id]
      if (p && c) {
        result.push({
          x1: p.x + nw / 2, y1: p.y + nh,
          x2: c.x + nw / 2, y2: c.y,
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
  const dims = layoutDims.value
  const out = []
  buildLayout(props.tree, 0, dims.pad, out, dims)
  return out
})

const layoutMap = computed(() => {
  const m = {}
  layout.value.forEach(item => { m[item.node.id] = item })
  return m
})

const edges = computed(() => {
  if (!props.tree) return []
  return buildEdges(props.tree, layoutMap.value, layoutDims.value)
})

const canvasW = computed(() => {
  if (!layout.value.length) return 600
  const { nw, pad } = layoutDims.value
  return Math.max(...layout.value.map(i => i.x)) + nw + pad * 2
})

const canvasH = computed(() => {
  if (!layout.value.length) return 400
  const { nh, pad } = layoutDims.value
  return Math.max(...layout.value.map(i => i.y)) + nh + pad * 2
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
  const cpOffset = layoutDims.value.gy * 0.5
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
  touch-action: none;
}

.pan-layer.dragging .ncard {
  pointer-events: none;
}

/* ── 变换层（仅平移；缩放由 --z 驱动真实布局尺寸）── */
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
  box-sizing: border-box;
  border-radius: calc(8px * var(--z, 1));
  border: calc(1px * var(--z, 1)) solid var(--border);
  padding: calc(7px * var(--z, 1)) calc(10px * var(--z, 1));
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
  gap: calc(6px * var(--z, 1));
}

.status-dot {
  width: calc(7px * var(--z, 1));
  height: calc(7px * var(--z, 1));
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
  font-size: calc(12px * var(--z, 1));
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
  font-size: calc(10px * var(--z, 1));
  color: var(--text-dim);
  font-family: var(--font-mono);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: calc(88px * var(--z, 1));
}

.ncard-badge {
  font-size: calc(9px * var(--z, 1));
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: calc(2px * var(--z, 1)) calc(5px * var(--z, 1));
  border-radius: calc(3px * var(--z, 1));
  font-family: var(--font-mono);
  flex-shrink: 0;
}

.RUNNING .ncard-badge { background: rgba(79,158,255,.18); color: #4f9eff; }
.SUCCESS .ncard-badge { background: rgba(0,224,122,.15);  color: #00e07a; }
.FAILURE .ncard-badge { background: rgba(255,64,102,.15); color: #ff4066; }
.INVALID .ncard-badge { background: rgba(94,122,146,.12); color: var(--text-dim); }
</style>
