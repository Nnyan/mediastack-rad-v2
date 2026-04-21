<template>
  <div>
    <h1 class="page-title">
      Containers
      <span class="sub">{{ filtered.length }} shown · {{ containers.length }} total</span>
    </h1>

    <div class="card flex items-center gap-3 mb-3">
      <input
        v-model="search"
        class="mono"
        placeholder="filter by name or image…"
        style="max-width: 340px"
      />
      <label class="flex items-center gap-2 small muted nowrap">
        <input type="checkbox" v-model="showStopped" style="width: auto" />
        show stopped
      </label>
      <div class="ml-auto flex gap-2" v-if="selected.size > 0">
        <span class="small muted">{{ selected.size }} selected</span>
        <button @click="bulk('start')">Start</button>
        <button @click="bulk('stop')">Stop</button>
        <button @click="bulk('restart')">Restart</button>
        <button class="danger" @click="bulk('remove')">Remove</button>
      </div>
    </div>

    <div class="grid">
      <div
        v-for="c in filtered"
        :key="c.id"
        class="card"
        :class="{ selected: selected.has(c.name) }"
        @click.self="toggleSelect(c.name); confirmRemove = null"
      >
        <div class="card-header">
          <label class="card-select" style="cursor: pointer">
            <input
              type="checkbox"
              :checked="selected.has(c.name)"
              @change="toggleSelect(c.name)"
              style="width: auto; flex-shrink: 0"
            />
          </label>
          <div class="app-identity">
            <div class="app-name-row">
              <div class="status-dot-wrap" :title="statusLabel(c)">
                <span class="status-dot" :class="statusDotClass(c)"></span>
                <span v-if="statusIsAnimated(c)" class="status-ping" :class="statusDotClass(c)"></span>
              </div>
              <span class="app-name">{{ formatName(c.name) }}</span>
              <span v-if="c.health === 'unhealthy'" class="health-badge err">unhealthy</span>
              <span v-if="c.health === 'starting'" class="health-badge warn">starting</span>
            </div>
            <div class="app-image truncate">{{ c.image.split('/').pop().split(':')[0] }}</div>
          </div>
        </div>

        <div class="stats-row" v-if="stats[c.id]">
          <div class="stat">
            <div class="stat-label">CPU</div>
            <div class="stat-value" :class="{ hot: stats[c.id].cpu_percent > 80 }">
              {{ stats[c.id].cpu_percent.toFixed(1) }}%
            </div>
            <div class="stat-bar">
              <div class="stat-bar-fill" :style="{ width: Math.min(stats[c.id].cpu_percent, 100) + '%', background: stats[c.id].cpu_percent > 80 ? 'var(--err)' : 'var(--accent)' }"></div>
            </div>
          </div>
          <div class="stat">
            <div class="stat-label">MEM</div>
            <div class="stat-value">
              {{ mb(stats[c.id].mem_usage_bytes) }}<span class="muted tiny">M</span>
              <span class="muted tiny"> / {{ mb(stats[c.id].mem_limit_bytes) }}M</span>
            </div>
            <div class="stat-bar">
              <div class="stat-bar-fill" :style="{ width: Math.min(stats[c.id].mem_percent, 100) + '%', background: stats[c.id].mem_percent > 85 ? 'var(--err)' : 'var(--info, #4fb2d9)' }"></div>
            </div>
          </div>
          <div class="stat">
            <div class="stat-label">NET</div>
            <div class="stat-value">
              <span class="muted tiny">↓</span>{{ humanBytes(stats[c.id].net_rx_bytes) }}
              <span class="muted tiny"> ↑</span>{{ humanBytes(stats[c.id].net_tx_bytes) }}
            </div>
          </div>
        </div>
        <div v-else-if="c.status === 'running'" class="stats-loading mono muted tiny">
          collecting stats…
        </div>
        <div v-else class="small muted mono">{{ c.status }}</div>

        <!-- Ports -->
        <div class="ports mono" v-if="c.ports && c.ports.length">
          <span v-for="(p, i) in c.ports.filter(p => p.host_port)" :key="i" class="port">
            {{ p.host_port }}:{{ p.container_port }}
          </span>
        </div>

        <!-- Action buttons -->
        <div class="card-footer">
          <div class="card-actions">
            <button
              v-if="c.status !== 'running'"
              class="act-btn act-start"
              @click.stop="action(c.name, 'start')"
              title="Start"
            >▶</button>
            <button
              v-else
              class="act-btn act-stop"
              @click.stop="action(c.name, 'stop')"
              title="Stop"
            >⏸</button>
            <button
              class="act-btn act-restart"
              @click.stop="action(c.name, 'restart')"
              title="Restart"
            >↺</button>
            <button
              class="act-btn act-logs"
              @click.stop="showLogs(c.name)"
              title="View logs"
            >≡</button>
            <a
              v-if="webUiUrls[c.id]"
              :href="webUiUrls[c.id]"
              target="_blank"
              class="act-btn act-open"
              @click.stop
              title="Open app"
            >↗</a>
          </div>

          <!-- Remove — two-step inline confirm -->
          <div class="remove-area">
            <template v-if="confirmRemove !== c.name">
              <button
                class="act-btn act-remove"
                @click.stop="confirmRemove = c.name"
                title="Remove container"
              >✕</button>
            </template>
            <template v-else>
              <span class="remove-confirm-label">Remove?</span>
              <button
                class="act-btn act-remove-confirm"
                @click.stop="doRemove(c.name)"
              >Yes</button>
              <button
                class="act-btn act-cancel"
                @click.stop="confirmRemove = null"
              >No</button>
            </template>
          </div>
        </div>
      </div>
    </div>

    <div v-if="logsOpen" class="log-modal" @click.self="logsOpen = false">
      <div class="log-panel">
        <div class="flex items-center justify-between mb-2">
          <strong class="mono">{{ logsName }} — last 300 lines</strong>
          <button @click="logsOpen = false">close</button>
        </div>
        <pre class="logs mono">{{ logs }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, inject } from 'vue'

