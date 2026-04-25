<template>
  <div class="containers">

    <!-- ── Toolbar ─────────────────────────────────────────────────────── -->
    <div class="toolbar">
      <div class="search-wrap">
        <span class="search-icon">🔍</span>
        <input v-model="search" placeholder="Filter containers…" class="search-input" />
      </div>
      <label class="toggle-label">
        <input type="checkbox" v-model="showStopped" />
        <span>Show stopped</span>
      </label>
      <div class="toolbar-count">{{ filtered.length }} / {{ containers.length }}</div>
      <!-- Bulk actions appear only when rows are selected -->
      <transition name="fade">
        <div v-if="selected.size > 0" class="bulk-actions">
          <span class="bulk-count">{{ selected.size }} selected</span>
          <button @click="bulk('start')">Start</button>
          <button @click="bulk('stop')">Stop</button>
          <button @click="bulk('restart')">Restart</button>
          <button class="danger" @click="bulk('remove')">Remove</button>
          <button class="bulk-clear" @click="selected = new Set()">✕</button>
        </div>
      </transition>
    </div>

    <!-- ── Container table ────────────────────────────────────────────── -->
    <div class="container-table">
      <!-- Table header -->
      <div class="table-header">
        <div class="th th-check">
          <div class="check-box" :class="{ checked: selected.size > 0 && selected.size === filtered.length }"
               @click="toggleSelectAll">
            <svg v-if="selected.size > 0 && selected.size === filtered.length" viewBox="0 0 10 10" fill="none">
              <polyline points="1.5,5 4,7.5 8.5,2" stroke="currentColor" stroke-width="1.8"
                stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </div>
        </div>
        <div class="th th-name">Name</div>
        <div class="th th-state">State</div>
        <div class="th th-actions">Quick Actions</div>
        <div class="th th-image">Image</div>
        <div class="th th-created">Created</div>
        <div class="th th-ports">Ports</div>
      </div>

      <!-- Table rows -->
      <div
        v-for="c in filtered"
        :key="c.id"
        class="table-row"
        :class="{
          'row-running':   c.state === 'running' && c.health !== 'unhealthy',
          'row-unhealthy': c.health === 'unhealthy',
          'row-stopped':   c.state !== 'running',
          'row-selected':  selected.has(c.name),
        }"
        @click="toggleExpand(c.id)"
      >
        <!-- Checkbox -->
        <div class="td td-check" @click.stop="toggleSelect(c.name)">
          <div class="check-box" :class="{ checked: selected.has(c.name) }">
            <svg v-if="selected.has(c.name)" viewBox="0 0 10 10" fill="none">
              <polyline points="1.5,5 4,7.5 8.5,2" stroke="currentColor" stroke-width="1.8"
                stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </div>
        </div>

        <!-- Name with status indicator -->
        <div class="td td-name">
          <div class="name-cell">
            <div class="dot-wrap" :title="statusLabel(c)">
              <span class="dot" :class="dotClass(c)"></span>
              <span v-if="statusIsAnimated(c)" class="dot-ping" :class="dotClass(c)"></span>
            </div>
            <span class="container-name">{{ formatName(c.name) }}</span>
          </div>
        </div>

        <!-- State -->
        <div class="td td-state">
          <span class="status-pill" :class="pillClass(c)">{{ pillLabel(c) }}</span>
        </div>

        <!-- Quick Actions -->
        <div class="td td-actions" @click.stop>
          <div class="action-buttons">
            <a v-if="webUiUrls[c.id]" :href="webUiUrls[c.id]" target="_blank"
               class="act-btn act-open" title="Open app">↗</a>
            <button v-if="c.state !== 'running'" class="act-btn act-start"
              @click="action(c.name, 'start')" title="Start">▶</button>
            <button v-else class="act-btn act-stop"
              @click="action(c.name, 'stop')" title="Stop">⏸</button>
            <button class="act-btn act-restart"
              @click="action(c.name, 'restart')" title="Restart">↺</button>
            <button class="act-btn act-logs"
              @click="showLogs(c.name)" title="Logs">≡</button>

            <!-- Two-step remove -->
            <template v-if="confirmRemove !== c.name">
              <button class="act-btn act-remove"
                @click="confirmRemove = c.name" title="Remove">✕</button>
            </template>
            <template v-else>
              <span class="confirm-label">Remove?</span>
              <button class="act-btn act-confirm" @click="doRemove(c.name)">Yes</button>
              <button class="act-btn act-cancel"  @click="confirmRemove = null">No</button>
            </template>
          </div>
        </div>

        <!-- Image -->
        <div class="td td-image">
          <span class="image-name">{{ shortImage(c.image) }}</span>
        </div>

        <!-- Created -->
        <div class="td td-created">
          <span class="created-time">{{ uptime(c) }}</span>
        </div>

        <!-- Ports -->
        <div class="td td-ports">
          <div class="port-list">
            <span v-for="(p, i) in c.ports.filter(p => p.host_port).slice(0, 3)" :key="i" class="port-badge">
              {{ p.host_port }}:{{ p.container_port }}
            </span>
            <span v-if="c.ports.filter(p => p.host_port).length > 3" class="port-more">
              +{{ c.ports.filter(p => p.host_port).length - 3 }}
            </span>
          </div>
        </div>

        <!-- Expanded stats row -->
        <div v-if="expanded === c.id" class="stats-row">
          <div class="stats-content">
            <template v-if="stats[c.id]">
              <div class="stat-item">
                <span class="stat-label">CPU</span>
                <span class="stat-val" :class="{ hot: stats[c.id].cpu_percent > 80 }">
                  {{ stats[c.id].cpu_percent.toFixed(1) }}%
                </span>
                <div class="stat-bar">
                  <div class="stat-fill" :style="{
                    width: Math.min(stats[c.id].cpu_percent, 100) + '%',
                    background: stats[c.id].cpu_percent > 80 ? 'var(--err)' : 'var(--accent)'
                  }"></div>
                </div>
              </div>
              <div class="stat-item">
                <span class="stat-label">MEM</span>
                <span class="stat-val">
                  {{ mb(stats[c.id].mem_usage_bytes) }}<span class="stat-unit">M</span>
                  <span class="muted"> / {{ mb(stats[c.id].mem_limit_bytes) }}M</span>
                </span>
                <div class="stat-bar">
                  <div class="stat-fill" :style="{
                    width: Math.min(stats[c.id].mem_percent, 100) + '%',
                    background: stats[c.id].mem_percent > 85 ? 'var(--err)' : 'var(--blue)'
                  }"></div>
                </div>
              </div>
              <div class="stat-item stat-net">
                <span class="stat-label">NET</span>
                <span class="stat-val">
                  <span class="muted">↓</span>{{ humanBytes(stats[c.id].net_rx_bytes) }}
                  <span class="muted"> ↑</span>{{ humanBytes(stats[c.id].net_tx_bytes) }}
                </span>
              </div>
            </template>
            <span v-else class="stats-pending">collecting stats…</span>
          </div>
        </div>
      </div>

      <div v-if="!filtered.length" class="empty-state muted">
        No containers match your filter.
      </div>
    </div>

    <!-- ── Log modal ──────────────────────────────────────────────────── -->
    <div v-if="logsOpen" class="log-modal" @click.self="logsOpen = false">
      <div class="log-panel">
        <div class="log-header">
          <strong class="mono">{{ logsName }}</strong>
          <span class="muted small"> — last 300 lines</span>
          <button class="log-close" @click="logsOpen = false">✕</button>
        </div>
        <pre class="logs mono">{{ logs }}</pre>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, inject } from 'vue'

