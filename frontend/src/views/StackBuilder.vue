<template>
  <div class="stack-builder">

    <!-- Header -->
    <div class="sb-header">
      <h1 class="sb-title">Stack Builder</h1>
      <div class="sb-actions">
        <button class="btn btn-secondary" @click="preview" :disabled="previewLoading">
          {{ previewLoading ? 'Generating…' : 'Generate' }}
        </button>
        <button class="btn btn-primary" :disabled="deploying || !selectedServices.length" @click="deploy">
          {{ deploying ? 'Deploying…' : 'Deploy' }}
        </button>
      </div>
    </div>

    <!-- Main Area -->
    <div class="sb-layout">

      <!-- Sidebar Filters -->
      <div class="sb-sidebar">
        <div class="sb-filters">
          <div class="filter-label">Services</div>
          <div class="filter-pills">
            <button
              v-for="cat in categories"
              :key="cat.key"
              :class="['filter-pill', { active: activeCategory === cat.key }]"
              @click="activeCategory = activeCategory === cat.key ? '' : cat.key"
            >
              <span class="pill-icon">{{ cat.icon }}</span>
              <span class="pill-name">{{ cat.name }}</span>
              <span class="pill-count">{{ cat.count }}</span>
            </button>
          </div>
        </div>

        <div class="sb-search">
          <input
            v-model="search"
            placeholder="Search services..."
            class="sb-input"
          />
        </div>

        <div class="sb-stats">
          <span class="stat">{{ selectedServices.length }} selected</span>
          <span class="stat-divider">·</span>
          <span class="stat">{{ filteredServices.length }} shown</span>
        </div>
      </div>

      <!-- Service Grid -->
      <div class="sb-grid">
        <div
          v-for="svc in filteredServices"
          :key="svc.key"
          :class="['sb-card', { selected: pick[svc.key], running: LIVE_SERVICES.has(svc.key) }]"
          @click="toggle(svc.key)"
        >
          <div class="card-check">
            <div class="check-circle" :class="{ checked: pick[svc.key] }">
              <svg v-if="pick[svc.key]" viewBox="0 0 10 10" fill="none">
                <polyline points="2,5 4,7 8,3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
            </div>
          </div>

          <div class="card-icon">{{ svc.icon }}</div>

          <div class="card-body">
            <div class="card-header">
              <span class="card-name">{{ svc.display_name }}</span>
              <span v-if="LIVE_SERVICES.has(svc.key)" class="card-badge running">Running</span>
            </div>
            <div class="card-desc">{{ svc.description }}</div>
          </div>

          <div class="card-meta">
            <span v-if="svc.web_port" class="card-port">{{ svc.web_port }}</span>
            <span v-else class="card-port empty">—</span>
          </div>
        </div>

        <div v-if="!filteredServices.length" class="sb-empty">
          No services match your filter.
        </div>
      </div>
    </div>

    <!-- Config Drawer -->
    <div class="sb-drawer" :class="{ open: configOpen }">
      <div class="drawer-header">
        <h2>Configuration</h2>
        <button class="drawer-close" @click="configOpen = false">✕</button>
      </div>

      <div class="drawer-scroll">
        <div class="drawer-section">
          <div class="config-group">
            <label class="config-label">Domain</label>
            <input v-model="req.domain" placeholder="example.com" class="config-input" />
            <span class="config-hint">Apps served as sonarr.{{ req.domain || 'example.com' }}</span>
          </div>

          <div class="config-group">
            <label class="config-label">Config Root</label>
            <input v-model="req.config_root" placeholder="/home/stack/mediacenter/config" class="config-input" />
          </div>

          <div class="config-group">
            <label class="config-label">Media Root</label>
            <input v-model="req.media_root" placeholder="/mnt/media" class="config-input" />
            <span class="config-hint">Mounted as /data inside containers</span>
          </div>

          <div class="config-group">
            <label class="config-label">Timezone</label>
            <input v-model="req.timezone" placeholder="America/Los_Angeles" class="config-input" />
          </div>

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
        </div>

        <template v-if="pick['tailscale']">
          <div class="drawer-divider"></div>
          <div class="drawer-section-title">Tailscale</div>

          <div class="drawer-section">
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
          </div>
        </template>

        <template v-if="pick['tinyauth']">
          <div class="drawer-divider"></div>
          <div class="drawer-section-title">Tinyauth</div>

          <div class="drawer-section">
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
          </div>
        </template>

        <div class="drawer-divider"></div>
        <pre v-if="previewText" class="drawer-output">{{ previewText }}</pre>

        <div v-if="deployOutput" :class="['drawer-result', deployOk ? 'ok' : 'err']">
          <div class="result-status">{{ deployOk ? '✓ Deploy complete' : '✕ Deploy failed' }}</div>
          <pre class="result-text">{{ deployOutput }}</pre>
        </div>
      </div>
    </div>

    <!-- Mobile Bottom Bar -->
    <div v-if="selectedServices.length && !configOpen" class="sb-mobile-bar">
      <span class="mobile-count">{{ selectedServices.length }} services</span>
      <div class="mobile-actions">
        <button class="btn btn-secondary" @click="configOpen = true">Configure</button>
        <button class="btn btn-primary" :disabled="deploying" @click="deploy">Deploy</button>
      </div>
    </div>

    <!-- Backdrop -->
    <div v-if="configOpen" class="sb-backdrop" @click="configOpen = false"></div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch, inject } from 'vue'