const showToast = inject('showToast')

const containers = ref([])
const stats = ref({})
const search = ref('')
const showStopped = ref(true)
const selected = ref(new Set())

const logsOpen = ref(false)
const logsName = ref('')
const logs = ref('')
const confirmRemove = ref(null)  // container name pending remove confirmation

let pollTimer = null
let ws = null
let wsActive = false  // guard: stop reconnecting after unmount

// Precompute web UI URLs once per containers update — avoids calling
// webUiUrl(c) twice per render (v-if + :href both called it).
const webUiUrls = computed(() => {
  const map = {}
  for (const c of containers.value) map[c.id] = webUiUrl(c)
  return map
})

const filtered = computed(() => {
  const q = search.value.toLowerCase()
  return containers.value
    .filter(c => showStopped.value || c.status === 'running')
    .filter(c =>
      !q ||
      c.name.toLowerCase().includes(q) ||
      c.image.toLowerCase().includes(q)
    )
    .sort((a, b) => {
      // Running first, then by name
      if (a.status === 'running' && b.status !== 'running') return -1
      if (a.status !== 'running' && b.status === 'running') return 1
      return a.name.localeCompare(b.name)
    })
})

async function refresh() {
  try {
    const r = await fetch('/api/containers').then(r => r.json())
    containers.value = r
  } catch (e) {
    console.error(e)
  }
}

// Compute dot class from both status + health
function statusDotClass(c) {
  if (c.health === 'unhealthy') return 'dot-err'
  if (c.state === 'restarting') return 'dot-warn'
  if (c.state === 'paused')     return 'dot-warn'
  if (c.state === 'dead')       return 'dot-err'
  if (c.state === 'running')    return 'dot-ok'
  return 'dot-off'
}

// True if the dot should pulse (active transition states)
function statusIsAnimated(c) {
  return c.state === 'restarting' || c.health === 'starting'
}

// Human-readable tooltip for the dot
function statusLabel(c) {
  if (c.health === 'unhealthy') return 'Unhealthy'
  if (c.health === 'starting')  return 'Health check starting'
  if (c.state === 'restarting') return 'Restarting'
  if (c.state === 'paused')     return 'Paused'
  if (c.state === 'dead')       return 'Dead'
  if (c.state === 'running')    return 'Running'
  return c.status
}

