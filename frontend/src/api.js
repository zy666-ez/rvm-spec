// 前端 API 客户端。所有路径均为相对路径：
// 开发时由 Vite 代理转发到后端（8000）；生产时由后端同源托管。
async function request(url, options) {
  const res = await fetch(url, options)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export const api = {
  getState: () => request('/api/state'),

  setMode: (mode) =>
    request('/api/mode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode }),
    }),

  toggleBlur: (enable) =>
    request('/api/blur', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enable }),
    }),

  setZoom: (level) =>
    request('/api/zoom', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ level }),
    }),

  selectBackground: (filename) =>
    request(`/api/background/${encodeURIComponent(filename)}`, { method: 'POST' }),

  listBackgrounds: () => request('/api/backgrounds'),

  startRecord: () => request('/api/record', { method: 'POST' }),
}
