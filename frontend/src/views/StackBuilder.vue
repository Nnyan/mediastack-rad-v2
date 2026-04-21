<template>
  <div class="builder">

    <!-- Header -->
    <div class="builder-header">
      <div class="builder-header-left">
        <h1 class="page-title">Stack Builder</h1>
        <div class="builder-subtitle">
          <span class="sel-count">{{ selectedServices.length }} service{{ selectedServices.length !== 1 ? 's' : '' }} selected</span>
          <div v-if="selectedServices.length" class="sel-pills">
            <span
              v-for="key in selectedServices" :key="key"
              class="sel-pill"
              :style="{ background: catBg(svcCategory(key)), color: catColor(svcCategory(key)), borderColor: catBorder(key) }"
            >{{ svcDisplayName(key) }}</span>
          </div>
        </div>
      </div>
      <div class="header-actions">
        <button class="primary" :disabled="deploying" @click="deploy">
          {{ deploying ? 'Deploying…' : 'Deploy stack →' }}
        </button>
      </div>
    </div>

    <!-- Two-column layout wrapper (single col on narrow, side-by-side on wide) -->
    <div class="builder-layout">
    <div class="grid-panel">

    <!-- Search + filter pills -->
    <div class="filter-row">
      <div class="search-wrap">
        <span class="search-icon">🔍</span>
        <input v-model="search" placeholder="Search services…" class="search-input" />
      </div>
      <div class="filter-pills">
        <button
          v-for="[tag, label] in Object.entries(TAG_LABELS)"
          :key="tag"
          :class="['pill', { active: activeFilter === tag }]"
          :style="activeFilter === tag ? tagStyle(tag) : {}"
          @click="activeFilter = activeFilter === tag ? '' : tag"
        >{{ label }}</button>
      </div>
    </div>

    <!-- Service grid -->
    <div class="service-grid">
      <button
        v-for="svc in filteredServices"
        :key="svc.key"
        :class="['tile', { on: pick[svc.key] }]"
        :style="pick[svc.key] ? { '--tc': catColor(svc.category), '--tc-bg': catBg(svc.category) } : {}"
        @click="toggle(svc.key)"
      >
        <!-- Icon + checkbox -->
        <div class="tile-top">
          <span class="tile-icon">{{ svc.icon }}</span>
          <div class="tile-check" :class="{ checked: pick[svc.key] }">
            <svg v-if="pick[svc.key]" viewBox="0 0 12 12" fill="none">
              <polyline points="2,6 5,9 10,3" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </div>
        </div>
        <!-- Name -->
        <div class="tile-name">{{ svc.display_name }}</div>
        <!-- Description -->
        <div class="tile-desc">{{ svc.short_desc }}</div>
        <!-- Footer: tag + port + live -->
        <div class="tile-foot">
          <span class="tile-tag" :style="tagStyle(svc.category)">{{ TAG_LABELS[svc.category] || svc.category }}</span>
          <span v-if="svc.web_port" class="tile-port">{{ svc.web_port }}</span>
          <span v-if="isLive(svc.key)" class="tile-live">live</span>
        </div>
        <!-- Tunnel warning -->
      </button>

      <!-- Add custom app tile -->
      <button
        :class="['tile', 'tile-add', { on: addCustom }]"
        @click="toggleAddCustom"
      >
        <div class="tile-top">
          <span class="tile-icon">＋</span>
          <div class="tile-check" :class="{ checked: addCustom }">
            <svg v-if="addCustom" viewBox="0 0 12 12" fill="none">
              <polyline points="2,6 5,9 10,3" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </div>
        </div>
        <div class="tile-name">Custom app</div>
        <div class="tile-desc">Add via compose or image URL</div>
        <div class="tile-foot">
          <span class="tile-tag" style="background:var(--bg-2);color:var(--fg-2);border-color:var(--border)">Custom</span>
        </div>
      </button>
    </div>

    </div><!-- /grid-panel -->

    <!-- Config panel (sticky on wide screens) -->
    <div class="config-panel">
    <!-- Configuration accordion sections -->
    <div v-if="showConfig" class="config-area">
      <div class="config-heading">Configuration</div>

      <!-- Core settings (always shown) -->
      <CfgSection title="Core settings" icon="⚙️" badge="required"
        :open="expanded === 'core'" @toggle="toggle_cfg('core')">
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
      </CfgSection>

      <!-- Cloudflare — only if cloudflared selected -->
      <CfgSection v-if="pick['cloudflared']" title="Cloudflare Tunnel" icon="☁️"
        badge="required by Cloudflare Tunnel" badge-color="var(--teal)"
        :open="expanded === 'cloudflare'" @toggle="toggle_cfg('cloudflare')">
        <div class="cfg-grid">
          <label class="cfg-field span2">
            <span class="cfg-label">
              DNS API token
              <a href="https://dash.cloudflare.com/profile/api-tokens" target="_blank" class="cfg-link">Create token ↗</a>
            </span>
            <input v-model="req.cloudflare_token" type="password" placeholder="Zone:DNS:Edit + Zone:Zone:Read" />
            <span class="cfg-hint">Required for DNS-01 certificate issuance via Let's Encrypt.</span>
          </label>
          <label class="cfg-field span2">
            <span class="cfg-label">Tunnel token</span>
            <input v-model="req.cloudflare_tunnel_token" type="password" placeholder="Paste from Cloudflare Zero Trust → Networks → Tunnels" />
          </label>
        </div>
      </CfgSection>

      <!-- Tailscale — only if tailscale selected -->
      <CfgSection v-if="pick['tailscale']" title="Tailscale" icon="🔗"
        badge="required by Tailscale" badge-color="var(--blue)"
        :open="expanded === 'tailscale'" @toggle="toggle_cfg('tailscale')">
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
      </CfgSection>

      <!-- Tinyauth — only if tinyauth selected -->
      <CfgSection v-if="pick['tinyauth']" title="Tinyauth" icon="🔒"
        badge="required by Tinyauth" badge-color="var(--purple)"
        :open="expanded === 'tinyauth'" @toggle="toggle_cfg('tinyauth')">
        <div class="cfg-note purple">
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
            <span class="cfg-hint">Base URL for cookie scoping and post-login redirect</span>
          </label>
          <label class="cfg-field span2">
            <span class="cfg-label">Secret</span>
            <input v-model="req.tinyauth_secret" type="password" placeholder="random 32-char hex" />
            <span class="cfg-hint">Generate: <code>python3 -c "import secrets; print(secrets.token_hex(32))"</code></span>
          </label>
          <label class="cfg-field span2">
            <span class="cfg-label">Users</span>
            <input v-model="req.tinyauth_users" placeholder="rafael:$2y$10$..." />
            <span class="cfg-hint">Format: <code>username:bcrypt_hash</code> — generate hash with: <code>docker run --rm ghcr.io/steveiliop56/tinyauth:latest generate-hash --password yourpw</code></span>
          </label>
          <label class="cfg-field span2 toggle-field">
            <span class="cfg-label">Require TOTP (2FA)</span>
            <label class="toggle">
              <input type="checkbox" v-model="req.tinyauth_totp" />
              <span class="toggle-track"></span>
              <span class="toggle-label">{{ req.tinyauth_totp ? 'TOTP enabled — scan QR in Tinyauth UI after first login' : 'Password only' }}</span>
            </label>
          </label>
        </div>
      </CfgSection>

      <!-- Plex — only if plex selected -->
      <CfgSection v-if="pick['plex']" :title="`Plex (${plexMode === 'local' ? 'on this stack' : 'external server'})`"
        icon="🎬" badge-color="var(--pink)"
        :open="expanded === 'plex'" @toggle="toggle_cfg('plex')">
        <!-- Mode toggle -->
        <div class="mode-toggle">
          <button :class="['mode-btn', { active: plexMode === 'local' }]" @click="plexMode = 'local'">Running on this stack</button>
          <button :class="['mode-btn', { active: plexMode === 'external' }]" @click="plexMode = 'external'">External server</button>
        </div>
        <!-- Local -->
        <template v-if="plexMode === 'local'">
          <div class="cfg-note pink">
            ℹ️ Plex is <strong>not routed through any reverse proxy tunnel</strong> — it uses its own relay and direct connections.
            For remote access use Tailscale or Plex's built-in relay.
          </div>
          <div class="cfg-grid">
            <label class="cfg-field span2">
              <span class="cfg-label">
                Plex Claim Token
                <a href="https://plex.tv/claim" target="_blank" class="cfg-link">Get at plex.tv/claim ↗</a>
              </span>
              <input v-model="req.plex_claim" placeholder="claim-xxxxxxxxxxxxxxxxxxxx" />
              <span class="cfg-hint">Links this server to your Plex account on first start. Token expires in 4 minutes — grab it right before deploying.</span>
            </label>
            <label class="cfg-field span2">
              <span class="cfg-label">
                X-Plex-Token
                <a href="https://support.plex.tv/articles/204059436" target="_blank" class="cfg-link">How to find it ↗</a>
              </span>
              <input v-model="req.plex_token" type="password" placeholder="Your Plex authentication token" />
              <span class="cfg-hint">Used by Sonarr, Radarr, and other apps for API authentication without username/password. In Plex: Account → Troubleshooting → Show → X-Plex-Token.</span>
            </label>
          </div>
        </template>
        <!-- External -->
        <template v-else>
          <div class="cfg-note neutral">
            ℹ️ Your Plex server runs on another machine. The URL and token let *arr apps connect for library lookups and notifications.
          </div>
          <div class="cfg-grid">
            <label class="cfg-field span2">
              <span class="cfg-label">Plex server URL</span>
              <input v-model="req.external_plex_url" placeholder="http://192.168.1.50:32400" />
              <span class="cfg-hint">LAN address preferred for *arr apps — avoids unnecessary external routing.</span>
            </label>
            <label class="cfg-field span2">
              <span class="cfg-label">
                X-Plex-Token
                <a href="https://support.plex.tv/articles/204059436" target="_blank" class="cfg-link">How to find it ↗</a>
              </span>
              <input v-model="req.plex_token" type="password" placeholder="Your Plex authentication token" />
              <span class="cfg-hint">Required for API access. In Plex: Account → Troubleshooting → Show → X-Plex-Token.</span>
            </label>
          </div>
        </template>
      </CfgSection>

      <!-- Add custom app (inline, not a modal) -->
      <CfgSection v-if="addCustom" title="Add custom app" icon="＋"
        badge-color="var(--fg-2)"
        :open="expanded === 'custom'" @toggle="toggle_cfg('custom')">
        <div class="tab-row" style="margin-top:10px">
          <button v-for="[t, label] in [['compose','Paste docker-compose'],['url','Image URL'],['file','Upload file']]"
            :key="t" :class="['tab-btn', { active: addTab === t }]" @click="addTab = t">{{ label }}</button>
        </div>
        <template v-if="addTab === 'compose'">
          <p class="cfg-hint" style="margin:8px 0 6px">Paste a <code>docker-compose.yml</code> fragment — it will be parsed and merged into your stack.</p>
          <textarea v-model="addInput" class="compose-textarea" placeholder="services:
  myapp:
    image: ghcr.io/author/myapp:latest
    ports:
      - &quot;8123:8123&quot;"></textarea>
        </template>
        <template v-else-if="addTab === 'url'">
          <p class="cfg-hint" style="margin:8px 0 6px">Enter a Docker Hub image name or full registry URL. Sensible defaults will be generated.</p>
          <input v-model="addInput" placeholder="lscr.io/linuxserver/heimdall  or  portainer/portainer-ce" class="url-input" style="margin-bottom:4px" />
        </template>
        <template v-else>
          <div class="file-drop" style="margin-top:10px">
            <div class="file-drop-icon">📄</div>
            <div class="file-drop-title">Drop a compose file here</div>
            <div class="file-drop-sub">or click to browse — .yml and .yaml supported</div>
          </div>
        </template>
        <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:12px">
          <button class="primary">Parse & add →</button>
        </div>
      </CfgSection>

      <!-- Preview / deploy -->
      <CfgSection title="Review & deploy" icon="🚀"
        :open="expanded === 'deploy'" @toggle="toggle_cfg('deploy')">
        <div class="deploy-row">
          <button @click="preview" :disabled="previewLoading">
            {{ previewLoading ? 'Generating…' : 'Preview compose.yml' }}
          </button>
          <button class="primary" :disabled="deploying" @click="deploy">
            {{ deploying ? 'Deploying…' : 'Deploy stack' }}
          </button>
          <span class="muted small ml-auto">{{ selectedServices.length }} services · {{ req.domain || 'no domain' }}</span>
        </div>
        <pre v-if="previewText" class="output mono">{{ previewText }}</pre>
        <div v-if="deployOutput" class="output-block" :class="deployOk ? 'ok' : 'err'">
          <div class="output-label">{{ deployOk ? '✓ Deploy complete' : '✗ Deploy failed' }}</div>
          <pre class="output mono">{{ deployOutput }}</pre>
        </div>
      </CfgSection>
    </div>

    </div><!-- /config-panel -->
    </div><!-- /builder-layout -->

    <!-- Sticky bottom bar (hidden on wide screens via CSS) -->
    <div v-if="selectedServices.length" class="bottom-bar">
      <div class="bottom-pills">
        <span v-for="key in selectedServices" :key="key" class="bottom-pill"
          :style="{ background: catBg(svcCategory(key)), borderColor: catBorder(key), color: catColor(svcCategory(key)) }">
          {{ svcDisplayName(key) }}
          <span class="pill-remove" @click="toggle(key)">✕</span>
        </span>
      </div>
      <button class="primary bottom-deploy" :disabled="deploying" @click="deploy">
        {{ deploying ? 'Deploying…' : 'Deploy stack →' }}
      </button>
    </div>

  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch, inject, defineComponent, h } from 'vue'