const showToast = inject('showToast')

// State
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

// Storage
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

// Constants
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
  infra: { key: 'infra', name: 'Infra', icon: '⚙️' },
}

const LIVE_SERVICES = new Set([
  'traefik', 'plex', 'sonarr', 'radarr', 'prowlarr', 'qbittorrent', 'cloudflared',
])

// Computed
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

// Actions
function toggle(key) {
  pick[key] = !pick[key]
  localStorage.setItem('rad-stack-builder-pick', JSON.stringify({...pick}))
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

// API
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
/* Layout */
.stack-builder {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  padding-bottom: 60px;
}

.sb-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border);
  background: var(--bg-1);
}

.sb-title {
  font-size: 18px;
  font-weight: 700;
  margin: 0;
}

.sb-actions {
  display: flex;
  gap: var(--space-2);
}

.sb-layout {
  display: flex;
  gap: var(--space-4);
  padding: var(--space-4);
}

/* Sidebar */
.sb-sidebar {
  width: 180px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.filter-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--fg-2);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: var(--space-2);
}

.filter-pills {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.filter-pill {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: var(--radius-sm);
  background: transparent;
  border: none;
  cursor: pointer;
  text-align: left;
  transition: all 0.12s;
}

.filter-pill:hover {
  background: var(--bg-2);
}

.filter-pill.active {
  background: var(--accent);
  color: #fff;
}

.pill-icon {
  font-size: 12px;
}

.pill-name {
  font-size: 12px;
  font-weight: 500;
  flex: 1;
}

.pill-count {
  font-size: 10px;
  opacity: 0.7;
}

.sb-input {
  width: 100%;
  padding: 6px 10px;
  font-size: 12px;
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--fg-0);
}

.sb-input:focus {
  outline: none;
  border-color: var(--accent);
}

.sb-stats {
  font-size: 11px;
  color: var(--fg-2);
}

.stat-divider {
  margin: 0 4px;
}

/* Service Grid */
.sb-grid {
  flex: 1;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--space-2);
  align-content: start;
}

.sb-card {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3);
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  cursor: pointer;
  transition: all 0.15s;
}

.sb-card:hover {
  border-color: var(--border-strong);
  box-shadow: var(--shadow-1);
}

.sb-card.selected {
  border-color: var(--accent);
  background: var(--accent-subtle);
}

.sb-card.running {
  border-left: 3px solid var(--ok);
}

.sb-card.selected.running {
  border-left: 3px solid var(--ok);
}

.card-check {
  flex-shrink: 0;
}

.check-circle {
  width: 18px;
  height: 18px;
  border: 1.5px solid var(--border-strong);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}

.check-circle.checked {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}

.check-circle svg {
  width: 10px;
  height: 10px;
}

.card-icon {
  font-size: 20px;
  flex-shrink: 0;
}

.card-body {
  flex: 1;
  min-width: 0;
}

