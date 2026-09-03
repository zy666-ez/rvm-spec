<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  mode: { type: String, default: 'real' },
  blur: { type: Boolean, default: false },
  bg: { type: String, default: null },
  recording: { type: Boolean, default: false },
  count: { type: Number, default: 0 },
  max: { type: Number, default: 100 },
  zoom: { type: Number, default: 1.0 },
})
const emit = defineEmits(['zoomIn', 'zoomOut'])

const streamSrc = '/video_feed'
const showPlaceholder = ref(true)

function onStreamLoad() {
  showPlaceholder.value = false
}

function onStreamError() {
  showPlaceholder.value = false
}

const zoomText = computed(() => Math.round((props.zoom || 1) * 100) + '%')
const modeText = computed(() => (props.mode === 'virtual' ? 'Virtual' : 'Real'))
const blurText = computed(() => (props.blur ? 'ON' : 'OFF'))
const recText = computed(() => `Recording: ${props.count}/${props.max}`)

function onWheel(e) {
  e.preventDefault()
  if (e.deltaY < 0) emit('zoomIn')
  else emit('zoomOut')
}
</script>

<template>
  <div class="video-wrap" @wheel="onWheel">
    <img
      :src="streamSrc"
      alt="Live stream"
      @load="onStreamLoad"
      @error="onStreamError"
    />
    <div v-if="showPlaceholder" class="placeholder">
      <p>正在连接摄像头...</p>
    </div>
    <div class="zoom-indicator">{{ zoomText }}</div>
  </div>

  <div class="status-bar">
    <span><span class="dot live"></span> LIVE</span>
    <span>Mode: {{ modeText }}</span>
    <span>Blur: {{ blurText }}</span>
    <span>BG: {{ bg || 'None' }}</span>
    <span v-if="recording" class="rec">{{ recText }}</span>
  </div>
</template>

<style scoped>
.video-wrap {
  flex: 1;
  position: relative;
  background: #d0d3d8;
  overflow: hidden;
  min-height: 0;
}
.video-wrap img {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  max-width: 100%;
  max-height: 100%;
  width: auto;
  height: auto;
  object-fit: contain;
  display: block;
}
.placeholder {
  position: absolute;
  color: #999;
  text-align: center;
  width: 100%;
  top: 50%;
  transform: translateY(-50%);
}
.zoom-indicator {
  position: absolute;
  bottom: 12px;
  right: 12px;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  padding: 4px 10px;
  border-radius: 12px;
  font-size: 0.75em;
  pointer-events: none;
  z-index: 5;
}
.status-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 8px 16px;
  background: #fff;
  font-size: 0.8em;
  color: var(--text-light);
  border-top: 1px solid var(--border);
  flex-wrap: wrap;
}
.dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 4px;
}
.dot.live {
  background: #4caf50;
  animation: pulse 1.5s infinite;
}
.rec {
  color: #f5a623;
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
</style>