const showToast = inject('showToast')

const containers   = ref([])
const stats        = ref({})
const search       = ref('')
const showStopped  = ref(true)
const selected     = ref(new Set())
const expanded     = ref(null)   // container id currently expanded
const confirmRemove = ref(null)
const logsOpen     = ref(false)
const logsName     = ref('')
const logs         = ref('')

let pollTimer = null
let ws        = null
let wsActive  = false

// ── Computed ───────────────────────────────────────────────────────────────
const webUiUrls = computed(() => {
  const map = {}
  const host = window.location.hostname
  for (const c of containers.value) {
    if (c.web_url) {
      map[c.id] = c.web_url.replace('://0.0.0.0:', `://${host}:`)
    } else {
      map[c.id] = null
    }
  }
  return map
})

const filtered = computed(() => {
  const q = search.value.toLowerCase()
  return containers.value
    .filter(c => showStopped.value || c.state === 'running')
    .filter(c => !q || c.name.toLowerCase().includes(q) || c.image.toLowerCase().includes(q))
    .sort((a, b) => {
      // Running first, then by name
      if (a.state === 'running' && b.state !== 'running') return -1
      if (a.state !== 'running' && b.state === 'running') return 1
      return a.name.localeCompare(b.name)
    })
})

// ── Helpers ────────────────────────────────────────────────────────────────
function formatName(n) { return n.replace(/^\//, '') }
function shortImage(img) {
  // "lscr.io/linuxserver/sonarr:latest" → "linuxserver/sonarr"
  return img.split('/').slice(-2).join('/').split(':')[0]
}
function mb(b) { return b ? (b / 1048576).toFixed(0) : '0' }
function humanBytes(b) {
  if (!b || b < 1024) return '0B'
  if (b < 1048576)    return (b / 1024).toFixed(1) + 'K'
  if (b < 1073741824) return (b / 1048576).toFixed(1) + 'M'
  return (b / 1073741824).toFixed(2) + 'G'
}

function dotClass(c) {
  if (c.health === 'unhealthy') return 'dot-err'
  if (c.state === 'restarting' || c.state === 'paused') return 'dot-warn'
  if (c.state === 'dead')       return 'dot-err'
  if (c.state === 'running')    return 'dot-ok'
  return 'dot-off'
}
function statusIsAnimated(c) {
  return c.state === 'restarting' || c.health === 'starting'
}
function statusLabel(c) {
  if (c.health === 'unhealthy') return 'Unhealthy'
  if (c.health === 'starting')  return 'Health check starting'
  if (c.state === 'restarting') return 'Restarting'
  if (c.state === 'paused')     return 'Paused'
  if (c.state === 'dead')       return 'Dead'
  if (c.state === 'running')    return 'Running'
  return c.status
}
function pillClass(c) {
  if (c.health === 'unhealthy') return 'pill-err'
  if (c.state === 'restarting') return 'pill-warn'
  if (c.state === 'running')    return 'pill-ok'
  return 'pill-off'
}
function pillLabel(c) {
  if (c.health === 'unhealthy') return 'unhealthy'
  if (c.state === 'restarting') return 'restarting'
  if (c.state === 'running')    return 'running'
  return c.state || c.status
}

function uptime(c) {
  if (c.state !== 'running' || !c.created) return '—'
  const secs = Math.floor(Date.now() / 1000) - c.created
  if (secs < 60)      return `${secs}s`
  if (secs < 3600)    return `${Math.floor(secs/60)}m`
  if (secs < 86400)   return `${Math.floor(secs/3600)}h`
  return `${Math.floor(secs/86400)}d`
}

// ── Actions ────────────────────────────────────────────────────────────────
function toggleExpand(id) {
  expanded.value = expanded.value === id ? null : id
  confirmRemove.value = null
}
function toggleSelect(name) {
  const s = new Set(selected.value)
  s.has(name) ? s.delete(name) : s.add(name)
  selected.value = s
}

function toggleSelectAll() {
  if (selected.value.size === filtered.value.length && filtered.value.length > 0) {
    selected.value = new Set()
  } else {
    selected.value = new Set(filtered.value.map(c => c.name))
  }
}

async function action(name, kind) {
  try {
    const r = await fetch(`/api/containers/${name}/${kind}`,
      { method: kind === 'remove' ? 'DELETE' : 'POST' })
    if (r.ok) {
      showToast(`${kind} ${name} → ok`)
      await new Promise(r => setTimeout(r, 500))
      refresh()
    }
    else showToast(`${kind} ${name} failed: ${await r.text()}`, 'err')
  } catch (e) { showToast(`${kind} ${name}: ${e.message}`, 'err') }
}

async function doRemove(name) {
  confirmRemove.value = null
  const c = containers.value.find(x => x.name === name)
  try {
    if (c?.state === 'running') {
      showToast(`Stopping ${name}…`, 'warn', 2000)
      const s = await fetch(`/api/containers/${name}/stop`, { method: 'POST' })
      if (!s.ok) { showToast(`Could not stop ${name}`, 'err'); return }
      await new Promise(r => setTimeout(r, 800))
    }
    const r = await fetch(`/api/containers/${name}`, { method: 'DELETE' })
    if (r.ok) { showToast(`${name} removed`); refresh() }
    else showToast(`Remove failed: ${await r.text()}`, 'err')
  } catch (e) { showToast(`Remove error: ${e.message}`, 'err') }
}

async function bulk(kind) {
  const names = [...selected.value]
  if (kind === 'remove') { for (const n of names) await doRemove(n) }
  else                   { for (const n of names) await action(n, kind) }
  selected.value = new Set()
}

async function showLogs(name) {
  logsName.value = name; logs.value = 'Loading…'; logsOpen.value = true
  try {
    const r = await fetch(`/api/containers/${name}/logs?tail=300`, { method: 'POST' })
    logs.value = await r.text()
  } catch (e) { logs.value = String(e) }
}

// ── API + WebSocket ────────────────────────────────────────────────────────
async function refresh() {
  try { containers.value = await fetch('/api/containers').then(r => r.json()) }
  catch (e) { console.error(e) }
}

function openWebSocket() {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  ws = new WebSocket(`${proto}//${window.location.host}/ws/stats`)
  ws.onmessage = e => {
    const msg = JSON.parse(e.data)
    if (msg.type === 'stats') {
      const next = {}
      for (const row of msg.containers) next[row.id] = row
      stats.value = next
    }
  }
  ws.onclose = () => { if (wsActive) setTimeout(openWebSocket, 2000) }
}

onMounted(() => { wsActive = true; refresh(); openWebSocket(); pollTimer = setInterval(refresh, 10000) })
onUnmounted(() => { wsActive = false; if (pollTimer) clearInterval(pollTimer); if (ws) ws.close() })
</script>

<style scoped>
.containers { max-width: 1100px; }

/* ── Toolbar ─────────────────────────────────────────────────────────────── */
.toolbar {
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  margin-bottom: 16px;
}
.search-wrap { position: relative; flex: 1; max-width: 320px; }
.search-icon { position: absolute; left: 9px; top: 50%; transform: translateY(-50%); font-size: 12px; }
.search-input {
  width: 100%; padding: 6px 9px 6px 28px; font-family: var(--font-sans);
  font-size: 13px; background: var(--bg-1); border: 1.5px solid var(--border);
  border-radius: var(--radius-sm); color: var(--fg-0); box-sizing: border-box;
}
.search-input:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-dim); }
.toggle-label { display: flex; align-items: center; gap: 6px; font-size: 12.5px; color: var(--fg-1); cursor: pointer; white-space: nowrap; }
.toggle-label input { cursor: pointer; }
.toolbar-count { font-size: 12px; color: var(--fg-2); font-family: var(--font-mono); white-space: nowrap; }
.bulk-actions { display: flex; align-items: center; gap: 6px; margin-left: auto; }
.bulk-count { font-size: 12px; font-weight: 600; color: var(--accent); }
.bulk-clear { background: none; border: none; cursor: pointer; font-size: 14px; color: var(--fg-2); padding: 0 2px; }