// Format container name: remove leading slash, title-case words separated by _ or -
function formatName(name) {
  return name.replace(/^\//, '')
}

function mb(bytes) {
  if (!bytes) return '0'
  return (bytes / 1024 / 1024).toFixed(0)
}

function humanBytes(bytes) {
  if (!bytes || bytes < 1024) return '0B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + 'K'
  if (bytes < 1024 * 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + 'M'
  return (bytes / 1024 / 1024 / 1024).toFixed(2) + 'G'
}

function webUiUrl(c) {
  // Heuristic: if the container has a published web port, give the
  // user a direct link. Covers the 80/443/typical *arr ports.
  const webPorts = [80, 443, 3000, 5055, 5000, 6767, 6789, 7878, 8080, 8081,
                    8085, 8096, 8686, 8787, 8989, 9696, 32400]
  const port = (c.ports || []).find(
    p => p.host_port && webPorts.includes(p.container_port)
  )
  if (!port) return null
  const host = window.location.hostname
  const scheme = port.container_port === 443 ? 'https' : 'http'
  let path = ''
  if (c.name === 'plex') path = '/web'
  if (c.name === 'traefik') path = '/dashboard/'
  return `${scheme}://${host}:${port.host_port}${path}`
}

function toggleSelect(name) {
  if (selected.value.has(name)) {
    selected.value.delete(name)
  } else {
    selected.value.add(name)
  }
  // Force reactivity — Set mutations don't trigger Vue by themselves.
  selected.value = new Set(selected.value)
}

async function action(name, kind) {
  const url = `/api/containers/${name}/${kind}`
  const method = kind === 'remove' ? 'DELETE' : 'POST'
  try {
    const r = await fetch(url, { method })
    if (r.ok) {
      showToast(`${kind} ${name} → ok`)
      refresh()
    } else {
      const t = await r.text()
      showToast(`${kind} ${name} failed: ${t}`, 'err')
    }
  } catch (e) {
    showToast(`${kind} ${name} failed: ${e}`, 'err')
  }
}

async function doRemove(name) {
  confirmRemove.value = null
  const container = containers.value.find(c => c.name === name)
  try {
    // If running, stop first then remove
    if (container?.status === 'running') {
      showToast(`Stopping ${name}…`, 'warn', 2000)
      const stopRes = await fetch(`/api/containers/${name}/stop`, { method: 'POST' })
      if (!stopRes.ok) {
        showToast(`Could not stop ${name} — remove cancelled`, 'err')
        return
      }
      // Brief pause so Docker registers the stop
      await new Promise(r => setTimeout(r, 800))
    }

    const r = await fetch(`/api/containers/${name}`, { method: 'DELETE' })
    if (r.ok) {
      showToast(`${name} removed`)
      refresh()
    } else {
      const t = await r.text()
      showToast(`Remove failed: ${t}`, 'err')
    }
  } catch (e) {
    showToast(`Remove error: ${e.message}`, 'err')
  }
}

async function bulk(kind) {
  const names = [...selected.value]
  if (kind === 'remove') {
    // doRemove handles stop-first logic and uses the correct DELETE endpoint
    for (const n of names) await doRemove(n)
  } else {
    for (const n of names) await action(n, kind)
  }
  selected.value = new Set()
}

async function showLogs(name) {
  logsName.value = name
  logs.value = 'Loading…'
  logsOpen.value = true
  try {
    const r = await fetch(`/api/containers/${name}/logs?tail=300`, {
      method: 'POST'
    })
    logs.value = await r.text()
  } catch (e) {
    logs.value = String(e)
  }
}

function openWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  ws = new WebSocket(`${protocol}//${window.location.host}/ws/stats`)
  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data)
    if (msg.type === 'stats') {
      const next = {}
      for (const row of msg.containers) {
        next[row.id] = row
      }
      stats.value = next
    }
  }
  ws.onclose = () => {
    // Only reconnect while the component is still mounted.
    // Without this guard, onUnmounted's ws.close() triggers a reconnect
    // that leaks a WebSocket after the component is gone.
    if (wsActive) setTimeout(openWebSocket, 2000)
  }
}

onMounted(() => {
  wsActive = true
  refresh()
  openWebSocket()
  pollTimer = setInterval(refresh, 10000)
})
onUnmounted(() => {
  wsActive = false  // prevent ws.onclose from reconnecting
  if (pollTimer) clearInterval(pollTimer)
  if (ws) ws.close()
})
</script>

<style scoped>
.card {
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.card:hover { border-color: var(--border-strong); box-shadow: var(--shadow-2); }
.card.selected { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-dim); }

/* Card header */
.card-header {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
}
.card-select {
  display: flex;
  align-items: center;
  padding-top: 3px;
  flex-shrink: 0;
}
.app-identity {
  flex: 1;
  min-width: 0;
}
.app-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 3px;
  flex-wrap: wrap;
}
.app-name {
  font-size: 15px;
  font-weight: 700;
  color: var(--fg-0);
  letter-spacing: -0.01em;
  line-height: 1.2;
  word-break: break-word;
}
.app-image {
  font-family: var(--font-mono);
  font-size: 10.5px;
  color: var(--fg-2);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Status dot with ping animation */
.status-dot-wrap {
  position: relative;
  width: 10px;
  height: 10px;
  flex-shrink: 0;
}
.status-dot {
  display: block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  position: relative;
  z-index: 1;
}
.status-ping {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  animation: ping 1.4s cubic-bezier(0,0,0.2,1) infinite;
  opacity: 0.5;
}
@keyframes ping {
  0%   { transform: scale(1); opacity: 0.5; }
  75%, 100% { transform: scale(2.2); opacity: 0; }
}

/* Dot colors */
.dot-ok  { background: var(--ok);   box-shadow: 0 0 6px var(--ok); }
.dot-warn { background: var(--warn); box-shadow: 0 0 5px var(--warn); }
.dot-err  { background: var(--err);  box-shadow: 0 0 5px var(--err); }
.dot-off  { background: var(--fg-2); }
.status-ping.dot-ok   { background: var(--ok); }
.status-ping.dot-warn { background: var(--warn); }
.status-ping.dot-err  { background: var(--err); }

/* Health badges */
.health-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 1px 7px;
  border-radius: 20px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  flex-shrink: 0;
}
.health-badge.err  { background: var(--err-bg);  color: var(--err);  border: 1px solid var(--err-dim); }
.health-badge.warn { background: var(--warn-bg); color: var(--warn); border: 1px solid rgba(217,119,6,0.2); }

