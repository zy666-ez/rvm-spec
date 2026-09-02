<script setup>
defineProps({
  mode: { type: String, default: 'real' },
  blur: { type: Boolean, default: false },
  zoom: { type: Number, default: 1.0 },
  recording: { type: Boolean, default: false },
})
const emit = defineEmits([
  'mode',
  'blur',
  'prev',
  'next',
  'zoomIn',
  'zoomOut',
  'zoomReset',
  'record',
])

const zoomText = (z) => Math.round((z || 1) * 100) + '%'
</script>

<template>
  <div class="controls">
    <button @click="emit('mode', 'real')">真实背景 <span class="kbd">N</span></button>
    <button @click="emit('mode', 'virtual')">虚拟背景</button>
    <span class="sep"></span>
    <button @click="emit('blur')">虚化切换 <span class="kbd">V</span></button>
    <span class="sep"></span>
    <button @click="emit('prev')">◀ 上一个 <span class="kbd">S</span></button>
    <button @click="emit('next')">下一个 ▶ <span class="kbd">W</span></button>
    <span class="sep"></span>
    <button @click="emit('zoomOut')" title="缩小">🔍−</button>
    <button class="zoom-reset" @click="emit('zoomReset')">{{ zoomText(zoom) }}</button>
    <button @click="emit('zoomIn')" title="放大">🔍+</button>
    <span class="sep"></span>
    <button class="rec-btn" @click="emit('record')">记录指标 <span class="kbd">R</span></button>
  </div>
</template>

<style scoped>
.controls {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background: #fff;
  border-top: 1px solid var(--border);
  flex-wrap: wrap;
}
.controls button {
  padding: 6px 14px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: #fff;
  color: var(--text);
  cursor: pointer;
  font-size: 0.8em;
  transition: all 0.2s;
}
.controls button:hover {
  background: var(--hover);
  border-color: var(--accent);
  color: var(--accent);
}
.controls button:active {
  background: var(--accent);
  color: #fff;
}
.controls .kbd {
  font-size: 0.65em;
  color: var(--text-dim);
  background: #f0f0f0;
  padding: 1px 5px;
  border-radius: 3px;
  margin-left: 4px;
  border: 1px solid #e0e0e0;
}
.controls .sep {
  width: 1px;
  height: 20px;
  background: var(--border);
  margin: 0 4px;
}
.zoom-reset {
  min-width: 52px;
  text-align: center;
}
.rec-btn {
  border-color: #f5a623;
  color: #f5a623;
}
</style>
