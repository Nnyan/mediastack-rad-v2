<template>
  <div class="builder">

    <!-- ── Header ──────────────────────────────────────────────────────── -->
    <div class="builder-header">
      <div>
        <h1 class="page-title">Stack Builder</h1>
        <div class="header-sub">
          <span>{{ selectedServices.length }} service{{ selectedServices.length !== 1 ? 's' : '' }} selected</span>
          <span v-if="req.domain" class="header-sub-sep">·</span>
          <span v-if="req.domain">{{ req.domain }}</span>
        </div>
      </div>
      <div class="header-actions">
        <button class="btn-review" :disabled="previewLoading || !selectedServices.length" @click="preview">
          {{ previewLoading ? 'Generating…' : 'Review' }}
        </button>
        <button class="primary" :disabled="deploying || !selectedServices.length" @click="deploy">
          {{ deploying ? 'Deploying…' : 'Deploy stack →' }}
        </button>
      </div>
    </div>

    <!-- ── Two-column layout: config left, grid right ───────────────────── -->
    <div class="builder-layout">

      <!-- Left: config accordion -->
      <div class="config-panel">
        <div class="config-area">
          <!-- Port conflict banner -->
          <div v-if="portConflicts.length" class="port-conflict-banner">
            <div class="port-conflict-banner-head">
              <span class="port-conflict-icon">⚠</span>
              <span class="port-conflict-title">{{ portConflicts.length }} port conflict{{ portConflicts.length !== 1 ? 's' : '' }} detected</span>
              <span v-if="portsChecking" class="port-conflict-checking">checking…</span>
            </div>
            <div v-for="c in portConflicts" :key="c.service" class="port-conflict-row">
              <span class="port-conflict-svc">{{ svcName(c.service) }}</span>
              <span class="port-conflict-detail">
                port <strong>{{ c.port }}</strong> already used by
                <code>{{ c.conflict_with }}</code>
              </span>
              <button class="port-conflict-accept" @click="acceptPortSuggestion(c)">
                Use {{ c.suggested_port }} instead
              </button>
            </div>
          </div>

          <div class="config-heading">Configuration</div>

          <!-- Core settings — always visible -->
          <div class="cfg-section" :class="{ open: expanded.core }">
          <div class="cfg-head cfg-head-pinned">
            <span class="cfg-icon">⚙️</span>
            <span class="cfg-title">Core settings</span>
          </div>
          <div v-if="expanded.core" class="cfg-body">
            <div class="cfg-grid">
              <label class="cfg-field span2">
                <span class="cfg-label">Domain</span>
                <input v-model="req.domain" placeholder="nyrdalyrt.com" />
                <span class="cfg-hint">Apps served as sonarr.{{ req.domain || 'example.com' }}</span>
              </label>
              <label class="cfg-field span2">
                <span class="cfg-label">Config root</span>
                <input v-model="req.config_root" placeholder="/home/stack/mediacenter/config" />
              </label>
              <label class="cfg-field">
                <span class="cfg-label">Media root</span>
                <input v-model="req.media_root" placeholder="/mnt/media" />
                <span class="cfg-hint">Mounted as /data inside containers</span>
              </label>
              <label class="cfg-field">
                <span class="cfg-label">Timezone</span>
                <input v-model="req.timezone" placeholder="America/Los_Angeles" />
              </label>
              <label class="cfg-field">
                <span class="cfg-label">PUID</span>
                <input v-model.number="req.puid" type="number" />
              </label>
              <label class="cfg-field">
                <span class="cfg-label">PGID</span>
                <input v-model.number="req.pgid" type="number" />
              </label>
            </div>
          </div>
          </div>

          <!-- Cloudflare — credentials live in Settings → Secrets, no config needed here -->

          <!-- Tailscale — only when tailscale is selected -->
                    <template v-if="pick['tailscale']">
          <div class="cfg-section" :class="{ open: expanded.tailscale }">
          <div class="cfg-head" @click="toggleCfg('tailscale')">
            <span class="cfg-icon">🔗</span>
            <span class="cfg-title">Tailscale</span>
          </div>
          <div v-if="expanded.tailscale" class="cfg-body">
            <div class="cfg-grid">
              <label class="cfg-field span2">
                <span class="cfg-label">
                  Auth key
                  <a href="https://login.tailscale.com/admin/settings/keys" target="_blank" class="cfg-link">Tailscale admin ↗</a>
                </span>
                <input v-model="req.tailscale_auth_key" type="password" placeholder="tskey-auth-… (reusable, non-ephemeral)" />
                <span class="cfg-hint">Generate a reusable, non-ephemeral key — ephemeral keys expire and drop the node.</span>
              </label>
              <label class="cfg-field">
                <span class="cfg-label">Node hostname</span>
                <input v-model="req.tailscale_hostname" placeholder="mediastack" />
                <span class="cfg-hint">How this server appears in your tailnet</span>
              </label>
              <label class="cfg-field">
                <span class="cfg-label">Subnet routes</span>
                <input v-model="req.tailscale_routes" placeholder="172.20.0.0/16" />
                <span class="cfg-hint">Docker network CIDR — gives enrolled devices direct container access</span>
              </label>
            </div>
          </div>
          </div>
          </template>

          <!-- Tinyauth — only when tinyauth is selected -->
                    <template v-if="pick['tinyauth']">
          <div class="cfg-section" :class="{ open: expanded.tinyauth }">
          <div class="cfg-head" @click="toggleCfg('tinyauth')">
            <span class="cfg-icon">🔒</span>
            <span class="cfg-title">Tinyauth</span>
          </div>
          <div v-if="expanded.tinyauth" class="cfg-body">
            <div class="cfg-note cfg-note-purple">
              🔒 <strong>LAN users ({{ req.lan_subnet }}) pass through automatically.</strong>
              Only Tailscale and internet traffic is challenged.
            </div>
            <div class="cfg-grid">
              <label class="cfg-field">
                <span class="cfg-label">LAN subnet</span>
                <input v-model="req.lan_subnet" placeholder="10.0.0.0/22" />
                <span class="cfg-hint">Devices in this CIDR bypass Tinyauth entirely</span>
              </label>
              <label class="cfg-field">
                <span class="cfg-label">App URL</span>
                <input v-model="req.tinyauth_app_url" placeholder="https://auth.nyrdalyrt.com" />
                <span class="cfg-hint">⚠ Must be added as a public hostname in your CF Tunnel → forward to http://tinyauth:3000</span>
              </label>

              <label class="cfg-field span2">
                <span class="cfg-label">
                  Users
                  <button class="gen-btn" type="button" @click="generateCredentials">Generate admin</button>
                </span>
                <input v-model="req.tinyauth_users" placeholder="admin:$2b$10$..." />
                <span class="cfg-hint">Format: <code>username:bcrypt_hash</code> — click Generate admin or separate multiple users with commas</span>
              </label>
              <div v-if="generatedPassword" class="generated-password-box">
                <span class="gen-pw-label">
                  ⚠ Save this — not shown again
                  <button class="gen-pw-dismiss" @click="generatedPassword = ''">✕ dismiss</button>
                </span>
                <code class="gen-pw-value">{{ generatedPassword }}</code>
              </div>

            </div>
          </div>
          </div>
          </template>

          <!-- Plex — only when plex is selected -->
          <template v-if="pick['plex']">
          <div class="cfg-section" :class="{ open: expanded.plex }">
          <div class="cfg-head" @click="toggleCfg('plex')">
            <span class="cfg-icon">🎬</span>
            <span class="cfg-title">Plex</span>
            <span class="cfg-badge-mode">{{ plexMode === 'local' ? 'new server' : 'existing server' }}</span>
          </div>
          <div v-if="expanded.plex" class="cfg-body">
            <div class="mode-toggle">
              <button :class="['mode-btn', { active: plexMode === 'local' }]" @click="plexMode = 'local'">New Plex server</button>
              <button :class="['mode-btn', { active: plexMode === 'external' }]" @click="plexMode = 'external'">Link existing server</button>
            </div>

            <!-- New Plex server -->
            <div v-show="plexMode === 'local'">
              <div class="cfg-grid">
                <label class="cfg-field">
                  <span class="cfg-label">Server name</span>
                  <input v-model="req.plex_server_name" placeholder="My Plex Server" />
                  <span class="cfg-hint">Friendly name shown in Plex clients</span>
                </label>
                <label class="cfg-field">
                  <span class="cfg-label">
                    Plex Claim Token
                    <a href="https://plex.tv/claim" target="_blank" class="cfg-link">Get one ↗</a>
                  </span>
                  <input v-model="req.plex_claim" type="password" placeholder="claim-xxxxxxxxxxxxxxxxxxxx" />
                  <span class="cfg-hint">Links this server to your Plex account on first boot. Expires in 4 minutes — generate it just before deploying.</span>
                </label>
                <label class="cfg-field">
                  <span class="cfg-label">
                    X-Plex-Token
                    <a href="https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/" target="_blank" class="cfg-link">How to find ↗</a>
                  </span>
                  <input v-model="req.plex_token" type="password" placeholder="xxxxxxxxxxxxxxxxxxxx" />
                  <span class="cfg-hint">Your personal Plex auth token. Used by Sonarr, Radarr, Prowlarr and other apps to authenticate with this Plex server.</span>
                </label>
              </div>
            </div>

            <!-- Existing Plex server -->
            <div v-show="plexMode === 'external'">
              <div class="cfg-note cfg-note-info" style="margin-bottom: var(--space-3)">
                Plex will not be added to this stack. The IP address and token below will be passed to Sonarr, Radarr, Prowlarr, Bazarr and Seerr so they can connect to your existing server.
              </div>
              <div class="cfg-grid">
                <label class="cfg-field span2">
                  <span class="cfg-label">Plex server URL</span>
                  <input v-model="req.plex_url" placeholder="http://192.168.1.50:32400" />
                  <span class="cfg-hint">Use the local LAN IP for best performance. Port is usually 32400.</span>
                </label>
                <label class="cfg-field span2">
                  <span class="cfg-label">
                    X-Plex-Token
                    <a href="https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/" target="_blank" class="cfg-link">How to find ↗</a>
                  </span>
                  <input v-model="req.plex_token" type="password" placeholder="xxxxxxxxxxxxxxxxxxxx" />
                  <span class="cfg-hint">Your personal Plex auth token. In Plex Web: Settings → Troubleshooting → Show → X-Plex-Token. Passed to Sonarr, Radarr, Prowlarr, Bazarr and Seerr.</span>
                </label>
              </div>
            </div>

          </div>
          </div>
          </template>

          <!-- Add custom app — always visible below Core settings -->
          <div class="cfg-section" :class="{ open: expanded.custom }">
          <div class="cfg-head" @click="toggleCfg('custom')">
            <span class="cfg-icon">＋</span>
            <span class="cfg-title">Add custom app</span>
          </div>
          <div v-if="expanded.custom" class="cfg-body">
            <div class="tab-row">
              <button
                v-for="[t, label] in [['compose','Compose YAML'],['url','Image URL'],['file','Upload']]"
                :key="t" :class="['tab-btn', { active: addTab === t }]" @click="addTab = t"
              >{{ label }}</button>
            </div>
            <template v-if="addTab === 'compose'">
              <p class="cfg-hint custom-hint">Paste a <code>docker-compose.yml</code> fragment — it will be parsed and merged into your stack.</p>
              <textarea v-model="addInput" class="compose-textarea" placeholder="services:
  myapp:
    image: ghcr.io/author/myapp:latest
    ports:
      - &quot;8123:8123&quot;"></textarea>
            </template>
            <template v-else-if="addTab === 'url'">
              <p class="cfg-hint custom-hint">Enter a Docker Hub image name or full registry URL. Sensible defaults will be generated.</p>
              <input v-model="addInput" placeholder="lscr.io/linuxserver/heimdall  or  portainer/portainer-ce" class="url-input" />
            </template>
            <template v-else>
              <div class="file-drop">
                <div class="file-drop-icon">📄</div>
                <div class="file-drop-title">Drop a compose file here</div>
                <div class="file-drop-sub">or click to browse — .yml and .yaml supported</div>
              </div>
            </template>
            <!-- Parse result preview -->
            <div v-if="addResult" class="parse-result">
              <div class="parse-result-head">
                <span class="parse-result-title">
                  {{ addResult.services.length }} service{{ addResult.services.length !== 1 ? 's' : '' }} found
                </span>
                <button class="parse-confirm" @click="confirmCustomApp">
                  ✓ Add to stack
                </button>
              </div>
              <div v-for="svc in addResult.services" :key="svc.name" class="parse-svc">
                <span class="parse-svc-name">{{ svc.name }}</span>
                <span class="parse-svc-image">{{ svc.image }}</span>
                <span v-for="p in svc.ports" :key="p" class="parse-svc-port">{{ p }}</span>
              </div>
              <div v-if="customYaml" class="parse-confirmed">
                ✓ Will be included in next deploy
              </div>
            </div>

            <div class="custom-actions">
              <button class="btn-review" :disabled="addParsing" @click="parseAndAdd">
                {{ addParsing ? 'Fetching…' : 'Parse & add' }}
              </button>
            </div>
          </div>
          </div>

          <!-- Per-service extra env vars — shown when any service is selected -->
          <div v-if="selectedServices.length" class="cfg-section" :class="{ open: expanded.extraenv }">
          <div class="cfg-head" @click="toggleCfg('extraenv')">
            <span class="cfg-icon">🔧</span>
            <span class="cfg-title">Variables</span>
          </div>
          <div v-if="expanded.extraenv" class="cfg-body">
            <p class="cfg-hint" style="margin: 6px 0 10px; font-style: normal; font-size: 11px;">
              Add arbitrary environment variables to any selected service.
              These are merged last and override catalog defaults.
            </p>
            <div v-for="key in selectedServices" :key="key" class="extraenv-service">
              <div class="extraenv-service-head" @click="toggleExtraEnv(key)">
                <span class="extraenv-icon">{{ svcByKey[key]?.icon || '📦' }}</span>
                <span class="extraenv-name">{{ svcName(key) }}</span>
                <span v-if="(extraEnvRows[key]||[]).filter(r=>r.k).length"
                  class="extraenv-count">{{ (extraEnvRows[key]||[]).filter(r=>r.k).length }} var{{ (extraEnvRows[key]||[]).filter(r=>r.k).length !== 1 ? 's' : '' }}</span>
                <span class="extraenv-chevron" :class="{ open: extraEnvOpen[key] }">›</span>
              </div>
              <div v-if="extraEnvOpen[key]" class="extraenv-rows">
                <div v-for="(row, idx) in (extraEnvRows[key] ||= [])" :key="idx" class="extraenv-row">
                  <input v-model="row.k" placeholder="VAR_NAME" class="extraenv-key" @keydown.tab.prevent="addEnvRow(key)" />
                  <span class="extraenv-eq">=</span>
                  <input v-model="row.v" placeholder="value" class="extraenv-val" />
                  <button class="extraenv-rm" @click="removeEnvRow(key, idx)">✕</button>
                </div>
                <button class="extraenv-add" @click="addEnvRow(key)">+ Add variable</button>
              </div>
            </div>
          </div>
          </div>


        </div>
      </div><!-- /config-panel -->

      <!-- Right: service grid -->
      <div class="grid-panel">

        <!-- Search under title -->
        <div class="search-wrap">
          <span class="search-icon">🔍</span>
          <input v-model="search" placeholder="Search services…" class="search-input" />
        </div>

        <!-- Service grid — compact single-line tiles, fixed 4 columns -->
        <div class="service-grid">
          <button
            v-for="svc in filteredServices"
            :key="svc.key"
            :class="['tile', tileClass(svc.key)]"
            
            @click="toggle(svc.key)"
          >
            <span class="tile-icon">{{ svc.icon }}</span>
            <span class="tile-name">{{ svc.display_name }}</span>
            <span v-if="liveServices.has(svc.key)" class="tile-live">●</span>
            <span v-if="portOverrides[svc.key]" class="tile-port-override">:{{ portOverrides[svc.key] }}</span>
          </button>

        </div>

      </div><!-- /grid-panel -->

    </div><!-- /builder-layout -->

  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, watch, inject } from 'vue'