const showToast = inject('showToast')

// ── State ──────────────────────────────────────────────────────────────────
const rawCatalog = ref({})   // keyed by category from API
const pick = reactive({})
const search = ref('')
const activeFilter = ref('')
const expanded = ref('core')
const plexMode = ref('local')
const addCustom = ref(false)
const addTab = ref('compose')
const addInput = ref('')
const previewText = ref('')
const previewLoading = ref(false)
const deployOutput = ref('')
const deployOk = ref(false)
const deploying = ref(false)

// ── Persistence ────────────────────────────────────────────────────────────
const STORAGE_KEY = 'rad-stack-builder-v3'
const defaults = {
  domain: '', timezone: 'America/Los_Angeles', puid: 1000, pgid: 1000,
  config_root: '/home/stack/mediacenter/config',
  media_root: '/mnt/media',
  cloudflare_token: '',
  cloudflare_tunnel_token: '',
  external_plex_url: '',
  plex_claim: '',
  plex_token: '',
  tailscale_auth_key: '', tailscale_routes: '', tailscale_hostname: 'mediastack',
  tinyauth_secret: '', tinyauth_users: '', tinyauth_app_url: '', tinyauth_totp: false,
  lan_subnet: '10.0.0.0/22',
}
const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')
const req = reactive({ ...defaults, ...stored })
watch(req, v => localStorage.setItem(STORAGE_KEY, JSON.stringify(v)), { deep: true })

