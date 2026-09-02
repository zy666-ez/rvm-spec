<script setup>
import { usePipeline } from './composables/usePipeline.js'
import BackgroundPanel from './components/BackgroundPanel.vue'
import VideoStage from './components/VideoStage.vue'
import ControlBar from './components/ControlBar.vue'
import MetricsToast from './components/MetricsToast.vue'

const {
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
} = usePipeline()
</script>

<template>
  <div class="app">
    <BackgroundPanel
      :bg-list="state.bg_list"
      :current="state.current_bg_name"
      @select="selectBg"
    />

    <main class="main">
      <VideoStage
        :mode="state.current_mode"
        :blur="state.blur_enabled"
        :bg="state.current_bg_name"
        :recording="state.is_recording"
        :count="state.record_count"
        :max="state.record_max"
        :zoom="state.zoom_level"
        @zoom-in="zoomIn"
        @zoom-out="zoomOut"
      />

      <ControlBar
        :mode="state.current_mode"
        :blur="state.blur_enabled"
        :zoom="state.zoom_level"
        :recording="state.is_recording"
        @mode="setMode"
        @blur="toggleBlur"
        @prev="bgPrev"
        @next="bgNext"
        @zoom-in="zoomIn"
        @zoom-out="zoomOut"
        @zoom-reset="zoomReset"
        @record="record"
      />

      <MetricsToast :result="state.metrics_result" />
    </main>
  </div>
</template>

<style scoped>
.app {
  display: flex;
  height: 100vh;
  overflow: hidden;
}
.main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: #e8eaed;
}
</style>