const showToast = inject('showToast')

// ── State ──────────────────────────────────────────────────────────────────
const rawCatalog   = ref({})
const pick         = reactive(JSON.parse(localStorage.getItem('rad-stack-builder-pick') || '{}'))
const search       = ref('')
const activeFilter = ref('')
// Plain reactive object — boolean per section. More reliable than reactive(Set)
// because Vue 3 template compiler tracks plain property reads, not Set.has() calls.
const expanded = reactive({
  core: true, cloudflare: false, tailscale: false,
  tinyauth: false, plex: false, custom: true, extraenv: false, deploy: true,
})
const plexMode     = ref('local')
const addTab       = ref('compose')
const addInput     = ref('')
const portOverrides  = reactive({})   // { service_key: override_port }
const extraEnvOpen   = reactive({})   // { service_key: bool } — expand env panel
const extraEnvRows   = reactive({})   // { service_key: [{k:'',v:''},...] }
const portConflicts  = ref([])        // [{service, port, conflict_with, suggested_port}]
const portsChecking  = ref(false)
const addParsing   = ref(false)
const addResult    = ref(null)   // { yaml, services } from backend
const customYaml   = ref('')     // confirmed YAML to include in deploy
const previewText  = ref('')
const previewLoading = ref(false)
const deployOutput    = ref('')
const deployOk        = ref(false)
const deploying       = ref(false)
const deployConflicts = ref([])   // container names blocking the deploy