// ── Tag / category config ──────────────────────────────────────────────────
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
  overseerr: 'Request manager', jellyseerr: 'Request manager',
  traefik: 'Reverse proxy & HTTPS', tinyauth: 'Auth gateway',
  tailscale: 'Private VPN mesh', cloudflared: 'Public tunnel',
}

const ICONS = {
  plex: '🎬', jellyfin: '🎞️', sonarr: '📺', radarr: '🎥', lidarr: '🎵',
  readarr: '📚', bazarr: '💬', prowlarr: '🔍', qbittorrent: '⬇️',
  sabnzbd: '📰', nzbget: '📥', overseerr: '🙋', jellyseerr: '🙋',
  traefik: '🔀', tinyauth: '🔒', tailscale: '🔗', cloudflared: '☁️',
}

const LIVE_SERVICES = ['traefik', 'plex', 'sonarr', 'radarr', 'prowlarr', 'qbittorrent', 'cloudflared']

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

const filteredServices = computed(() => {
  const q = search.value.toLowerCase()
  return flatServices.value.filter(svc => {
    if (activeFilter.value && svc.category !== activeFilter.value) return false
    if (!q) return true
    return svc.display_name.toLowerCase().includes(q) ||
           (svc.short_desc || '').toLowerCase().includes(q) ||
           TAG_LABELS[svc.category]?.toLowerCase().includes(q)
  })
})

