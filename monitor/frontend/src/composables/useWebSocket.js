import { ref, shallowRef, onUnmounted } from 'vue'

export function useWebSocket() {
  const connected = ref(false)
  const tick = ref(0)
  const fps = ref('—')
  const tree = shallowRef(null)
  const blackboard = ref({})
  const conversation = ref([])
  const metrics = ref({})

  let ws = null
  let reconnectTimer = null
  const fpsSamples = []
  let fpsTimer = null

  function calcFps() {
    const now = Date.now() / 1000
    // 保留2秒内的样本
    while (fpsSamples.length && now - fpsSamples[0] > 2) fpsSamples.shift()
    fps.value = fpsSamples.length > 0
      ? (fpsSamples.length / 2).toFixed(1)
      : '0.0'
  }

  function connect() {
    if (ws) {
      ws.onclose = null
      ws.close()
    }
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    ws = new WebSocket(`${proto}://${location.host}/ws`)

    ws.onopen = () => {
      connected.value = true
    }

    ws.onclose = () => {
      connected.value = false
      reconnectTimer = setTimeout(connect, 2000)
    }

    ws.onerror = () => {
      connected.value = false
    }

    ws.onmessage = (e) => {
      const data = JSON.parse(e.data)
      if (data.ping) return

      fpsSamples.push(Date.now() / 1000)
      tick.value = data.tick ?? tick.value

      if (data.tree) tree.value = data.tree
      if (data.blackboard) blackboard.value = data.blackboard
      if (data.conversation) conversation.value = data.conversation
      if (data.audio || data.timestamp) {
        metrics.value = {
          timestamp: data.timestamp,
          audio: data.audio ?? {},
        }
      }
    }
  }

  fpsTimer = setInterval(calcFps, 1000)
  connect()

  onUnmounted(() => {
    clearInterval(fpsTimer)
    clearTimeout(reconnectTimer)
    if (ws) ws.onclose = null
    ws?.close()
  })

  return { connected, tick, fps, tree, blackboard, conversation, metrics }
}