// ── Persistence ────────────────────────────────────────────────────────────
const STORAGE_KEY      = 'rad-stack-builder-v3'
const STORAGE_KEY_PREV = 'rad-stack-builder-v2'
const defaults = {
  domain: '', timezone: 'America/Los_Angeles', puid: 1000, pgid: 1000,
  config_root: '/home/stack/mediacenter/config',
  media_root: '/mnt/media',
  external_plex_url: '',
  plex_server_name: '',
  plex_url: '',
  plex_token: '',
  // Credentials (CF token, tunnel token, Plex claim, Tinyauth secrets)
  // are managed in Settings → Secrets, not stored here
  tailscale_auth_key: '', tailscale_routes: '', tailscale_hostname: 'mediastack',
  tinyauth_users: '', tinyauth_app_url: '',
  lan_subnet: '10.0.0.0/22',
}
// Migrate settings from previous key if v3 is empty
let _stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null')
if (!_stored || Object.keys(_stored).length === 0) {
  const _prev = JSON.parse(localStorage.getItem(STORAGE_KEY_PREV) || '{}')
  if (Object.keys(_prev).length > 0) {
    _stored = _prev
    localStorage.setItem(STORAGE_KEY, JSON.stringify(_stored))
  }
}
const stored = _stored || {}
const req = reactive({ ...defaults, ...stored })