const selectedServices = computed(() =>
  Object.entries(pick).filter(([, on]) => on).map(([k]) => k)
)

const showConfig = computed(() => selectedServices.value.length > 0)

// ── Helpers ────────────────────────────────────────────────────────────────
function catColor(cat)   { return CAT_COLORS[cat]?.text   || 'var(--accent)' }
function catBg(cat)      { return CAT_COLORS[cat]?.bg      || 'var(--accent-subtle)' }
function catBorder(key)  {
  const svc = flatServices.value.find(s => s.key === key)
  return svc ? (CAT_COLORS[svc.category]?.border || 'var(--border)') : 'var(--border)'
}
function tagStyle(cat) {
  const c = CAT_COLORS[cat]
  if (!c) return {}
  return { background: c.bg, color: c.text, borderColor: c.border }
}
function isLive(key)        { return LIVE_SERVICES.includes(key) }
function svcCategory(key)   { return flatServices.value.find(s => s.key === key)?.category || 'infra' }
function svcDisplayName(key){ return flatServices.value.find(s => s.key === key)?.display_name || key }
function toggle(key)        { pick[key] = !pick[key] }
function toggleAddCustom()  {
  addCustom.value = !addCustom.value
  if (addCustom.value) expanded.value = 'custom'
}
function toggle_cfg(id)     { expanded.value = expanded.value === id ? '' : id }

