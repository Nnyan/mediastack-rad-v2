<template>
  <div class="stack-builder">

    <!-- Header -->
    <div class="page-header">
      <h1 class="page-title">Stack Builder</h1>
      <div class="header-actions">
        <button class="btn btn-secondary" @click="preview" :disabled="previewLoading">
          {{ previewLoading ? 'Generating…' : 'Preview' }}
        </button>
        <button class="btn btn-primary" :disabled="deploying || !selectedServices.length" @click="deploy">
          {{ deploying ? 'Deploying…' : 'Deploy Stack' }}
        </button>
      </div>
    </div>

    <!-- Main Layout: Sidebar + Table -->
    <div class="builder-layout">

      <!-- Left Sidebar: Categories -->
      <div class="sidebar">
        <div class="sidebar-section">
          <div class="sidebar-title">Services</div>
          <div class="category-list">
            <button
              v-for="cat in categories"
              :key="cat.key"
              :class="['category-item', { active: activeCategory === cat.key }]"
              @click="activeCategory = activeCategory === cat.key ? '' : cat.key"
            >
              <span class="cat-icon">{{ cat.icon }}</span>
              <span class="cat-name">{{ cat.name }}</span>
              <span class="cat-count">{{ cat.count }}</span>
            </button>
          </div>
        </div>

        <div class="sidebar-section">
          <div class="sidebar-title">Quick Filters</div>
          <button :class="['filter-btn', { active: search }]" @click="search = ''">
            <span>Clear filter</span>
          </button>
        </div>
      </div>

      <!-- Right: Service Table -->
      <div class="main-content">

        <!-- Search Bar -->
        <div class="toolbar-row">
          <div class="search-input-wrap">
            <span class="search-icon">🔍</span>
            <input
              v-model="search"
              placeholder="Search services..."
              class="search-input"
            />
          </div>
          <div class="toolbar-info">
            {{ selectedServices.length }} selected · {{ filteredServices.length }} shown
          </div>
        </div>

        <!-- Service Table -->
        <div class="service-table">
          <!-- Table Header -->
          <div class="table-header">
            <div class="th th-check">
              <div
                class="check-box"
                :class="{ checked: allSelected, indeterminate: someSelected }"
                @click="toggleSelectAll"
              >
                <svg v-if="someSelected && !allSelected" viewBox="0 0 10 10" fill="none">
                  <rect x="1" y="3" width="8" height="4" rx="1" fill="currentColor"/>
                </svg>
                <svg v-else-if="allSelected" viewBox="0 0 10 10" fill="none">
                  <polyline points="1.5,5 4,7.5 8.5,2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
              </div>
            </div>
            <div class="th th-service">Service</div>
            <div class="th th-desc">Description</div>
            <div class="th th-status">Status</div>
            <div class="th th-port">Port</div>
          </div>

          <!-- Table Rows -->
          <div
            v-for="svc in filteredServices"
            :key="svc.key"
            :class="['table-row', { selected: pick[svc.key], 'row-running': LIVE_SERVICES.has(svc.key) && pick[svc.key] }]"
            @click="toggle(svc.key)"
          >
            <div class="td td-check" @click.stop>
              <div
                class="check-box"
                :class="{ checked: pick[svc.key] }"
                @click="toggle(svc.key)"
              >
                <svg v-if="pick[svc.key]" viewBox="0 0 10 10" fill="none">
                  <polyline points="1.5,5 4,7.5 8.5,2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
              </div>
            </div>

            <div class="td td-service">
              <span class="service-icon">{{ svc.icon }}</span>
              <span class="service-name">{{ svc.display_name }}</span>
              <span v-if="portOverrides[svc.key]" class="port-override">:{{ portOverrides[svc.key] }}</span>
              <span v-if="LIVE_SERVICES.has(svc.key)" class="live-badge">● Running</span>
            </div>

            <div class="td td-desc">
              <span class="service-desc">{{ svc.description }}</span>
            </div>

            <div class="td td-status">
              <span v-if="pick[svc.key]" class="status-badge enabled">Enabled</span>
              <span v-else class="status-badge">Disabled</span>
            </div>

            <div class="td td-port">
              <span v-if="svc.web_port" class="port-number">{{ svc.web_port }}</span>
              <span v-else class="port-empty">—</span>
            </div>
          </div>

          <div v-if="!filteredServices.length" class="empty-state">
            No services match your filter.
          </div>
        </div>
      </div>
    </div>

    <!-- Config Drawer (slides in from right) -->
    <div class="config-drawer" :class="{ open: configOpen }">
      <div class="drawer-header">
        <h2>Configuration</h2>
        <button class="drawer-close" @click="configOpen = false">✕</button>
      </div>

      <div class="drawer-content">
        <!-- Domain -->
        <div class="config-group">
          <label class="config-label">Domain</label>
          <input v-model="req.domain" placeholder="example.com" class="config-input" />
          <span class="config-hint">Apps served as sonarr.{{ req.domain || 'example.com' }}</span>
        </div>

        <!-- Config Root -->
        <div class="config-group">
          <label class="config-label">Config Root</label>
          <input v-model="req.config_root" placeholder="/home/stack/mediacenter/config" class="config-input" />
        </div>

        <!-- Media Root -->
        <div class="config-group">
          <label class="config-label">Media Root</label>
          <input v-model="req.media_root" placeholder="/mnt/media" class="config-input" />
          <span class="config-hint">Mounted as /data inside containers</span>
        </div>

        <!-- Timezone -->
        <div class="config-group">
          <label class="config-label">Timezone</label>
          <input v-model="req.timezone" placeholder="America/Los_Angeles" class="config-input" />
        </div>

        <!-- PUID/PGID -->
        <div class="config-row">
          <div class="config-group">
            <label class="config-label">PUID</label>
            <input v-model.number="req.puid" type="number" class="config-input" />
          </div>
          <div class="config-group">
            <label class="config-label">PGID</label>
            <input v-model.number="req.pgid" type="number" class="config-input" />
          </div>
        </div>

        <!-- Tailscale Config (if selected) -->
        <template v-if="pick['tailscale']">
          <div class="config-divider"></div>
          <div class="config-section-title">Tailscale</div>

          <div class="config-group">
            <label class="config-label">Auth Key</label>
            <input v-model="req.tailscale_auth_key" type="password" class="config-input" />
            <a href="https://login.tailscale.com/admin/settings/keys" target="_blank" class="config-link">Generate in Tailscale ↗</a>
          </div>

          <div class="config-group">
            <label class="config-label">Node Hostname</label>
            <input v-model="req.tailscale_hostname" class="config-input" />
          </div>

          <div class="config-group">
            <label class="config-label">Subnet Routes</label>
            <input v-model="req.tailscale_routes" placeholder="172.20.0.0/16" class="config-input" />
          </div>
        </template>

        <!-- Tinyauth Config (if selected) -->
        <template v-if="pick['tinyauth']">
          <div class="config-divider"></div>
          <div class="config-section-title">Tinyauth</div>

          <div class="config-group">
            <label class="config-label">LAN Subnet</label>
            <input v-model="req.lan_subnet" placeholder="10.0.0.0/22" class="config-input" />
            <span class="config-hint">Devices in this CIDR bypass auth</span>
          </div>

          <div class="config-group">
            <label class="config-label">App URL</label>
            <input v-model="req.tinyauth_app_url" placeholder="https://auth.example.com" class="config-input" />
          </div>

          <div class="config-group">
            <label class="config-label">Users</label>
            <div class="user-row">
              <input v-model="req.tinyauth_users" placeholder="admin:$2b$10$..." class="config-input" />
              <button class="btn btn-small" @click="generateCredentials">Generate</button>
            </div>
          </div>
        </template>

        <!-- Config Output -->
        <div class="config-divider"></div>
        <pre v-if="previewText" class="config-output">{{ previewText }}</pre>

        <!-- Deploy Output -->
        <div v-if="deployOutput" :class="['deploy-output', deployOk ? 'ok' : 'err']">
          <div class="deploy-status">{{ deployOk ? '✓ Deploy complete' : '✕ Deploy failed' }}</div>
          <pre class="deploy-text">{{ deployOutput }}</pre>
        </div>
      </div>
    </div>

    <!-- Bottom Bar for Mobile -->
    <div v-if="selectedServices.length && !configOpen" class="bottom-bar">
      <div class="bottom-info">
        {{ selectedServices.length }} services selected
      </div>
      <button class="btn btn-secondary" @click="configOpen = true">Configure</button>
      <button class="btn btn-primary" :disabled="deploying" @click="deploy">Deploy</button>
    </div>

  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch, inject } from 'vue'