// Sensitive fields that must never be persisted to localStorage.
const SENSITIVE_FIELDS = new Set([
  'tailscale_auth_key', 'tinyauth_users', 'plex_token', 'plex_claim',
])

function sanitizeForStorage(v) {
  const safe = { ...v }
  for (const key of SENSITIVE_FIELDS) {
    delete safe[key]
  }
  return safe
}

watch(req, v => localStorage.setItem(STORAGE_KEY, JSON.stringify(sanitizeForStorage(v))), { deep: true })
watch(pick,   v => localStorage.setItem('rad-stack-builder-pick', JSON.stringify({...v})), { deep: true })

// ── Constants ──────────────────────────────────────────────────────────────
const TAG_LABELS = {
  media:       'Media',
  indexers:    'Management',
  downloaders: 'Download',
  requests:    'Requests',
  infra:       'Infrastructure',
}

const CAT_COLORS = {
  media:       { bg: 'rgba(219,39,119,0.07)', border: 'rgba(219,39,119,0.3)', text: 'var(--pink)' },
  indexers:    { bg: 'rgba(124,58,237,0.07)', border: 'rgba(124,58,237,0.3)', text: 'var(--purple)' },
  downloaders: { bg: 'rgba(37,99,235,0.07)',  border: 'rgba(37,99,235,0.3)',  text: 'var(--blue)' },
  requests:    { bg: 'rgba(234,88,12,0.07)',  border: 'rgba(234,88,12,0.3)',  text: 'var(--orange)' },
  infra:       { bg: 'rgba(8,145,178,0.07)',  border: 'rgba(8,145,178,0.3)',  text: 'var(--teal)' },
}

const SHORT_DESCS = {
  plex: 'Media server', jellyfin: 'Open-source media server',
  sonarr: 'TV manager', radarr: 'Movie manager', lidarr: 'Music manager',
  readarr: 'Books & audiobooks', bazarr: 'Subtitle manager', prowlarr: 'Index manager',
  qbittorrent: 'BitTorrent client', sabnzbd: 'Usenet downloader', nzbget: 'Usenet (lite)',
  seerr: 'Request manager (Plex/Jellyfin/Emby)',  // replaces Overseerr + Jellyseerr
  traefik: 'Reverse proxy & HTTPS', tinyauth: 'Auth gateway',
  tailscale: 'Private VPN mesh', cloudflared: 'Public tunnel',
}

const ICONS = {
  plex: '🎬', jellyfin: '🎞️', sonarr: '📺', radarr: '🎥', lidarr: '🎵',
  readarr: '📚', bazarr: '💬', prowlarr: '🔍', qbittorrent: '⬇️',
  sabnzbd: '📰', nzbget: '📥', seerr: '🙋',
  traefik: '🔀', tinyauth: '🔒', tailscale: '🔗', cloudflared: '☁️',
}

// Set for O(1) lookup instead of Array.includes()
// Keyed by container name — assumes container name === service key, which holds
// for compose-managed stacks where the service name is the container name.
const liveServices = ref(new Set())

async function loadRunningServices() {
  try {
    const running = await fetch('/api/containers/running').then(r => r.json())
    liveServices.value = new Set(Array.isArray(running) ? running : [])
  } catch (e) {
    console.warn('Could not load running services:', e)
  }
}

// ── Computed ───────────────────────────────────────────────────────────────
const flatServices = computed(() => {
  const out = []
  for (const [cat, svcs] of Object.entries(rawCatalog.value)) {
    for (const svc of svcs) {
      out.push({
        ...svc,
        category: cat,
        icon: ICONS[svc.key] || '📦',
        short_desc: SHORT_DESCS[svc.key] || svc.description,
      })
    }
  }
  return out
})

// Lookup map: key → service. Avoids repeated .find() calls in helpers.
const svcByKey = computed(() => {
  const map = {}
  for (const svc of flatServices.value) map[svc.key] = svc
  return map
})

const filteredServices = computed(() => {
  const q = search.value.toLowerCase()
  const filtered = flatServices.value.filter(svc => {
    if (activeFilter.value && svc.category !== activeFilter.value) return false
    if (!q) return true
    return (
      svc.display_name.toLowerCase().includes(q) ||
      (svc.short_desc || '').toLowerCase().includes(q) ||
      TAG_LABELS[svc.category]?.toLowerCase().includes(q)
    )
  })
  // Order: live (installed+running) first, then selected, then rest — each group alpha
  const rank = svc => liveServices.value.has(svc.key) ? 0 : pick[svc.key] ? 1 : 2
  return [...filtered].sort((a, b) => {
    const rd = rank(a) - rank(b)
    if (rd !== 0) return rd
    return a.display_name.localeCompare(b.display_name)
  })
})

const selectedServices = computed(() =>
  Object.entries(pick).filter(([, on]) => on).map(([k]) => k)
)

// ── Style helpers — consistent: all take category or key via svcByKey ──────
function catColors(cat)    { return CAT_COLORS[cat] || { bg: 'var(--accent-subtle)', border: 'var(--accent-dim)', text: 'var(--accent)' } }
function tagStyle(cat)     { const c = catColors(cat); return { background: c.bg, color: c.text, borderColor: c.border } }
function tileStyle(cat)    { const c = catColors(cat); return { '--tc': c.text, '--tc-bg': c.bg } }
function tileClass(key)   {
  if (liveServices.value.has(key) && pick[key]) return 'tile-live-on'
  if (pick[key]) return 'tile-selected'
  return ''
}
function svcPillStyle(key) { const c = catColors(svcByKey.value[key]?.category); return { background: c.bg, color: c.text, borderColor: c.border } }
function svcName(key)      { return svcByKey.value[key]?.display_name || key }

// ── Actions ────────────────────────────────────────────────────────────────
// Map service key → config section id (only services that have a config section)
const SERVICE_SECTION = { cloudflared: 'cloudflare', tailscale: 'tailscale', tinyauth: 'tinyauth', plex: 'plex' }

function toggle(key) {
  pick[key] = !pick[key]
  // Auto-open the config section when a service is selected,
  // auto-close it when deselected (unless it was already open)
  const section = SERVICE_SECTION[key]
  if (section) {
    expanded[section] = pick[key]
  }
}

// camelCase throughout — was mixed snake_case/camelCase previously
function toggleCfg(id) {
  expanded[id] = !expanded[id]
}

// ── Tinyauth credential generators ────────────────────────────────────────
const generatedPassword = ref('')

