<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  result: { type: Object, default: null },
})

const visible = ref(false)
const content = ref('')
const shownFrames = ref(null)

// 只有出现「新的」统计结果（frames 变化）时才弹窗，避免每次轮询重复弹出
watch(
  () => props.result,
  (r) => {
    if (r && r.frames !== shownFrames.value) {
      shownFrames.value = r.frames
      content.value = `
        <p>帧数: <span style="color:var(--accent);font-weight:bold">${r.frames}</span></p>
        <p>时序边缘方差 (乱跳度): <span style="color:var(--accent);font-weight:bold">${r.mean_temp} ± ${r.std_temp}</span></p>
        <p>拉普拉斯方差 (锋利度): <span style="color:var(--accent);font-weight:bold">${r.mean_lap} ± ${r.std_lap}</span></p>`
      visible.value = true
      setTimeout(() => {
        visible.value = false
      }, 8000)
    }
  }
)
</script>

<template>
  <div class="metrics-toast" :class="{ show: visible }">
    <h4>指标统计完成</h4>
    <div v-html="content"></div>
  </div>
</template>

<style scoped>
.metrics-toast {
  position: fixed;
  top: 20px;
  right: 20px;
  background: #fff;
  border: 1px solid var(--accent);
  border-radius: 8px;
  padding: 14px 18px;
  font-size: 0.85em;
  display: none;
  z-index: 100;
  max-width: 340px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
}
.metrics-toast.show {
  display: block;
}
.metrics-toast h4 {
  color: var(--accent);
  margin-bottom: 6px;
  font-size: 0.95em;
}
</style>