.stats-row {
  display: grid;
  grid-template-columns: 1fr 1.3fr 1.5fr;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
}
.stat-label {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--fg-2);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.stat-value {
  font-family: var(--font-mono);
  font-size: 13px;
  margin-bottom: 3px;
}
.stat-value.hot { color: var(--err); }
.stat-bar {
  height: 2px;
  background: var(--bg-3);
  border-radius: 2px;
  overflow: hidden;
}
.stat-bar-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 1s ease-out;
}
.stats-loading {
  margin-bottom: var(--space-2);
  animation: pulse 1.5s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 0.5; }
  50% { opacity: 1; }
}

.ports {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: var(--space-2);
}
.port {
  font-family: var(--font-mono);
  font-size: 10.5px;
  color: var(--fg-2);
  background: var(--bg-2);
  border: 1px solid var(--border);
  padding: 1px 6px;
  border-radius: 4px;
}

/* Card footer: actions left, remove right */
.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: var(--space-2);
  border-top: 1px solid var(--border);
  margin-top: var(--space-2);
  gap: var(--space-2);
}
.card-actions {
  display: flex;
  gap: 4px;
  align-items: center;
}

/* Compact icon buttons */
.act-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border-radius: 6px;
  font-size: 13px;
  font-family: var(--font-mono);
  border: 1.5px solid var(--border);
  background: var(--bg-1);
  color: var(--fg-1);
  cursor: pointer;
  transition: all 0.15s;
  text-decoration: none;
  flex-shrink: 0;
}
.act-btn:hover { border-color: var(--border-strong); background: var(--bg-2); color: var(--fg-0); }

/* Per-button accent colors on hover */
.act-start:hover  { border-color: var(--ok);   color: var(--ok);   background: var(--ok-bg); }
.act-stop:hover   { border-color: var(--warn);  color: var(--warn); background: var(--warn-bg); }
.act-restart:hover { border-color: var(--blue);  color: var(--blue); background: color-mix(in srgb, var(--blue) 8%, var(--bg-1)); }
.act-logs:hover   { border-color: var(--purple); color: var(--purple); background: var(--accent-dim); }
.act-open:hover   { border-color: var(--teal);  color: var(--teal); background: color-mix(in srgb, var(--teal) 8%, var(--bg-1)); }

/* Remove — right side, muted until confirm */
.remove-area {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}
.act-remove {
  font-size: 11px;
  color: var(--fg-2);
  border-color: transparent;
  background: transparent;
}
.act-remove:hover {
  border-color: var(--err-dim);
  color: var(--err);
  background: var(--err-bg);
}

/* Inline confirm state */
.remove-confirm-label {
  font-size: 11.5px;
  color: var(--err);
  font-weight: 600;
  white-space: nowrap;
}
.act-remove-confirm {
  width: auto;
  padding: 0 8px;
  font-size: 11.5px;
  font-family: var(--font-sans);
  font-weight: 600;
  background: var(--err-bg);
  border-color: var(--err);
  color: var(--err);
}
.act-remove-confirm:hover {
  background: var(--err);
  color: #fff;
  border-color: var(--err);
}
.act-cancel {
  width: auto;
  padding: 0 8px;
  font-size: 11.5px;
  font-family: var(--font-sans);
}

.log-modal {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 500;
}
.log-panel {
  background: var(--bg-0);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius);
  padding: var(--space-4);
  width: 90vw;
  max-width: 1000px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
}
.logs {
  flex: 1;
  overflow: auto;
  background: var(--bg-1);
  padding: var(--space-3);
  border-radius: var(--radius);
  font-size: 12px;
  line-height: 1.4;
  white-space: pre;
}

/* btn-open replaced by act-btn act-open */
</style>