async function generateCredentials() {
  // Random 16-char password: letters + digits, no ambiguous chars
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
    if (!r.ok) throw new Error(await r.text())
    const { hash } = await r.json()
    req.tinyauth_users = `admin:${hash}`
    generatedPassword.value = password
    showToast('Credentials generated — save the password shown below', 'warn', 8000)
  } catch (e) {
    showToast(`Generate failed: ${e.message}`, 'err')
  }
}

async function parseAndAdd() {
  const content = addInput.value.trim()
  if (!content) { showToast('Enter a URL or image name first', 'warn'); return }

  addParsing.value = true
  addResult.value  = null
  try {
    const r = await fetch('/api/custom-app/parse', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: addTab.value, content }),
    })
    if (!r.ok) {
      const msg = await r.text()
      showToast(msg, 'err', 6000)
      return
    }
    addResult.value = await r.json()
    showToast(`Parsed — ${addResult.value.services.length} service(s) found`)
  } catch (e) {
    showToast(`Parse failed: ${e.message}`, 'err')
  } finally {
    addParsing.value = false
  }
}

function confirmCustomApp() {
  customYaml.value = addResult.value?.yaml || ''
  showToast('Custom app added to stack — click Deploy to apply')
}

// ── Port conflict check ───────────────────────────────────────────────────────
let _portCheckTimer = null
function schedulePortCheck() {
  clearTimeout(_portCheckTimer)
  _portCheckTimer = setTimeout(checkPorts, 600)
}

async function checkPorts() {
  if (!selectedServices.value.length) { portConflicts.value = []; return }
  portsChecking.value = true
  try {
    const r = await fetch('/api/stack/port-check', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildRequest()),
    })
    if (r.ok) {
      const data = await r.json()
      portConflicts.value = data.conflicts || []
    }
  } catch (e) {
    console.warn('Port check failed:', e)
  } finally {
    portsChecking.value = false
  }
}

function acceptPortSuggestion(conflict) {
  portOverrides[conflict.service] = conflict.suggested_port
  // Remove this conflict from the list optimistically
  portConflicts.value = portConflicts.value.filter(c => c.service !== conflict.service)
  // Re-check with the new override applied
  schedulePortCheck()
  showToast(`Port changed: ${conflict.service} → ${conflict.suggested_port}`)
}

// ── API ────────────────────────────────────────────────────────────────────
async function loadCatalog() {
  try {
    rawCatalog.value = await fetch('/api/catalog').then(r => r.json())
    if (Object.keys(pick).length === 0) {
      ['traefik', 'prowlarr', 'sonarr', 'radarr', 'bazarr', 'seerr',
       'qbittorrent', 'plex', 'cloudflared'].forEach(k => { pick[k] = true })
    }
  } catch (e) {
    showToast('Failed to load catalog — check the backend is running', 'err')
  }
}

function buildRequest() {
  return {
    domain:                 req.domain,
    timezone:               req.timezone,
    puid:                   req.puid,
    pgid:                   req.pgid,
    config_root:            req.config_root,
    media_root:             req.media_root,
    // Credentials come from .env on the server (managed in Settings → Secrets)
    plex_server_name:          req.plex_server_name,
    plex_url:                  req.plex_url || req.external_plex_url || undefined,
    plex_token:                req.plex_token || undefined,
    external_plex_url:         req.external_plex_url || undefined,
    tailscale_auth_key:     req.tailscale_auth_key,
    tailscale_routes:       req.tailscale_routes,
    tailscale_hostname:     req.tailscale_hostname,
    tinyauth_enabled:       !!pick['tinyauth'],
    tinyauth_users:         req.tinyauth_users,
    tinyauth_app_url:       req.tinyauth_app_url,
    lan_subnet:             req.lan_subnet,
    services:               selectedServices.value.map(k => ({
      key: k, enabled: true,
      port_override: portOverrides[k] || undefined,
      extra_env:    {},
    })),
    custom_yaml:            customYaml.value || undefined,
  }
}

async function preview() {
  previewLoading.value = true
  previewText.value = ''
  expanded.deploy = true
  try {
    const r = await fetch('/api/stack/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildRequest()),
    })
    if (!r.ok) throw new Error(await r.text())
    const data = await r.json()
    previewText.value = data.yaml
    const warnCount = data.warnings?.length || 0
    showToast(`Generated — ${data.bytes} bytes${warnCount ? ` · ${warnCount} warning(s)` : ''}`)
  } catch (e) {
    const msg = typeof e === 'object' && e.errors
      ? e.errors.map(x => x.message).join(' | ')
      : e.message || String(e)
    showToast(`Generate failed: ${msg}`, 'err', 8000)
  } finally {
    previewLoading.value = false
  }
}

async function purgeAndRetry() {
  const names = deployConflicts.value
  if (!names.length) return
  deploying.value = true
  deployOutput.value = ''
  try {
    const r = await fetch('/api/stack/purge-conflicts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ names }),
    })
    const data = await r.json()
    if (data.errors?.length) {
      showToast(`Purge errors: ${data.errors.join('; ')}`, 'err', 7000)
      deploying.value = false
      return
    }
    showToast(`Removed: ${data.removed.join(', ')} — redeploying…`, 'ok', 4000)
    deployConflicts.value = []
    deploying.value = false
    await deploy()
  } catch (e) {
    showToast(`Purge failed: ${e.message}`, 'err')
    deploying.value = false
  }
}

async function deploy() {
  if (!confirm('Deploy this stack? Running containers may be recreated.')) return
  deploying.value = true
  deployOutput.value = ''
  expanded.deploy = true
  try {
    const r = await fetch('/api/stack/deploy', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildRequest()),
    })
    const data = await r.json()
    if (!r.ok) {
      deployOk.value = false
      const lines = (data.errors || []).map(e => `✗  ${e.message || e}`)
      deployOutput.value = lines.length
        ? lines.join('\n')
        : (data.message || data.detail || `HTTP ${r.status}`)
      showToast(data.message || 'Deploy blocked — fix errors below', 'err', 7000)
      return
    }
    deployOk.value = data.ok
    deployConflicts.value = data.conflicts || []
    deployOutput.value = [data.stdout, data.stderr ? '--- stderr ---\n' + data.stderr : '']
      .filter(Boolean).join('\n').trim()
    if (data.ok) {
      showToast('Deploy complete', 'ok', 5000)
      // Clear selections — deployed stack is now running; live dots show status
      Object.keys(pick).forEach(k => { pick[k] = false })
      localStorage.setItem('rad-stack-builder-pick', JSON.stringify({}))
    } else if (deployConflicts.value.length) {
      showToast(`${deployConflicts.value.length} container conflict(s) — click "Remove conflicts & retry"`, 'warn', 8000)
    } else {
      showToast('Deploy failed — see output below', 'err', 5000)
    }
  } catch (e) {
    deployOk.value = false
    deployOutput.value = String(e)
    showToast(`Deploy error: ${e.message}`, 'err')
  } finally {
    deploying.value = false
  }
}