const showToast = inject('showToast')

// ── State ──────────────────────────────────────────────────────────────────
const rawCatalog = ref({})
const pick = reactive(JSON.parse(localStorage.getItem('rad-stack-builder-pick') || '{}'))
const search = ref('')
const activeCategory = ref('')
const configOpen = ref(false)
const portOverrides = reactive({})

const previewLoading = ref(false)
const previewText = ref('')
const deployOutput = ref('')
const deployOk = ref(false)
const deploying = ref(false)

// ── Storage ───────────────────────────────────────────────────────────────
const STORAGE_KEY = 'rad-stack-builder-v3'
const defaults = {
  domain: '', timezone: 'America/Los_Angeles', puid: 1000, pgid: 1000,
  config_root: '/home/stack/mediacenter/config',
  media_root: '/mnt/media',
  tailscale_auth_key: '', tailscale_routes: '', tailscale_hostname: 'mediastack',
  tinyauth_users: '', tinyauth_app_url: '',
  lan_subnet: '10.0.0.0/22',
}

let _stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null')
if (!_stored || Object.keys(_stored).length === 0) {
  _stored = {}
}
const req = reactive({ ...defaults, ...(_stored || {}) })

watch(req, v => localStorage.setItem(STORAGE_KEY, JSON.stringify(v)), { deep: true })
watch(pick, v => localStorage.setItem('rad-stack-builder-pick', JSON.stringify({...v})), { deep: true })