// ── API ────────────────────────────────────────────────────────────────────
async function loadCatalog() {
  rawCatalog.value = await fetch('/api/catalog').then(r => r.json())
  if (Object.keys(pick).length === 0) {
    ['traefik', 'prowlarr', 'sonarr', 'radarr', 'bazarr', 'overseerr',
     'qbittorrent', 'plex', 'cloudflared'].forEach(k => { pick[k] = true })
  }
}

function buildRequest() {
  return {
    ...req,
    services: selectedServices.value.map(k => ({ key: k, enabled: true })),
    tinyauth_enabled: !!pick['tinyauth'],
  }
}

async function preview() {
  previewLoading.value = true
  previewText.value = ''
  expanded.value = 'deploy'
  try {
    const r = await fetch('/api/stack/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildRequest()),
    })
    if (!r.ok) throw new Error(await r.text())
    const data = await r.json()
    previewText.value = data.yaml
    showToast(`Generated — ${data.bytes} bytes`)
  } catch (e) {
    showToast(`Generate failed: ${e.message}`, 'err')
  } finally {
    previewLoading.value = false
  }
}

async function deploy() {
  if (!confirm('Deploy this stack? Running containers may be recreated.')) return
  deploying.value = true
  deployOutput.value = ''
  expanded.value = 'deploy'
  try {
    const r = await fetch('/api/stack/deploy', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildRequest()),
    })
    const data = await r.json()
    deployOk.value = data.ok
    deployOutput.value = [data.stdout, data.stderr ? '--- stderr ---\n' + data.stderr : '']
      .filter(Boolean).join('\n').trim()
    showToast(data.ok ? 'Deploy complete' : 'Deploy failed — see output below',
              data.ok ? 'ok' : 'err', 5000)
  } catch (e) {
    deployOk.value = false
    deployOutput.value = String(e)
    showToast(`Deploy error: ${e.message}`, 'err')
  } finally {
    deploying.value = false
  }
}

// ── Inline component — must be defined inside <script setup> so Vue ──────────
// registers it automatically. A separate <script> block does NOT make
// components available to <script setup> templates.
const CfgSection = {
  name: 'CfgSection',
  props: {
    title: String,
    icon: String,
    badge: String,
    badgeColor: { type: String, default: 'var(--fg-2)' },
    open: Boolean,
  },
  emits: ['toggle'],
  template: `
    <div class="cfg-section" :class="{ open }">
      <div class="cfg-head" @click="$emit('toggle')">
        <span class="cfg-icon">{{ icon }}</span>
        <span class="cfg-title">{{ title }}</span>
        <span v-if="badge" class="cfg-badge" :style="{ background: badgeColor + '18', color: badgeColor, borderColor: badgeColor + '40' }">{{ badge }}</span>
        <span class="cfg-chevron" :class="{ open }">›</span>
      </div>
      <div v-if="open" class="cfg-body">
        <slot />
      </div>
    </div>
  `,
}

onMounted(loadCatalog)
</script>



<style scoped>
.builder { max-width: 1040px; padding-bottom: 80px; }

/* ── Responsive two-column layout ─────────────────────────────────── */
.builder-layout {
  display: flex;
  flex-direction: column;
  gap: 0;
}
.grid-panel { min-width: 0; }
.config-panel { min-width: 0; }