// Auto-expand the config section when a service with one is first selected
const SERVICE_CFG = { cloudflared: 'cloudflare', tailscale: 'tailscale', tinyauth: 'tinyauth', plex: 'plex' }
watch(() => ({ ...pick }), (cur, prev) => {
  for (const [svcKey, cfgId] of Object.entries(SERVICE_CFG)) {
    if (cur[svcKey] && !prev?.[svcKey]) expanded[cfgId] = true
  }
})

watch(addInput, () => { addResult.value = null })
watch(addTab,   () => { addResult.value = null; addInput.value = '' })
watch(selectedServices, schedulePortCheck)

let runningPollTimer = null

onMounted(() => {
  loadCatalog()
  loadRunningServices()
  runningPollTimer = setInterval(loadRunningServices, 15000)
})

onUnmounted(() => {
  if (runningPollTimer) clearInterval(runningPollTimer)
})
</script>

<style scoped>
/* ── Layout ─────────────────────────────────────────────────────────────── */
.builder { padding-bottom: 80px; }

.builder-layout {
  display: flex;
  flex-direction: row;
  gap: 24px;
  align-items: flex-start;
}
.config-panel {
  flex: 0 0 280px;
  min-width: 0;
}
.grid-panel {
  flex: 1;
  min-width: 0;
}

/* ── Header ─────────────────────────────────────────────────────────────── */
.builder-header { margin-bottom: var(--space-3); display: flex; align-items: center; justify-content: space-between; }
.header-actions { display: flex; align-items: center; gap: var(--space-2); }
.header-sub     { font-size: 12px; color: var(--fg-2); margin-top: 2px; display: flex; align-items: center; gap: 5px; }
.header-sub-sep { opacity: 0.5; }
.btn-review     { font-size: 13.5px; font-weight: 600; font-family: var(--font-sans); padding: 6px 14px; border-radius: var(--radius); border: 1.5px solid var(--accent); background: transparent; color: var(--accent); cursor: pointer; transition: background 0.13s; }
.btn-review:hover:not(:disabled) { background: var(--accent-subtle); }
.btn-review:disabled { opacity: 0.4; cursor: not-allowed; }

/* ── Filter row ─────────────────────────────────────────────────────────── */
.search-wrap { position: relative; margin-bottom: var(--space-3); }
.search-icon { position: absolute; left: 10px; top: 50%; transform: translateY(-50%); font-size: 13px; }
.search-input {
  width: 100%;
  padding: 7px 10px 7px 30px;
  font-family: var(--font-sans);
  font-size: 13px;
  background: var(--bg-0);
  border: 1.5px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--fg-0);
  box-sizing: border-box;
}
.search-input:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-dim); }

/* ── Service grid ───────────────────────────────────────────────────────── */
/* ── Service grid — compact fixed-column layout ──────────────────────────── */
.service-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 4px;
  margin-bottom: var(--space-4);
}

/* Single-line tile: icon · name · live dot */
.tile {
  --tc:    var(--accent);
  --tc-bg: var(--accent-subtle);
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 9px;
  background: var(--bg-0);
  border: 1.5px solid transparent;
  border-radius: var(--radius-sm);
  text-align: left;
  cursor: pointer;
  transition: background 0.12s, border-color 0.12s;
  font-family: var(--font-sans);
  min-width: 0;
}
.tile:hover { background: var(--bg-2); border-color: var(--border); }
.tile.on    { background: var(--accent-subtle); border-color: var(--accent); }

