import { reactive, onMounted, onUnmounted } from 'vue'
import { api } from '../api.js'

// 集中管理：与后端交互的状态 + 动作 + 轮询 + 键盘快捷键。
export function usePipeline() {
  const state = reactive({
    current_mode: 'real',
    blur_enabled: false,
    current_bg_name: null,
    is_recording: false,
    record_count: 0,
    record_max: 100,
    bg_list: [],
    metrics_result: null,
    zoom_level: 1.0,
  })

  const ZOOM_MIN = 0.5
  const ZOOM_MAX = 3.0
  const ZOOM_STEP = 0.1
  let bgIndex = -1
  let pollTimer = null

  async function poll() {
    try {
      const s = await api.getState()
      state.current_mode = s.current_mode
      state.blur_enabled = s.blur_enabled
      state.current_bg_name = s.current_bg_name
      state.is_recording = s.is_recording
      state.record_count = s.record_count
      state.record_max = s.record_max
      state.bg_list = s.bg_list || []
      state.metrics_result = s.metrics_result
      if (s.zoom_level !== undefined) state.zoom_level = s.zoom_level
    } catch (e) {
      /* 网络抖动时忽略，下一轮继续 */
    }
  }

  async function selectBg(filename) {
    const data = await api.selectBackground(filename)
    if (data.ok) {
      state.current_bg_name = filename
      state.current_mode = 'virtual'
    }
  }

  async function bgNext() {
    if (!state.bg_list.length) return
    bgIndex = (bgIndex + 1) % state.bg_list.length
    await selectBg(state.bg_list[bgIndex])
  }

  async function bgPrev() {
    if (!state.bg_list.length) return
    bgIndex = (bgIndex - 1 + state.bg_list.length) % state.bg_list.length
    await selectBg(state.bg_list[bgIndex])
  }

  async function setMode(mode) {
    // 切到虚拟背景但还没选过背景时，自动加载第一个
    if (mode === 'virtual' && !state.current_bg_name && state.bg_list.length) {
      bgIndex = 0
      await selectBg(state.bg_list[0])
      return
    }
    await api.setMode(mode)
    state.current_mode = mode
    if (mode === 'real') state.current_bg_name = null
  }

  async function toggleBlur() {
    const data = await api.toggleBlur()
    state.blur_enabled = data.blur_enabled
  }

  async function setZoom(level) {
    const z = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, level))
    await api.setZoom(z)
    state.zoom_level = z
  }

  const zoomIn = () => setZoom(state.zoom_level + ZOOM_STEP)
  const zoomOut = () => setZoom(state.zoom_level - ZOOM_STEP)
  const zoomReset = () => setZoom(1.0)

  async function record() {
    await api.startRecord()
  }

  function onKey(e) {
    const t = e.target.tagName
    if (t === 'INPUT' || t === 'TEXTAREA') return
    switch (e.key.toLowerCase()) {
      case 'n': setMode('real'); break
      case 'v': toggleBlur(); break
      case 'w': bgNext(); break
      case 's': bgPrev(); break
      case 'r': if (!state.is_recording) record(); break
      case '+': case '=': zoomIn(); break
      case '-': zoomOut(); break
      case '0': zoomReset(); break
    }
  }

  onMounted(async () => {
    try {
      const list = await api.listBackgrounds()
      state.bg_list = list || []
    } catch (e) {
      /* ignore */
    }
    if (state.bg_list.length) {
      bgIndex = 0
      try { await selectBg(state.bg_list[0]) } catch (e) { /* ignore */ }
    }
    pollTimer = setInterval(poll, 500)
    window.addEventListener('keydown', onKey)
  })

  onUnmounted(() => {
    if (pollTimer) clearInterval(pollTimer)
    window.removeEventListener('keydown', onKey)
  })

  return {
    state,
    bgNext,
    bgPrev,
    selectBg,
    setMode,
    toggleBlur,
    zoomIn,
    zoomOut,
    zoomReset,
    record,
    ZOOM_MIN,
    ZOOM_MAX,
  }
}