// ── Constants ──────────────────────────────────────────────────────────────
const ICONS = {
  media: '🎬', indexers: '📺', downloaders: '⬇️', requests: '🙋', infra: '⚙️',
  plex: '🎬', jellyfin: '🎞️', sonarr: '📺', radarr: '🎥', lidarr: '🎵',
  readarr: '📚', bazarr: '💬', prowlarr: '🔍', qbittorrent: '⬇️',
  sabnzbd: '📰', nzbget: '📥', seerr: '🙋',
  traefik: '🔀', tinyauth: '🔒', tailscale: '🔗', cloudflared: '☁️',
}

const CATEGORIES = {
  media: { key: 'media', name: 'Media', icon: '🎬' },
  indexers: { key: 'indexers', name: 'Management', icon: '📺' },
  downloaders: { key: 'downloaders', name: 'Download', icon: '⬇️' },
  requests: { key: 'requests', name: 'Requests', icon: '🙋' },
  infra: { key: 'infra', name: 'Infrastructure', icon: '⚙️' },
}

const LIVE_SERVICES = new Set([
  'traefik', 'plex', 'sonarr', 'radarr', 'prowlarr', 'qbittorrent', 'cloudflared',
])

// ── Computed ───────────────────────────────────────────────────────────────
const flatServices = computed(() => {
  const out = []
  for (const [cat, svcs] of Object.entries(rawCatalog.value)) {
    for (const svc of svcs) {
      out.push({ ...svc, category: cat, icon: ICONS[svc.key] || '📦' })
    }
  }
  return out
})

const categories = computed(() => {
  const counts = {}
  for (const svc of flatServices.value) {
    counts[svc.category] = (counts[svc.category] || 0) + 1
  }
  return Object.values(CATEGORIES).map(c => ({ ...c, count: counts[c.key] || 0 }))
})

const filteredServices = computed(() => {
  const q = search.value.toLowerCase()
  return flatServices.value.filter(svc => {
    if (activeCategory.value && svc.category !== activeCategory.value) return false
    if (!q) return true
    return svc.display_name.toLowerCase().includes(q) || svc.description.toLowerCase().includes(q)
  })
})

const selectedServices = computed(() =>
  Object.entries(pick).filter(([, on]) => on).map(([k]) => k)
)

const allSelected = computed(() =>
  filteredServices.value.length && filteredServices.value.every(s => pick[s.key])
)

const someSelected = computed(() =>
  filteredServices.value.some(s => pick[s.key]) && !allSelected.value
)

// ── Actions ───────────────────────────────────────────────────────────────
function toggle(key) {
  pick[key] = !pick[key]
  localStorage.setItem('rad-stack-builder-pick', JSON.stringify({...pick}))
}

