<script setup>
defineProps({
  bgList: { type: Array, default: () => [] },
  current: { type: String, default: null },
})
const emit = defineEmits(['select'])

function onImgError(e) {
  e.target.style.background = '#eee'
  e.target.style.minHeight = '80px'
}
</script>

<template>
  <aside class="sidebar">
    <h2>背景素材</h2>
    <div class="hint">点击缩略图切换背景 | W/S 键也可切换</div>

    <div class="bg-grid">
      <div
        v-for="bg in bgList"
        :key="bg"
        class="bg-card"
        :class="{ active: bg === current }"
        @click="emit('select', bg)"
      >
        <img
          :src="`/api/thumb/${encodeURIComponent(bg)}`"
          :alt="bg"
          @error="onImgError"
        />
        <div class="label">{{ bg }}</div>
      </div>

      <div v-if="!bgList.length" class="empty">
        背景文件夹为空<br />请放入图片或视频
      </div>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 260px;
  min-width: 260px;
  background: var(--sidebar-bg);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  padding: 16px;
  gap: 10px;
  box-shadow: var(--shadow);
  z-index: 10;
}
.sidebar h2 {
  font-size: 1.05em;
  color: var(--accent);
  margin-bottom: 2px;
  font-weight: 600;
}
.sidebar .hint {
  font-size: 0.75em;
  color: var(--text-dim);
  margin-bottom: 6px;
  line-height: 1.4;
}
.bg-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.bg-card {
  background: var(--card-bg);
  border: 2px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s, transform 0.15s;
}
.bg-card:hover {
  border-color: var(--accent);
  box-shadow: 0 2px 8px rgba(74, 144, 217, 0.2);
  transform: translateY(-1px);
}
.bg-card.active {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(74, 144, 217, 0.15);
}
.bg-card img {
  width: 100%;
  height: 80px;
  object-fit: cover;
  display: block;
  background: #e8e8e8;
}
.bg-card .label {
  font-size: 0.7em;
  padding: 5px 6px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  text-align: center;
  color: var(--text-light);
  background: #fff;
}
.empty {
  grid-column: span 2;
  color: var(--text-dim);
  font-size: 0.8em;
  text-align: center;
  padding: 20px;
}
</style>
