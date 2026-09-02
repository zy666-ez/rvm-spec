import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发模式下，把 /api 与 /video_feed 反向代理到 FastAPI 后端（默认 8000 端口），
// 这样前端用相对路径即可，无需处理跨域，MJPEG 视频流也能正常走代理。
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/video_feed': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