function toggleSelectAll() {
  const newVal = !allSelected.value
  for (const svc of filteredServices.value) {
    pick[svc.key] = newVal
  }
}

// ── API ───────────────────────────────────────────────────────────────────
async function loadCatalog() {
  try {
    rawCatalog.value = await fetch('/api/catalog').then(r => r.json())
    if (Object.keys(pick).length === 0) {
      ['traefik', 'prowlarr', 'sonarr', 'radarr', 'bazarr', 'seerr',
       'qbittorrent', 'plex', 'cloudflared'].forEach(k => { pick[k] = true })
    }
  } catch (e) {
    showToast('Failed to load catalog', 'err')
  }
}

function buildRequest() {
  return {
    domain: req.domain,
    timezone: req.timezone,
    puid: req.puid,
    pgid: req.pgid,
    config_root: req.config_root,
    media_root: req.media_root,
    tailscale_auth_key: req.tailscale_auth_key,
    tailscale_routes: req.tailscale_routes,
    tailscale_hostname: req.tailscale_hostname,
    tinyauth_enabled: !!pick['tinyauth'],
    tinyauth_users: req.tinyauth_users,
    tinyauth_app_url: req.tinyauth_app_url,
    lan_subnet: req.lan_subnet,
    services: selectedServices.value.map(k => ({
      key: k,
      enabled: true,
      port_override: portOverrides[k] || undefined,
    })),
  }
}

async function preview() {
  previewLoading.value = true
  previewText.value = ''
  configOpen.value = true
  try {
    const r = await fetch('/api/stack/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildRequest()),
    })
    if (!r.ok) throw new Error(await r.text())
    const data = await r.json()
    previewText.value = data.yaml
    showToast(`Generated ${data.bytes} bytes`)
  } catch (e) {
    showToast(`Generate failed: ${e.message}`, 'err')
  } finally {
    previewLoading.value = false
  }
}

async function deploy() {
  if (!confirm('Deploy this stack?')) return
  deploying.value = true
  deployOutput.value = ''
  configOpen.value = true
  try {
    const r = await fetch('/api/stack/deploy', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildRequest()),
    })
    const data = await r.json()
    deployOk.value = data.ok
    deployOutput.value = [data.stdout, data.stderr].filter(Boolean).join('\n')
    if (data.ok) {
      showToast('Deploy complete', 'ok')
    } else {
      showToast('Deploy failed', 'err')
    }
  } catch (e) {
    deployOk.value = false
    deployOutput.value = String(e)
    showToast(`Deploy error: ${e.message}`, 'err')
  } finally {
    deploying.value = false
  }
}

const generatedPassword = ref('')

async function generateCredentials() {
  const chars = 'abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789'
  const arr = new Uint8Array(16)
  crypto.getRandomValues(arr)
  const password = Array.from(arr).map(b => chars[b % chars.length]).join('')
  try {
    const r = await fetch('/api/utils/hash-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    })
    const { hash } = await r.json()
    req.tinyauth_users = `admin:${hash}`
    generatedPassword.value = password
    showToast('Password: ' + password + ' — save it!', 'warn', 8000)
  } catch (e) {
    showToast(`Failed: ${e.message}`, 'err')
  }
}

onMounted(loadCatalog)
</script>

<style scoped>
/* ── Layout ─────────────────────────────────────────────────────────────── */
.stack-builder {
  padding-bottom: 80px;
  min-height: 100vh;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-4);
  flex-wrap: wrap;
  gap: var(--space-3);
}

.page-title {
  font-size: 24px;
  font-weight: 700;
  color: var(--fg-0);
  margin: 0;
}

.header-actions {
  display: flex;
  gap: var(--space-2);
}

.builder-layout {
  display: flex;
  gap: var(--space-4);
}

/* ── Sidebar ────────────────────────────────────────────────────────── */
.sidebar {
  width: 200px;
  flex-shrink: 0;
}

.sidebar-section {
  margin-bottom: var(--space-4);
}

.sidebar-title {
  font-size: 11px;
  font-weight: 700;
  color: var(--fg-2);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: var(--space-2);
}