.tile-icon  { font-size: 13px; line-height: 1; flex-shrink: 0; }
.tile-name  {
  font-size: 12.5px; font-weight: 600; color: var(--fg-0);
  letter-spacing: -0.01em; flex: 1; min-width: 0;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.tile.on .tile-name { color: var(--accent); }
.tile-live  { font-size: 11px; color: #16a34a; flex-shrink: 0; text-shadow: 0 0 6px rgba(22,163,74,0.9), 0 0 12px rgba(22,163,74,0.5); line-height: 1; }
.tile-port-override {
  font-family: var(--font-mono); font-size: 9px;
  color: var(--warn); flex-shrink: 0;
}



/* ── Config area ────────────────────────────────────────────────────────── */
.config-area    { display: flex; flex-direction: column; gap: 6px; }
.config-heading {
  font-size: 11px; font-weight: 700;
  color: var(--fg-2); text-transform: uppercase;
  letter-spacing: 0.08em; margin-bottom: 6px;
}

/* CfgSection — styles for the inline component template */
.cfg-section      { background: var(--bg-1); border: 1.5px solid var(--border); border-radius: var(--radius); overflow: hidden; transition: box-shadow 0.13s; }
.cfg-section.open { box-shadow: var(--shadow-1); }
.cfg-head         { display: flex; align-items: center; gap: 8px; padding: 6px 12px; cursor: pointer; user-select: none; }
.cfg-head:hover   { background: var(--bg-2); }
.cfg-icon         { font-size: 13px; }
.cfg-title        { font-size: 12.5px; font-weight: 600; color: var(--fg-0); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; flex: 1; }
/* cfg-badge removed */
.cfg-badge-mode   { font-size: 9px; font-weight: 600; color: var(--fg-2); background: var(--bg-2); padding: 1px 6px; border-radius: 20px; border: 1px solid var(--border); white-space: nowrap; flex-shrink: 0; }
.cfg-head-pinned  { cursor: default; }
.cfg-head-pinned:hover { background: var(--bg-1); }
.cfg-chevron      { color: var(--fg-2); font-size: 16px; transition: transform 0.13s; display: inline-block; line-height: 1; }
.cfg-chevron.open { transform: rotate(90deg); }


.cfg-body         { padding: 2px 12px 8px; border-top: 1px solid var(--border); }
.cfg-body input   { padding: 2px 6px; font-size: 10px; }

.cfg-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 5px; margin-top: 6px; }
.cfg-field        { display: flex; flex-direction: column; gap: 1px; min-width: 0; overflow: hidden; }
.cfg-field.span2  { grid-column: span 2; }
.cfg-field .cfg-label:empty, .cfg-label:only-child:empty { visibility: hidden; }
.cfg-label        { font-size: 9.5px; font-weight: 600; color: var(--fg-1); display: flex; align-items: center; gap: 6px; justify-content: space-between; min-width: 0; width: 100%; }
.cfg-link         { font-size: 11px; color: var(--accent); margin-left: auto; text-decoration: none; }
.cfg-link:hover   { text-decoration: underline; }

/* Generate buttons inside label rows */
.gen-btn {
  font-size: 10px; font-weight: 600; font-family: var(--font-sans);
  padding: 1px 8px; border-radius: 20px; cursor: pointer;
  background: var(--accent-subtle); color: var(--accent);
  border: 1px solid var(--accent-dim); transition: all 0.13s;
  flex-shrink: 0; white-space: nowrap;
}
.gen-btn:hover { background: var(--accent); color: #fff; }

/* Generated password reveal box */
.generated-password-box {
  grid-column: span 2;
  padding: 7px 10px; border-radius: 6px;
  background: var(--warn-bg); border: 1.5px solid rgba(217,119,6,0.3);
  min-width: 0; overflow: hidden;
}
.gen-pw-label  { display: flex; align-items: center; justify-content: space-between; font-size: 11px; color: var(--warn); font-weight: 600; margin-bottom: 4px; }
.gen-pw-value  { display: block; font-family: var(--font-mono); font-size: 12px; color: var(--fg-0); background: var(--bg-1); padding: 4px 8px; border-radius: 4px; border: 1px solid var(--border); word-break: break-all; width: 100%; box-sizing: border-box; }
.gen-pw-dismiss { font-size: 10px; color: var(--fg-2); background: none; border: none; cursor: pointer; }
.gen-pw-dismiss:hover { color: var(--fg-0); }
.cfg-hint         { font-size: 9px; color: var(--fg-2); line-height: 1.25; font-style: italic; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cfg-hint code    { font-family: var(--font-mono); font-size: 9.5px; background: var(--bg-2); padding: 1px 4px; border-radius: 3px; }

.cfg-note          { font-size: 10.5px; border-radius: 5px; padding: 4px 9px; line-height: 1.35; margin-top: 5px; }
.cfg-note-purple   { background: var(--accent-subtle); color: var(--fg-1); border: 1px solid var(--accent-dim); }
.cfg-note-pink     { background: rgba(219,39,119,0.05); color: var(--fg-1); border: 1px solid rgba(219,39,119,0.15); }
.cfg-note-neutral  { background: var(--bg-0); color: var(--fg-1); border: 1px solid var(--border); }

/* Plex mode toggle */
.mode-toggle { display: flex; background: var(--bg-0); border-radius: 6px; padding: 2px; gap: 2px; margin-top: 5px; }
.mode-btn    { flex: 1; padding: 3px 8px; border-radius: 4px; font-family: var(--font-sans); font-size: 11.5px; font-weight: 500; border: none; background: transparent; color: var(--fg-2); cursor: pointer; transition: all 0.13s; }
.mode-btn.active { background: var(--bg-1); color: var(--fg-0); box-shadow: var(--shadow-1); }

/* TOTP toggle */
.toggle-field  { flex-direction: column; gap: var(--space-2); }
.toggle        { display: flex; align-items: center; gap: var(--space-2); cursor: pointer; user-select: none; }
.toggle input  { display: none; }
.toggle-track  { width: 34px; height: 19px; border-radius: 10px; background: var(--border-strong); position: relative; flex-shrink: 0; transition: background 0.15s; }
.toggle-track::after { content: ''; position: absolute; top: 2.5px; left: 2.5px; width: 14px; height: 14px; border-radius: 50%; background: #fff; transition: transform 0.15s; }
.toggle input:checked ~ .toggle-track            { background: var(--accent); }
.toggle input:checked ~ .toggle-track::after     { transform: translateX(15px); }
.toggle-label  { font-size: 12px; color: var(--fg-1); }

/* Custom app section */
.tab-row       { display: flex; background: var(--bg-0); border-radius: 7px; padding: 3px; gap: 2px; margin-top: 10px; margin-bottom: 12px; }
.tab-btn       { flex: 1; padding: 5px 8px; border-radius: 5px; border: none; font-family: var(--font-sans); font-size: 12px; font-weight: 500; cursor: pointer; background: transparent; color: var(--fg-2); transition: all 0.13s; }
.tab-btn.active { background: var(--bg-1); color: var(--fg-0); box-shadow: var(--shadow-1); }
.custom-hint   { margin: 0 0 8px; }
.custom-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 12px; }
.compose-textarea { font-family: var(--font-mono); font-size: 11.5px; width: 100%; height: 160px; resize: vertical; background: #0e0f14; color: #e8eaf5; border: 1.5px solid #252a3d; border-radius: 7px; padding: 10px 12px; outline: none; box-sizing: border-box; line-height: 1.6; }
.url-input     { font-family: var(--font-mono); font-size: 12px; width: 100%; background: var(--bg-1); border: 1.5px solid var(--border); border-radius: 6px; padding: 8px 10px; outline: none; color: var(--fg-0); }
.file-drop     { border: 2px dashed var(--border); border-radius: 9px; padding: 28px 20px; text-align: center; background: var(--bg-0); cursor: pointer; margin-top: 8px; }
.file-drop-icon  { font-size: 26px; margin-bottom: 6px; }
.file-drop-title { font-size: 13.5px; font-weight: 600; color: var(--fg-0); margin-bottom: 3px; }
.file-drop-sub   { font-size: 12px; color: var(--fg-2); }

/* Parse result preview */
.parse-result {
  margin-top: 12px;
  border: 1.5px solid var(--ok);
  border-radius: 7px;
  overflow: hidden;
  background: var(--ok-bg);
}
.parse-result-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 7px 12px;
  background: var(--ok-bg);
  border-bottom: 1px solid rgba(22,163,74,0.15);
}
.parse-result-title { font-size: 12px; font-weight: 600; color: var(--ok); }
.parse-confirm {
  font-size: 11.5px; font-weight: 600; font-family: var(--font-sans);
  padding: 3px 10px; border-radius: 5px;
  background: var(--ok); color: #fff; border: none; cursor: pointer;
}
.parse-svc {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  padding: 5px 12px; border-top: 1px solid rgba(22,163,74,0.1);
  font-size: 11.5px;
}
.parse-svc-name  { font-weight: 700; color: var(--fg-0); }
.parse-svc-image { font-family: var(--font-mono); font-size: 10.5px; color: var(--fg-2); flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.parse-svc-port  { font-family: var(--font-mono); font-size: 9.5px; background: var(--bg-2); border: 1px solid var(--border); border-radius: 4px; padding: 1px 5px; color: var(--fg-2); }
.parse-confirmed { padding: 5px 12px; font-size: 11px; font-weight: 600; color: var(--ok); border-top: 1px solid rgba(22,163,74,0.15); }

/* Deploy area */

.deploy-btn    { font-size: 11.5px; padding: 4px 10px; white-space: nowrap; }
.output        { max-height: 380px; overflow: auto; background: var(--bg-0); padding: var(--space-3); border-radius: var(--radius); font-size: 12px; line-height: 1.4; white-space: pre-wrap; word-break: break-word; border: 1px solid var(--border); margin: 0; }
.output-block  { border-radius: var(--radius); overflow: hidden; margin-top: var(--space-2); }
.output-label  { padding: 6px 12px; font-size: 12px; font-weight: 600; }
.output-block.ok  .output-label { background: var(--ok-bg);  color: var(--ok);  }
.output-block.err .output-label { background: var(--err-bg); color: var(--err); }
.output-block .output { border-top: none; border-radius: 0; }

/* Container name conflict banner (deploy-time) */
.conflict-banner {
  margin-top: var(--space-3);
  border: 1.5px solid rgba(217,119,6,0.4);
  border-radius: var(--radius);
  overflow: hidden;
  background: var(--warn-bg);
}
.conflict-banner-head {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid rgba(217,119,6,0.15);
}
.conflict-icon  { font-size: 14px; color: var(--warn); }
.conflict-title { font-size: 12px; font-weight: 600; color: var(--warn); }
.conflict-names {
  display: flex; flex-wrap: wrap; gap: 5px;
  padding: 8px 12px;
}
.conflict-name {
  font-family: var(--font-mono); font-size: 11.5px;
  background: var(--bg-1); border: 1px solid var(--border);
  border-radius: 4px; padding: 2px 7px; color: var(--fg-0);
}
.conflict-actions {
  display: flex; align-items: center; justify-content: space-between;
  gap: 10px; flex-wrap: wrap;
  padding: 8px 12px;
  border-top: 1px solid rgba(217,119,6,0.15);
}
.conflict-warn { font-size: 11.5px; color: var(--warn); font-weight: 500; }
.conflict-btn {
  font-size: 12px; font-weight: 700; font-family: var(--font-sans);
  padding: 5px 14px; border-radius: 6px; border: none; cursor: pointer;
  background: var(--warn); color: #fff; transition: opacity 0.13s;
  white-space: nowrap;
}
.conflict-btn:disabled { opacity: 0.6; cursor: default; }

/* ── Sticky bottom bar ──────────────────────────────────────────────────── */



.pill-remove   { cursor: pointer; opacity: 0.5; font-size: 9px; margin-left: 1px; }
.pill-remove:hover { opacity: 1; }

.ml-auto       { margin-left: auto; }

/* ── Extra env vars ──────────────────────────────────────────────────────── */
.extraenv-service { border-top: 1px solid var(--border); padding-top: 6px; margin-top: 6px; }
.extraenv-service:first-child { border-top: none; margin-top: 0; }
.extraenv-service-head { display: flex; align-items: center; gap: 7px; cursor: pointer; padding: 3px 2px; border-radius: 5px; user-select: none; }
.extraenv-service-head:hover { background: var(--bg-0); }
.extraenv-icon  { font-size: 12px; }
.extraenv-name  { font-size: 12px; font-weight: 600; color: var(--fg-0); flex: 1; }
.extraenv-count { font-size: 9.5px; font-weight: 700; color: var(--accent); background: var(--accent-subtle); border: 1px solid var(--accent-dim); padding: 1px 6px; border-radius: 20px; }
.extraenv-chevron { font-size: 13px; color: var(--fg-2); transition: transform 0.13s; display: inline-block; }
.extraenv-chevron.open { transform: rotate(90deg); }
.extraenv-rows { margin-top: 6px; display: flex; flex-direction: column; gap: 5px; }
.extraenv-row  { display: flex; align-items: center; gap: 5px; }
.extraenv-key  { font-family: var(--font-mono); font-size: 11.5px; flex: 0 0 160px; padding: 4px 7px; border: 1.5px solid var(--border); border-radius: 5px; background: var(--bg-0); color: var(--fg-0); outline: none; }
.extraenv-key:focus { border-color: var(--accent); }
.extraenv-eq   { font-family: var(--font-mono); font-size: 12px; color: var(--fg-2); flex-shrink: 0; }
.extraenv-val  { font-family: var(--font-mono); font-size: 11.5px; flex: 1; padding: 4px 7px; border: 1.5px solid var(--border); border-radius: 5px; background: var(--bg-0); color: var(--fg-0); outline: none; min-width: 0; }
.extraenv-val:focus { border-color: var(--accent); }
.extraenv-rm   { font-size: 10px; color: var(--fg-2); background: none; border: none; cursor: pointer; padding: 0 3px; flex-shrink: 0; }
.extraenv-rm:hover { color: var(--err); }
.extraenv-add  { font-size: 11.5px; font-weight: 600; font-family: var(--font-sans); color: var(--accent); background: none; border: 1.5px dashed var(--accent-dim); border-radius: 5px; padding: 3px 10px; cursor: pointer; margin-top: 2px; transition: all 0.13s; }
.extraenv-add:hover { background: var(--accent-subtle); }

/* ── Narrow screens: stack vertically ───────────────────────────────────── */
@media (max-width: 767px) {
  .builder-layout {
    flex-direction: column;
  }
  .config-panel {
    flex: 1;
    width: 100%;
  }
  .service-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  
}

/* ── Medium screens: 3-column grid ─────────────────────────────────────── */
@media (min-width: 768px) and (max-width: 1079px) {
  .service-grid {
    grid-template-columns: repeat(3, 1fr);
  }
  
}

/* ── Wide screens: always side-by-side, hide bottom bar ────────────────── */
@media (min-width: 1080px) {
  
}
</style>