/* ── Header ─────────────────────────────────────────────────────────────── */
.builder-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: var(--space-4);
  gap: var(--space-4);
}
.builder-header { align-items: flex-start; }
.builder-header-left { flex: 1; min-width: 0; }
.builder-subtitle { margin-top: 6px; }
.sel-count { font-size: 12px; color: var(--fg-2); display: block; margin-bottom: 6px; }
.sel-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}
.sel-pill {
  font-size: 11px;
  font-weight: 500;
  font-family: var(--font-sans);
  padding: 2px 9px;
  border-radius: 20px;
  border: 1px solid;
  white-space: nowrap;
}
.header-actions { display: flex; gap: var(--space-2); align-items: flex-start; flex-shrink: 0; padding-top: 2px; }

/* ── Filter row ─────────────────────────────────────────────────────────── */
.filter-row {
  display: flex;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
  align-items: center;
  flex-wrap: wrap;
}
.search-wrap { position: relative; flex: 1; max-width: 300px; }
.search-icon { position: absolute; left: 10px; top: 50%; transform: translateY(-50%); font-size: 13px; }
.search-input {
  width: 100%;
  padding: 7px 10px 7px 30px;
  font-family: var(--font-sans);
  font-size: 13px;
  background: var(--bg-1);
  border: 1.5px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--fg-0);
}
.search-input:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-dim); }
.filter-pills { display: flex; gap: 5px; flex-wrap: wrap; }
.pill {
  padding: 4px 11px;
  border-radius: 20px;
  font-size: 11.5px;
  font-weight: 500;
  font-family: var(--font-sans);
  cursor: pointer;
  border: 1.5px solid var(--border);
  background: var(--bg-1);
  color: var(--fg-2);
  transition: all 0.13s;
}
.pill:hover { border-color: var(--border-strong); color: var(--fg-0); }
.pill.active { font-weight: 600; border-color: currentColor; }

/* ── Service grid ───────────────────────────────────────────────────────── */
.service-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(148px, 1fr));
  gap: 8px;
  margin-bottom: var(--space-5);
  align-items: start;
}
.tile {
  --tc: var(--accent);
  --tc-bg: var(--accent-subtle);
  display: flex;
  flex-direction: column;
  gap: 0;
  padding: 7px 9px 7px;
  background: var(--bg-1);
  border: 1.5px solid var(--border);
  border-radius: var(--radius-sm);
  text-align: left;
  cursor: pointer;
  transition: border-color 0.13s, background 0.13s, box-shadow 0.13s;
  font-family: var(--font-sans);
}
.tile:hover { border-color: var(--border-strong); box-shadow: var(--shadow-1); }
.tile.on {
  border-color: var(--tc);
  background: var(--tc-bg);
  box-shadow: var(--shadow-1);
}
.tile-top {
  display: flex;
  align-items: center;
  margin-bottom: 5px;
}
.tile-icon { font-size: 13px; line-height: 1; }
.tile-check {
  margin-left: auto;
  width: 14px; height: 14px;
  border-radius: 3px;
  border: 1.5px solid var(--border-strong);
  background: var(--bg-1);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  transition: all 0.13s;
  flex-shrink: 0;
}
.tile-check.checked { background: var(--tc); border-color: var(--tc); }
.tile-check svg { width: 9px; height: 9px; }
.tile-name {
  font-family: var(--font-sans);
  font-size: 13.5px;
  font-weight: 700;
  color: var(--fg-0);
  margin-bottom: 2px;
  letter-spacing: -0.02em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.tile-desc {
  font-size: 10px;
  color: var(--fg-2);
  line-height: 1.3;
  margin-bottom: 6px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.tile-foot {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: nowrap;
}
.tile-tag {
  font-size: 9px;
  font-weight: 600;
  padding: 1px 5px;
  border-radius: 20px;
  border: 1px solid;
  white-space: nowrap;
}
.tile-port {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--fg-2);
  background: var(--bg-2);
  padding: 1px 4px;
  border-radius: 3px;
  border: 1px solid var(--border);
}
.tile-live {
  margin-left: auto;
  background: var(--ok-bg);
  color: var(--ok);
  font-size: 8px;
  font-weight: 700;
  padding: 1px 4px;
  border-radius: 20px;
  border: 1px solid rgba(22,163,74,0.2);
  text-transform: uppercase;
  flex-shrink: 0;
}
.tile-add { border-style: dashed; background: var(--bg-0); }
.tile-add:hover { border-color: var(--accent); border-style: dashed; }
.tile-add.on { border-color: var(--accent); border-style: solid; background: var(--accent-subtle); }
.tile-add .tile-icon { font-size: 16px; color: var(--fg-2); }
.tile-add.on .tile-icon { color: var(--accent); }

/* ── Config accordion ───────────────────────────────────────────────────── */
.config-area { display: flex; flex-direction: column; gap: 6px; }
.config-heading {
  font-size: 11px;
  font-weight: 700;
  color: var(--fg-2);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 6px;
}
.cfg-section {
  background: var(--bg-1);
  border: 1.5px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  transition: box-shadow 0.13s;
}
.cfg-section.open { box-shadow: var(--shadow-1); }
.cfg-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 14px;
  cursor: pointer;
  user-select: none;
}
.cfg-head:hover { background: var(--bg-2); }
.cfg-icon { font-size: 13px; }
.cfg-title { font-size: 12.5px; font-weight: 600; color: var(--fg-0); }
.cfg-badge {
  font-size: 9.5px;
  font-weight: 600;
  padding: 1px 7px;
  border-radius: 20px;
  border: 1px solid;
}
.cfg-chevron {
  margin-left: auto;
  color: var(--fg-2);
  font-size: 16px;
  transition: transform 0.13s;
  display: inline-block;
  line-height: 1;
}
.cfg-chevron.open { transform: rotate(90deg); }
.cfg-body { padding: 2px 14px 14px; border-top: 1px solid var(--border); }
.cfg-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-top: 10px;
}
.cfg-field { display: flex; flex-direction: column; gap: 3px; }
.cfg-field.span2 { grid-column: span 2; }
.cfg-label {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--fg-1);
  display: flex;
  align-items: center;
  gap: 6px;
}
.cfg-link { font-size: 11px; color: var(--accent); margin-left: auto; text-decoration: none; }
.cfg-link:hover { text-decoration: underline; }
.cfg-hint { font-size: 10px; color: var(--fg-2); line-height: 1.35; }
.cfg-hint code { font-family: var(--font-mono); font-size: 9.5px; background: var(--bg-2); padding: 1px 4px; border-radius: 3px; }
.cfg-note {
  font-size: 11.5px;
  border-radius: 6px;
  padding: 7px 11px;
  line-height: 1.5;
  margin-top: 10px;
  margin-bottom: 0;
}
.cfg-note.purple { background: var(--accent-subtle); color: var(--fg-1); border: 1px solid var(--accent-dim); }
.cfg-note.pink   { background: rgba(219,39,119,0.05); color: var(--fg-1); border: 1px solid rgba(219,39,119,0.15); }
.cfg-note.neutral{ background: var(--bg-0); color: var(--fg-1); border: 1px solid var(--border); }

