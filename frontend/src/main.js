import { createApp } from 'vue'
import App from './App.vue'
import router from './router.js'
import './assets/main.css'

const API_KEY_KEY = 'rad-api-key'

function getApiKey() {
  return sessionStorage.getItem(API_KEY_KEY) || ''
}

function promptApiKey() {
  const key = prompt('API key required. Enter your RAD API key:')
  if (key) {
    sessionStorage.setItem(API_KEY_KEY, key)
    return key
  }
  return ''
}

const originalFetch = window.fetch
window.fetch = function patchedFetch(input, init = {}) {
  const apiKey = getApiKey()
  if (apiKey) {
    const headers = new Headers(init.headers || {})
    headers.set('Authorization', `Bearer ${apiKey}`)
    init.headers = headers
  }
  return originalFetch(input, init).then(response => {
    if (response.status === 401 && !apiKey) {
      const newKey = promptApiKey()
      if (newKey) {
        const headers = new Headers(init.headers || {})
        headers.set('Authorization', `Bearer ${newKey}`)
        init.headers = headers
        return originalFetch(input, init)
      }
    }
    return response
  })
}

const WS_PROTO = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
const _origWS = window.WebSocket
window.WebSocket = function PatchedWS(url, protocols) {
  const apiKey = getApiKey()
  if (apiKey && url.startsWith(WS_PROTO)) {
    const sep = url.includes('?') ? '&' : '?'
    url = `${url}${sep}token=${encodeURIComponent(apiKey)}`
  }
  return new _origWS(url, protocols)
}
window.WebSocket.prototype = _origWS.prototype
window.WebSocket.CONNECTING = _origWS.CONNECTING
window.WebSocket.OPEN = _origWS.OPEN
window.WebSocket.CLOSING = _origWS.CLOSING
window.WebSocket.CLOSED = _origWS.CLOSED

createApp(App).use(router).mount('#app')