/* ── Container table ─────────────────────────────────────────────────────── */
.container-table {
  background: var(--bg-1);
  border: 1.5px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}

/* Table header */
.table-header {
  display: grid;
  grid-template-columns: 40px 1fr 120px 200px 1fr 100px 120px;
  background: var(--bg-0);
  border-bottom: 1px solid var(--border);
  font-weight: 600;
  font-size: 12px;
  color: var(--fg-1);
}

.th {
  padding: 12px 16px;
  display: flex;
  align-items: center;
  border-right: 1px solid var(--border);
}
.th:last-child { border-right: none; }
.th-check { justify-content: center; }

/* Table rows */
.table-row {
  display: grid;
  grid-template-columns: 40px 1fr 120px 200px 1fr 100px 120px;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  transition: background-color 0.13s;
  position: relative;
}
.table-row:last-child { border-bottom: none; }
.table-row:hover { background: var(--bg-0); }

.row-running { border-left: 3px solid var(--ok); }
.row-unhealthy { border-left: 3px solid var(--err); }
.row-stopped { border-left: 3px solid var(--fg-2); opacity: 0.7; }
.row-selected { background: var(--accent-subtle); border-left: 3px solid var(--accent); }

.td {
  padding: 12px 16px;
  display: flex;
  align-items: center;
  border-right: 1px solid var(--border);
  min-height: 48px;
}
.td:last-child { border-right: none; }