.card-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.card-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--fg-0);
}

.card-badge {
  font-size: 9px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 8px;
  background: var(--bg-2);
  color: var(--fg-2);
}

.card-badge.running {
  background: var(--ok-bg);
  color: var(--ok);
}

.card-desc {
  font-size: 11px;
  color: var(--fg-2);
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card-meta {
  flex-shrink: 0;
  text-align: right;
}

.card-port {
  font-size: 12px;
  font-family: var(--font-mono);
  color: var(--fg-1);
}

.card-port.empty {
  color: var(--fg-2);
}

.sb-empty {
  grid-column: 1 / -1;
  padding: var(--space-6);
  text-align: center;
  color: var(--fg-2);
  font-size: 13px;
}

/* Drawer */
.sb-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.3);
  z-index: 50;
}

.sb-drawer {
  position: fixed;
  right: 0;
  top: 0;
  bottom: 0;
  width: 380px;
  background: var(--bg-1);
  border-left: 1px solid var(--border);
  transform: translateX(100%);
  transition: transform 0.2s;
  z-index: 60;
  display: flex;
  flex-direction: column;
}

.sb-drawer.open {
  transform: translateX(0);
}

.drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.drawer-header h2 {
  font-size: 15px;
  font-weight: 600;
  margin: 0;
}

.drawer-close {
  background: none;
  border: none;
  font-size: 16px;
  cursor: pointer;
  color: var(--fg-2);
  padding: 4px;
}

.drawer-scroll {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-4);
}

.drawer-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.drawer-section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--fg-0);
  padding: 0 var(--space-4);
  margin-bottom: calc(-1 * var(--space-2));
}

.drawer-divider {
  height: 1px;
  background: var(--border);
  margin: var(--space-3) 0;
}

.config-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.config-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--fg-1);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.config-input {
  padding: 8px 10px;
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
  font-size: 11px;
  color: var(--fg-2);
}

.config-link {
  font-size: 11px;
  color: var(--accent);
}

.config-row {
  display: flex;
  gap: var(--space-3);
}

.config-row .config-group {
  flex: 1;
}

.user-row {
  display: flex;
  gap: var(--space-2);
}

.user-row .config-input {
  flex: 1;
}

.drawer-output {
  background: var(--bg-0);
  padding: var(--space-3);
  border-radius: var(--radius-sm);
  font-size: 10px;
  font-family: var(--font-mono);
  overflow-x: auto;
  max-height: 250px;
  white-space: pre;
}

.drawer-result {
  border-radius: var(--radius-sm);
  overflow: hidden;
}

.result-status {
  padding: var(--space-2) var(--space-3);
  font-size: 12px;
  font-weight: 600;
}

.drawer-result.ok .result-status {
  background: var(--ok-bg);
  color: var(--ok);
}

.drawer-result.err .result-status {
  background: var(--err-bg);
  color: var(--err);
}

.result-text {
  padding: var(--space-3);
  font-size: 10px;
  font-family: var(--font-mono);
  background: var(--bg-0);
  max-height: 180px;
  overflow-y: auto;
  white-space: pre;
}

/* Buttons */
.btn {
  padding: 6px 12px;
  font-size: 12px;
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
  background: var(--accent-hover);
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
  padding: 6px 10px;
  font-size: 11px;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Mobile */
.sb-mobile-bar {
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

.mobile-count {
  font-size: 12px;
  color: var(--fg-1);
}

.mobile-actions {
  display: flex;
  gap: var(--space-2);
}

/* Responsive */
@media (max-width: 768px) {
  .sb-layout {
    flex-direction: column;
  padding: var(--space-3);
  }

  .sb-sidebar {
    width: 100%;
    flex-direction: row;
    flex-wrap: wrap;
    gap: var(--space-2);
  }

  .filter-label {
    display: none;
  }

  .filter-pills {
    flex-direction: row;
    flex-wrap: wrap;
  }

  .sb-filters {
    flex: 1;
  }

  .sb-stats {
    width: 100%;
  }

  .sb-drawer {
    width: 100%;
  }

  .sb-mobile-bar {
    display: flex;
  }
}
</style>