.category-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.category-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 6px 10px;
  border-radius: var(--radius-sm);
  background: transparent;
  border: none;
  cursor: pointer;
  text-align: left;
  transition: background 0.12s;
}

.category-item:hover {
  background: var(--bg-2);
}

.category-item.active {
  background: var(--accent-subtle);
  color: var(--accent);
}

.cat-icon {
  font-size: 14px;
}

.cat-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--fg-0);
  flex: 1;
}

.category-item.active .cat-name {
  color: var(--accent);
}

.cat-count {
  font-size: 11px;
  color: var(--fg-2);
  background: var(--bg-2);
  padding: 1px 6px;
  border-radius: 10px;
}

.category-item.active .cat-count {
  background: var(--accent);
  color: #fff;
}

/* ── Main Content ─────────────────────────────────────────────────── */
.main-content {
  flex: 1;
  min-width: 0;
}

.toolbar-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}

.search-input-wrap {
  position: relative;
  flex: 1;
  max-width: 300px;
}

.search-icon {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 13px;
}

.search-input {
  width: 100%;
  padding: 6px 10px 6px 30px;
  font-size: 13px;
  background: var(--bg-0);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--fg-0);
}

.search-input:focus {
  outline: none;
  border-color: var(--accent);
}

.toolbar-info {
  font-size: 12px;
  color: var(--fg-2);
}

/* ── Service Table ───────────────────────────────────────────────── */
.service-table {
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}

.table-header {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  background: var(--bg-2);
  border-bottom: 1px solid var(--border);
  font-size: 11px;
  font-weight: 600;
  color: var(--fg-2);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.table-row {
  display: flex;
  align-items: center;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  transition: background 0.1s;
}

.table-row:hover {
  background: var(--bg-2);
}

.table-row.selected {
  background: var(--accent-subtle);
}

.table-row.row-running {
  background: rgba(22, 163, 74, 0.05);
}

.table-row.selected.row-running {
  background: rgba(22, 163, 74, 0.1);
}

.th-check, .td-check {
  width: 36px;
  flex-shrink: 0;
}

.th-service {
  flex: 1;
  min-width: 140px;
}

.td-service {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex: 1;
  min-width: 140px;
}

.service-icon {
  font-size: 16px;
}

.service-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--fg-0);
}

.port-override {
  font-size: 10px;
  color: var(--warn);
  font-family: var(--font-mono);
}

.live-badge {
  font-size: 9px;
  color: var(--ok);
  margin-left: 4px;
}

.th-desc, .td-desc {
  flex: 2;
  min-width: 150px;
}

.service-desc {
  font-size: 12px;
  color: var(--fg-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.th-status, .td-status {
  width: 80px;
  flex-shrink: 0;
}

.status-badge {
  font-size: 10px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
  background: var(--bg-2);
  color: var(--fg-2);
}

.status-badge.enabled {
  background: var(--accent-subtle);
  color: var(--accent);
}

.th-port, .td-port {
  width: 60px;
  flex-shrink: 0;
  text-align: right;
}

.port-number {
  font-size: 12px;
  font-family: var(--font-mono);
  color: var(--fg-1);
}

.port-empty {
  font-size: 12px;
  color: var(--fg-2);
}

/* Checkbox */
.check-box {
  width: 16px;
  height: 16px;
  border: 1.5px solid var(--border);
  border-radius: 3px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.1s;
}

.check-box:hover {
  border-color: var(--accent);
}

.check-box.checked {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}

.check-box.indeterminate {
  background: var(--accent-subtle);
  border-color: var(--accent);
}

.check-box svg {
  width: 10px;
  height: 10px;
}

/* ── Empty State ───────────────────────────────────────────── */
.empty-state {
  padding: var(--space-4);
  text-align: center;
  font-size: 13px;
  color: var(--fg-2);
}

/* ── Config Drawer ���─���────────────────────────────────────────────── */
.config-drawer {
  position: fixed;
  right: 0;
  top: 0;
  bottom: 0;
  width: 400px;
  background: var(--bg-1);
  border-left: 1px solid var(--border);
  transform: translateX(100%);
  transition: transform 0.2s;
  z-index: 100;
  overflow-y: auto;
}

.config-drawer.open {
  transform: translateX(0);
}

.drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  background: var(--bg-1);
}

.drawer-header h2 {
  font-size: 16px;
  font-weight: 600;
  margin: 0;
}

.drawer-close {
  background: none;
  border: none;
  font-size: 18px;
  cursor: pointer;
  color: var(--fg-2);
}

.drawer-content {
  padding: var(--space-4);
}

.config-group {
  margin-bottom: var(--space-3);
}

.config-label {
  display: block;
  font-size: 12px;
  font-weight: 600;
  color: var(--fg-1);
  margin-bottom: 4px;
}

.config-input {
  width: 100%;
  padding: 6px 10px;
  font-size: 13px;
  background: var(--bg-0);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--fg-0);
}