/* Checkbox */
.td-check { justify-content: center; }
.check-box {
  width: 16px; height: 16px; border-radius: 3px;
  border: 1.5px solid var(--border-strong); background: var(--bg-1);
  display: flex; align-items: center; justify-content: center;
  transition: all 0.12s; color: #fff; cursor: pointer;
}
.check-box.checked { background: var(--accent); border-color: var(--accent); }
.check-box svg { width: 10px; height: 10px; }

/* Name cell */
.name-cell {
  display: flex;
  align-items: center;
  gap: 12px;
}

.container-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--fg-0);
}

/* Status dot */
.dot-wrap { position: relative; width: 12px; height: 12px; flex-shrink: 0; }
.dot {
  display: block; width: 12px; height: 12px; border-radius: 50%;
  position: relative; z-index: 1;
}
.dot-ok   { background: #22c55e; box-shadow: 0 0 8px rgba(34,197,94,0.7), 0 0 2px rgba(34,197,94,0.9); }
.dot-warn { background: var(--warn); box-shadow: 0 0 6px rgba(217,119,6,0.6); }
.dot-err  { background: var(--err);  box-shadow: 0 0 6px rgba(220,38,38,0.6); }
.dot-off  { background: var(--fg-2); }
.dot-ping {
  position: absolute; inset: 0; border-radius: 50%;
  animation: ping 1.4s cubic-bezier(0,0,0.2,1) infinite; opacity: 0.5;
}
@keyframes ping { 0% { transform: scale(1); opacity:0.5 } 75%,100% { transform:scale(2.4); opacity:0 } }
.dot-ping.dot-ok   { background: #22c55e; }
.dot-ping.dot-warn { background: var(--warn); }
.dot-ping.dot-err  { background: var(--err); }

/* Status pill */
.status-pill {
  font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 12px;
  text-transform: uppercase; letter-spacing: 0.04em; white-space: nowrap;
}
.pill-ok  { background: var(--ok-bg);   color: var(--ok);   border: 1px solid rgba(22,163,74,0.2); }
.pill-err { background: var(--err-bg);  color: var(--err);  border: 1px solid rgba(220,38,38,0.2); }
.pill-warn { background: var(--warn-bg); color: var(--warn); border: 1px solid rgba(217,119,6,0.2); }
.pill-off { background: var(--bg-2); color: var(--fg-2); border: 1px solid var(--border); }

/* Action buttons */
.action-buttons { display: flex; align-items: center; gap: 4px; }
.act-btn {
  display: inline-flex; align-items: center; justify-content: center;
  width: 28px; height: 28px; padding: 0; border-radius: 4px;
  font-size: 12px; font-family: var(--font-mono);
  border: 1.5px solid var(--border); background: var(--bg-1); color: var(--fg-1);
  cursor: pointer; transition: all 0.13s; text-decoration: none; flex-shrink: 0;
}
.act-btn:hover { border-color: var(--border-strong); background: var(--bg-2); color: var(--fg-0); }
.act-start:hover  { border-color: var(--ok);     color: var(--ok);     background: var(--ok-bg); }
.act-stop:hover   { border-color: var(--warn);   color: var(--warn);   background: var(--warn-bg); }
.act-restart:hover { border-color: var(--blue);  color: var(--blue);   background: rgba(37,99,235,0.07); }
.act-logs:hover   { border-color: var(--purple); color: var(--purple); background: var(--accent-dim); }
.act-open:hover   { border-color: var(--teal);   color: var(--teal);   background: rgba(8,145,178,0.07); }
.act-remove { 
  color: var(--err); 
  border: 1.5px solid var(--err-dim); 
  background: var(--err-bg); 
  font-size: 10px; 
  box-shadow: 0 0 8px rgba(220, 38, 38, 0.3);
}
.act-remove:hover { border-color: var(--err); color: #fff; background: var(--err); }
.confirm-label { font-size: 11px; color: var(--err); font-weight: 600; white-space: nowrap; margin-right: 8px; }
.act-confirm { width: auto; padding: 0 8px; font-size: 11px; font-family: var(--font-sans); font-weight: 600; background: var(--err-bg); border-color: var(--err); color: var(--err); }
.act-confirm:hover { background: var(--err); color: #fff; }
.act-cancel  { width: auto; padding: 0 8px; font-size: 11px; font-family: var(--font-sans); }

/* Image */
.image-name {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--fg-2);
}

/* Created time */
.created-time {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--fg-1);
}

/* Ports */
.port-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.port-badge {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--fg-2);
  background: var(--bg-2);
  border: 1px solid var(--border);
  padding: 2px 6px;
  border-radius: 4px;
}

.port-more {
  font-size: 10px;
  color: var(--fg-2);
  font-style: italic;
}

/* Expanded stats row */
.stats-row {
  grid-column: 1 / -1;
  border-top: 1px solid var(--border);
  background: var(--bg-0);
}

.stats-content {
  display: flex;
  align-items: center;
  gap: 20px;
  flex-wrap: wrap;
  padding: 16px 24px;
}

.stat-item { display: flex; align-items: center; gap: 8px; min-width: 0; }
.stat-label { font-family: var(--font-mono); font-size: 10px; color: var(--fg-2); text-transform: uppercase; letter-spacing: 0.07em; flex-shrink: 0; }
.stat-val { font-family: var(--font-mono); font-size: 12px; color: var(--fg-0); white-space: nowrap; }
.stat-val.hot { color: var(--err); }
.stat-unit { font-size: 10px; color: var(--fg-2); }
.stat-bar { width: 60px; height: 4px; background: var(--border); border-radius: 2px; overflow: hidden; flex-shrink: 0; }
.stat-fill { height: 100%; border-radius: 2px; transition: width 1s ease-out; }
.stat-net .stat-bar { display: none; }
.stats-pending { font-size: 12px; color: var(--fg-2); font-style: italic; }

/* ── Log modal ───────────────────────────────────────────────────────────── */
.log-modal { position: fixed; inset: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 500; }
.log-panel { background: var(--bg-0); border: 1.5px solid var(--border-strong); border-radius: var(--radius); padding: 20px; width: 90vw; max-width: 1000px; max-height: 80vh; display: flex; flex-direction: column; gap: 10px; }
.log-header { display: flex; align-items: center; gap: 6px; }
.log-close { margin-left: auto; background: none; border: none; font-size: 16px; cursor: pointer; color: var(--fg-2); padding: 0; }
.logs { flex: 1; overflow: auto; background: var(--bg-1); padding: 12px; border-radius: var(--radius); font-size: 12px; line-height: 1.4; white-space: pre; }

.empty-state { padding: 40px 0; text-align: center; }
.fade-enter-active, .fade-leave-active { transition: opacity 0.15s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