/* Mode toggle for Plex */
.mode-toggle {
  display: flex;
  background: var(--bg-0);
  border-radius: 7px;
  padding: 3px;
  gap: 2px;
  margin-top: 10px;
}
.mode-btn {
  flex: 1;
  padding: 5px 8px;
  border-radius: 5px;
  font-family: var(--font-sans);
  font-size: 12px;
  font-weight: 500;
  border: none;
  background: transparent;
  color: var(--fg-2);
  cursor: pointer;
  transition: all 0.13s;
}
.mode-btn.active { background: var(--bg-1); color: var(--fg-0); box-shadow: var(--shadow-1); }

/* TOTP toggle */
.toggle-field { flex-direction: column; gap: var(--space-2); }
.toggle { display: flex; align-items: center; gap: var(--space-2); cursor: pointer; user-select: none; }
.toggle input { display: none; }
.toggle-track {
  width: 34px; height: 19px; border-radius: 10px;
  background: var(--border-strong); position: relative; flex-shrink: 0; transition: background 0.15s;
}
.toggle-track::after {
  content: ''; position: absolute; top: 2.5px; left: 2.5px;
  width: 14px; height: 14px; border-radius: 50%; background: #fff; transition: transform 0.15s;
}
.toggle input:checked ~ .toggle-track { background: var(--accent); }
.toggle input:checked ~ .toggle-track::after { transform: translateX(15px); }
.toggle-label { font-size: 12px; color: var(--fg-1); }