.config-input:focus {
  outline: none;
  border-color: var(--accent);
}

.config-hint {
  display: block;
  font-size: 11px;
  color: var(--fg-2);
  margin-top: 4px;
}

.config-link {
  font-size: 11px;
  color: var(--accent);
  margin-top: 4px;
  display: inline-block;
}

.config-row {
  display: flex;
  gap: var(--space-3);
}

.config-row .config-group {
  flex: 1;
}

.config-divider {
  height: 1px;
  background: var(--border);
  margin: var(--space-4) 0;
}

.config-section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--fg-0);
  margin-bottom: var(--space-3);
}

.user-row {
  display: flex;
  gap: var(--space-2);
}

.user-row .config-input {
  flex: 1;
}

.config-output {
  background: var(--bg-0);
  padding: var(--space-3);
  border-radius: var(--radius-sm);
  font-size: 11px;
  font-family: var(--font-mono);
  overflow-x: auto;
  max-height: 300px;
  white-space: pre;
}

.deploy-output {
  margin-top: var(--space-3);
  border-radius: var(--radius-sm);
  overflow: hidden;
}

.deploy-status {
  padding: var(--space-2) var(--space-3);
  font-size: 13px;
  font-weight: 600;
}

.deploy-output.ok .deploy-status {
  background: var(--ok-bg);
  color: var(--ok);
}

.deploy-output.err .deploy-status {
  background: var(--err-bg);
  color: var(--err);
}

.deploy-text {
  padding: var(--space-3);
  font-size: 11px;
  font-family: var(--font-mono);
  background: var(--bg-0);
  max-height: 200px;
  overflow-y: auto;
  white-space: pre;
}

/* ── Buttons ─────────────────────────────────────────────────── */
.btn {
  padding: 6px 14px;
  font-size: 13px;
  font-weight: 600;
  border-radius: var(--radius-sm);
  border: none;
  cursor: pointer;
  transition: all 0.15s;
}

.btn-primary {
  background: var(--accent);
  color: #fff;
}

.btn-primary:hover:not(:disabled) {
  background: var(--accent-dark);
}

.btn-secondary {
  background: var(--bg-2);
  color: var(--fg-0);
  border: 1px solid var(--border);
}

.btn-secondary:hover:not(:disabled) {
  background: var(--bg-3);
}

.btn-small {
  padding: 4px 10px;
  font-size: 11px;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ── Filter Button ──────────────────────────────────────────────��─�� */
.filter-btn {
  width: 100%;
  padding: 6px 10px;
  font-size: 12px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  color: var(--fg-1);
  text-align: left;
}

.filter-btn.active {
  background: var(--accent-subtle);
  border-color: var(--accent);
  color: var(--accent);
}

/* ── Bottom Bar ───────────────────────────────────────────────── */
.bottom-bar {
  display: none;
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  padding: var(--space-3) var(--space-4);
  background: var(--bg-1);
  border-top: 1px solid var(--border);
  justify-content: space-between;
  align-items: center;
  gap: var(--space-3);
}

.bottom-info {
  font-size: 13px;
  color: var(--fg-1);
}

@media (max-width: 768px) {
  .builder-layout {
    flex-direction: column;
  }

  .sidebar {
    width: 100%;
    display: flex;
    gap: var(--space-3);
    overflow-x: auto;
  }

  .sidebar-section {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    margin-bottom: 0;
  }

  .sidebar-title {
    display: none;
  }

  .category-list {
    flex-direction: row;
  }

  .category-item {
    padding: 4px 10px;
    white-space: nowrap;
  }

  .config-drawer {
    width: 100%;
  }

  .bottom-bar {
    display: flex;
  }
}
</style>