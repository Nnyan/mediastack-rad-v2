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
        @click.self="toggleSelect(c.name)"
      >
        <div class="flex items-center justify-between mb-2">
          <label class="flex items-center gap-2" style="cursor: pointer">
            <input
              type="checkbox"
              :checked="selected.has(c.name)"
              @change="toggleSelect(c.name)"
              style="width: auto"
            />
            <span class="dot" :class="statusClass(c.status)"></span>
            <strong class="mono">{{ c.name }}</strong>
          </label>
          <a
            v-if="webUiUrl(c)"
            :href="webUiUrl(c)"
            target="_blank"
            class="small"
            @click.stop
          >open ↗</a>
        </div>

        <div class="mono small muted truncate mb-2">{{ c.image }}</div>

        <div class="stats-row" v-if="stats[c.id]">
          <div class="stat">
            <div class="stat-label">CPU</div>
            <div class="stat-value">{{ stats[c.id].cpu_percent.toFixed(1) }}%</div>
          </div>
          <div class="stat">
            <div class="stat-label">MEM</div>
            <div class="stat-value">
              {{ mb(stats[c.id].mem_usage_bytes) }}
              <span class="muted tiny">/ {{ mb(stats[c.id].mem_limit_bytes) }}M</span>
            </div>
          </div>
          <div class="stat">
            <div class="stat-label">NET</div>
            <div class="stat-value">
              <span class="muted tiny">↓</span>{{ mb(stats[c.id].net_rx_bytes) }}
              <span class="muted tiny">↑</span>{{ mb(stats[c.id].net_tx_bytes) }}
            </div>
          </div>
        </div>
        <div v-else class="small muted mono">{{ c.status }}</div>

        <div class="ports mono tiny mb-2" v-if="c.ports && c.ports.length">
          <span v-for="(p, i) in c.ports" :key="i" class="port">
            {{ p.host_port ? `${p.host_port}:${p.container_port}` : p.container_port }}/{{ p.protocol }}
          </span>
        </div>

        <div class="flex gap-2">
          <button v-if="c.status !== 'running'" @click.stop="action(c.name, 'start')">Start</button>
          <button v-else @click.stop="action(c.name, 'stop')">Stop</button>
          <button @click.stop="action(c.name, 'restart')">Restart</button>
          <button @click.stop="showLogs(c.name)">Logs</button>
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

let pollTimer = null
let ws = null

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

function statusClass(s) {
  if (s === 'running') return 'ok'
  if (s === 'restarting') return 'warn'
  return 'off'
}

function mb(bytes) {
  if (!bytes) return '0'
  return (bytes / 1024 / 1024).toFixed(0)
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

async function bulk(kind) {
  const names = [...selected.value]
  for (const n of names) await action(n, kind)
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
      for (const row of msg.containers) next[row.id] = row
      stats.value = next
    }
  }
  ws.onclose = () => {
    // Reconnect after a short delay
    setTimeout(openWebSocket, 2000)
  }
}

onMounted(() => {
  refresh()
  openWebSocket()
  pollTimer = setInterval(refresh, 10000)
})
onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  if (ws) ws.close()
})
</script>

<style scoped>
.card {
  cursor: pointer;
  transition: border-color 0.1s;
}
.card:hover { border-color: var(--border-strong); }
.card.selected { border-color: var(--accent); }

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
}

.ports {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  color: var(--fg-2);
}
.port {
  background: var(--bg-2);
  padding: 1px 5px;
  border-radius: 3px;
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
</style>