/* Deploy area */
.deploy-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-top: var(--space-3);
  margin-bottom: var(--space-3);
}
.output {
  max-height: 380px; overflow: auto;
  background: var(--bg-0); padding: var(--space-3); border-radius: var(--radius);
  font-size: 12px; line-height: 1.4; white-space: pre; border: 1px solid var(--border); margin: 0;
}
.output-block { border-radius: var(--radius); overflow: hidden; margin-top: var(--space-2); }
.output-label { padding: 6px 12px; font-size: 12px; font-weight: 600; }
.output-block.ok .output-label { background: var(--ok-bg); color: var(--ok); }
.output-block.err .output-label { background: var(--err-bg); color: var(--err); }
.output-block .output { border-top: none; border-radius: 0; }

/* custom app section shares tab-row/compose-textarea styles below */
.tab-row { display: flex; background: var(--bg-0); border-radius: 7px; padding: 3px; gap: 2px; margin-bottom: 14px; }
.tab-btn {
  flex: 1; padding: 5px 8px; border-radius: 5px; border: none;
  font-family: var(--font-sans); font-size: 12px; font-weight: 500; cursor: pointer;
  background: transparent; color: var(--fg-2); transition: all 0.13s;
}
.tab-btn.active { background: var(--bg-1); color: var(--fg-0); box-shadow: var(--shadow-1); }
.compose-textarea {
  font-family: var(--font-mono); font-size: 11.5px; width: 100%; height: 160px; resize: vertical;
  background: #0e0f14; color: #e8eaf5; border: 1.5px solid #252a3d; border-radius: 7px;
  padding: 10px 12px; outline: none; box-sizing: border-box; line-height: 1.6;
}
.url-input {
  font-family: var(--font-mono); font-size: 12px; width: 100%;
  background: var(--bg-1); border: 1.5px solid var(--border); border-radius: 6px;
  padding: 8px 10px; outline: none; color: var(--fg-0);
}
.file-drop {
  border: 2px dashed var(--border); border-radius: 9px; padding: 28px 20px;
  text-align: center; background: var(--bg-0); cursor: pointer;
}
.file-drop-icon { font-size: 26px; margin-bottom: 6px; }
.file-drop-title { font-size: 13.5px; font-weight: 600; color: var(--fg-0); margin-bottom: 3px; }
.file-drop-sub { font-size: 12px; color: var(--fg-2); }

/* ── Sticky bottom bar ──────────────────────────────────────────────────── */
.bottom-bar {
  position: fixed; bottom: 0; left: 0; right: 0;
  background: rgba(var(--bg-1-rgb, 255,255,255), 0.96);
  backdrop-filter: blur(12px);
  border-top: 1.5px solid var(--border);
  padding: 10px 20px;
  display: flex; align-items: center; gap: 10px; z-index: 100;
}
.bottom-pills { display: flex; gap: 5px; flex-wrap: wrap; flex: 1; }
.bottom-pill {
  display: flex; align-items: center; gap: 4px;
  border: 1px solid; border-radius: 20px; padding: 3px 8px 3px 7px;
  font-size: 11.5px; font-weight: 500; font-family: var(--font-sans);
}
.pill-remove { cursor: pointer; opacity: 0.5; font-size: 9px; margin-left: 1px; }
.pill-remove:hover { opacity: 1; }
.bottom-deploy { flex-shrink: 0; }
.ml-auto { margin-left: auto; }

/* Wide screen: grid left, config sticky right */
@media (min-width: 1280px) {
  .builder {
    max-width: none;
    padding-bottom: 24px;
  }
  .builder-layout {
    flex-direction: row;
    align-items: flex-start;
    gap: 32px;
  }
  .grid-panel {
    flex: 0 0 54%;
  }
  .config-panel {
    flex: 1;
    position: sticky;
    top: 0;
    max-height: calc(100vh - 54px); /* 54px = topbar height */
    overflow-y: auto;
    border-left: 1.5px solid var(--border);
    padding-left: 28px;
    padding-bottom: 24px;
    /* Custom scrollbar so it doesn't look chunky */
    scrollbar-width: thin;
    scrollbar-color: var(--border-strong) transparent;
  }
  /* Hide bottom bar on wide — config panel is always visible */
  .bottom-bar {
    display: none !important;
  }
  /* Give service grid more columns on wide */
  .service-grid {
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  }
}

/* Ultra-wide (2560px+): cap grid column count so tiles don't get huge */
@media (min-width: 1800px) {
  .grid-panel { flex: 0 0 60%; }
  .service-grid {
    grid-template-columns: repeat(auto-fill, minmax(152px, 1fr));
  }
}

</style>
