<template>
  <div class="builder">

    <!-- ── Header ──────────────────────────────────────────────────────── -->
    <div class="builder-header">
      <div class="builder-header-left">
        <h1 class="page-title">Stack Builder</h1>
        <div class="builder-subtitle">
          <span class="sel-count">
            {{ selectedServices.length }} service{{ selectedServices.length !== 1 ? 's' : '' }} selected
          </span>
          <div v-if="selectedServices.length" class="sel-pills">
            <span
              v-for="key in selectedServices" :key="key"
              class="sel-pill"
              :style="svcPillStyle(key)"
            >{{ svcName(key) }}</span>
          </div>
        </div>
      </div>
      <div class="header-actions">
        <button class="primary" :disabled="deploying" @click="deploy">
          {{ deploying ? 'Deploying…' : 'Deploy stack →' }}
        </button>
      </div>
    </div>

    <!-- ── Two-column layout ────────────────────────────────────────────── -->
    <div class="builder-layout">

      <!-- Left: service grid -->
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
            :style="pick[svc.key] ? tileStyle(svc.category) : {}"
            @click="toggle(svc.key)"
          >
            <div class="tile-top">
              <span class="tile-icon">{{ svc.icon }}</span>
              <div class="tile-check" :class="{ checked: pick[svc.key] }">
                <svg v-if="pick[svc.key]" viewBox="0 0 12 12" fill="none">
                  <polyline points="2,6 5,9 10,3" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
              </div>
            </div>
            <div class="tile-name">{{ svc.display_name }}</div>
            <div class="tile-desc">{{ svc.short_desc }}</div>
            <div class="tile-foot">
              <span class="tile-tag" :style="tagStyle(svc.category)">{{ TAG_LABELS[svc.category] || svc.category }}</span>
              <span v-if="svc.web_port" class="tile-port" :class="{ 'tile-port-override': portOverrides[svc.key] }">
              {{ portOverrides[svc.key] || svc.web_port }}
            </span>
              <span v-if="LIVE_SERVICES.has(svc.key)" class="tile-live">live</span>
            </div>
          </button>

          <!-- Add custom app tile -->
          <button
            :class="['tile', 'tile-add', { on: addCustom }]"
            @click="toggleAddCustom"
          >
            <div class="tile-top">
              <span class="tile-icon tile-icon-add">＋</span>
              <div class="tile-check" :class="{ checked: addCustom }">
                <svg v-if="addCustom" viewBox="0 0 12 12" fill="none">
                  <polyline points="2,6 5,9 10,3" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
              </div>
            </div>
            <div class="tile-name">Custom app</div>
            <div class="tile-desc">Add via compose or image URL</div>
            <div class="tile-foot">
              <span class="tile-tag tile-tag-custom">Custom</span>
            </div>
          </button>
        </div>

      </div><!-- /grid-panel -->

      <!-- Right: config accordion (sticky on wide screens) -->
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
          <div class="cfg-head" @click="toggleCfg('core')">
            <span class="cfg-icon">⚙️</span>
            <span class="cfg-title">Core settings</span>
            <span class="cfg-chevron" :class="{ open: expanded.core }">›</span>
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

          <!-- Cloudflare — only when cloudflared is selected -->
                    <template v-if="pick['cloudflared']">
          <div class="cfg-section" :class="{ open: expanded.cloudflare }">
          <div class="cfg-head" @click="toggleCfg('cloudflare')">
            <span class="cfg-icon">☁️</span>
            <span class="cfg-title">Cloudflare Tunnel</span>
            <span class="cfg-chevron" :class="{ open: expanded.cloudflare }">›</span>
          </div>
          <div v-if="expanded.cloudflare" class="cfg-body">
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
                <input v-model="req.cloudflare_tunnel_token" type="password" placeholder="Cloudflare Zero Trust → Networks → Tunnels" />
              </label>
            </div>
          </div>
          </div>
          </template>

          <!-- Tailscale — only when tailscale is selected -->
                    <template v-if="pick['tailscale']">
          <div class="cfg-section" :class="{ open: expanded.tailscale }">
          <div class="cfg-head" @click="toggleCfg('tailscale')">
            <span class="cfg-icon">🔗</span>
            <span class="cfg-title">Tailscale</span>
            <span class="cfg-chevron" :class="{ open: expanded.tailscale }">›</span>
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
            <span class="cfg-chevron" :class="{ open: expanded.tinyauth }">›</span>
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
            <span class="cfg-badge-mode">{{ plexMode === 'local' ? 'local' : 'external' }}</span>
            <span class="cfg-chevron" :class="{ open: expanded.plex }">›</span>
          </div>
          <div v-if="expanded.plex" class="cfg-body">
            <div class="mode-toggle">
              <button :class="['mode-btn', { active: plexMode === 'local' }]" @click="plexMode = 'local'">Running on this stack</button>
              <button :class="['mode-btn', { active: plexMode === 'external' }]" @click="plexMode = 'external'">External server</button>
            </div>
            <div v-show="plexMode === 'local'">
              <div class="cfg-grid">
                <label class="cfg-field">
                  <span class="cfg-label">Server name</span>
                  <input v-model="req.plex_server_name" placeholder="My Plex Server" />
                  <span class="cfg-hint">Friendly name shown in Plex clients</span>
                </label>
                <label class="cfg-field">
                  <span class="cfg-label">&nbsp;</span>
                </label>
                <label class="cfg-field span2">
                  <span class="cfg-label">
                    Plex Claim Token
                    <a href="https://plex.tv/claim" target="_blank" class="cfg-link">Get at plex.tv/claim ↗</a>
                  </span>
                  <input v-model="req.plex_claim" placeholder="claim-xxxxxxxxxxxxxxxxxxxx" />
                  <span class="cfg-hint">Links this server to your Plex account on first start. Expires in 4 minutes — grab it right before deploying.</span>
                </label>
                <label class="cfg-field span2">
                  <span class="cfg-label">
                    X-Plex-Token
                    <a href="https://support.plex.tv/articles/204059436" target="_blank" class="cfg-link">How to find it ↗</a>
                  </span>
                  <input v-model="req.plex_token" type="password" placeholder="Your Plex authentication token" />
                  <span class="cfg-hint">Used by Sonarr, Radarr, and other apps for API auth. In Plex: Account → Troubleshooting → Show → X-Plex-Token.</span>
                </label>
              </div>
            </div>
            <div v-show="plexMode !== 'local'">
              <div class="cfg-grid">
                <label class="cfg-field span2">
                  <span class="cfg-label">Plex server URL</span>
                  <input v-model="req.external_plex_url" placeholder="http://192.168.1.50:32400" />
                  <span class="cfg-hint">LAN address preferred — avoids unnecessary external routing.</span>
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
            </div>
          </div>
          </div>
          </template>

          <!-- Add custom app — shown when custom tile is toggled on -->
                    <template v-if="addCustom">
          <div class="cfg-section" :class="{ open: expanded.custom }">
          <div class="cfg-head" @click="toggleCfg('custom')">
            <span class="cfg-icon">＋</span>
            <span class="cfg-title">Add custom app</span>
            <span class="cfg-chevron" :class="{ open: expanded.custom }">›</span>
          </div>
          <div v-if="expanded.custom" class="cfg-body">
            <div class="tab-row">
              <button
                v-for="[t, label] in [['compose','Paste docker-compose'],['url','Image URL'],['file','Upload file']]"
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
              <button class="primary" :disabled="addParsing" @click="parseAndAdd">
                {{ addParsing ? 'Fetching…' : 'Parse & add →' }}
              </button>
            </div>
          </div>
          </div>
          </template>

          <!-- Review & deploy — always visible -->
          <div class="cfg-section" :class="{ open: expanded.deploy }">
          <div class="cfg-head" @click="toggleCfg('deploy')">
            <span class="cfg-icon">🚀</span>
            <span class="cfg-title">Review &amp; deploy</span>
            <span class="cfg-chevron" :class="{ open: expanded.deploy }">›</span>
          </div>
          <div v-if="expanded.deploy" class="cfg-body">
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

            <!-- Conflict resolution banner -->
            <div v-if="deployConflicts.length" class="conflict-banner">
              <div class="conflict-banner-head">
                <span class="conflict-icon">⚠</span>
                <span class="conflict-title">
                  {{ deployConflicts.length }} container{{ deployConflicts.length !== 1 ? 's' : '' }} already exist and must be removed first
                </span>
              </div>
              <div class="conflict-names">
                <code v-for="name in deployConflicts" :key="name" class="conflict-name">{{ name }}</code>
              </div>
              <div class="conflict-actions">
                <span class="conflict-warn">These containers will be stopped and removed.</span>
                <button class="conflict-btn" :disabled="deploying" @click="purgeAndRetry">
                  {{ deploying ? 'Removing…' : 'Remove conflicts & retry deploy' }}
                </button>
              </div>
            </div>
          </div>
          </div>

        </div>
      </div><!-- /config-panel -->

    </div><!-- /builder-layout -->

    <!-- Sticky bottom bar — hidden on wide screens via CSS -->
    <div v-if="selectedServices.length" class="bottom-bar">
      <div class="bottom-pills">
        <span
          v-for="key in selectedServices" :key="key"
          class="bottom-pill"
          :style="svcPillStyle(key)"
        >
          {{ svcName(key) }}
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
import { ref, reactive, computed, onMounted, watch, inject } from 'vue'

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
  tinyauth: false, plex: false, custom: false, deploy: true,
})
const plexMode     = ref('local')
const addCustom    = ref(false)
const addTab       = ref('compose')
const addInput     = ref('')
const portOverrides  = reactive({})   // { service_key: override_port }
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
  cloudflare_token: '',
  cloudflare_tunnel_token: '',
  external_plex_url: '',
  plex_claim: '',
  plex_server_name: '',
  plex_token: '',  // kept for UI only — goes to Settings/Secrets
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
watch(req,  v => localStorage.setItem(STORAGE_KEY, JSON.stringify(v)), { deep: true })
watch(pick, v => localStorage.setItem('rad-stack-builder-pick', JSON.stringify({...v})), { deep: true })

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

// Set for O(1) lookup instead of Array.includes()
const LIVE_SERVICES = new Set([
  'traefik', 'plex', 'sonarr', 'radarr', 'prowlarr', 'qbittorrent', 'cloudflared',
])

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
  return flatServices.value.filter(svc => {
    if (activeFilter.value && svc.category !== activeFilter.value) return false
    if (!q) return true
    return (
      svc.display_name.toLowerCase().includes(q) ||
      (svc.short_desc || '').toLowerCase().includes(q) ||
      TAG_LABELS[svc.category]?.toLowerCase().includes(q)
    )
  })
})

const selectedServices = computed(() =>
  Object.entries(pick).filter(([, on]) => on).map(([k]) => k)
)

// ── Style helpers — consistent: all take category or key via svcByKey ──────
function catColors(cat)    { return CAT_COLORS[cat] || { bg: 'var(--accent-subtle)', border: 'var(--accent-dim)', text: 'var(--accent)' } }
function tagStyle(cat)     { const c = catColors(cat); return { background: c.bg, color: c.text, borderColor: c.border } }
function tileStyle(cat)    { const c = catColors(cat); return { '--tc': c.text, '--tc-bg': c.bg } }
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
  if (section) expanded[section] = pick[key]
}

function toggleAddCustom() {
  addCustom.value = !addCustom.value
  if (addCustom.value) expanded.custom = true; else expanded.custom = false
}

// camelCase throughout — was mixed snake_case/camelCase previously
function toggleCfg(id) { expanded[id] = !expanded[id] }

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
      ['traefik', 'prowlarr', 'sonarr', 'radarr', 'bazarr', 'overseerr',
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
    cloudflare_token:          req.cloudflare_token,
    cloudflare_tunnel_token:   req.cloudflare_tunnel_token,
    plex_claim:                req.plex_claim,
    plex_server_name:          req.plex_server_name,
    external_plex_url:         req.external_plex_url,
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

onMounted(loadCatalog)
</script>

<style scoped>
/* ── Layout ─────────────────────────────────────────────────────────────── */
.builder { max-width: 1040px; padding-bottom: 80px; }

.builder-layout {
  display: flex;
  flex-direction: column;
}
.grid-panel   { min-width: 0; }
.config-panel { min-width: 0; }

/* ── Header ─────────────────────────────────────────────────────────────── */
.builder-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-4);
  margin-bottom: var(--space-4);
}
.builder-header-left { flex: 1; min-width: 0; }
.builder-subtitle    { margin-top: 6px; }
.sel-count {
  font-size: 12px;
  color: var(--fg-2);
  display: block;
  margin-bottom: 6px;
}
.sel-pills  { display: flex; flex-wrap: wrap; gap: 5px; }
.sel-pill {
  font-size: 11px;
  font-weight: 500;
  font-family: var(--font-sans);
  padding: 2px 9px;
  border-radius: 20px;
  border: 1px solid;
  white-space: nowrap;
}
.header-actions {
  display: flex;
  gap: var(--space-2);
  align-items: flex-start;
  flex-shrink: 0;
  padding-top: 2px;
}

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
.pill:hover  { border-color: var(--border-strong); color: var(--fg-0); }
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
  --tc:    var(--accent);
  --tc-bg: var(--accent-subtle);
  display: flex;
  flex-direction: column;
  padding: 7px 9px;
  background: var(--bg-1);
  border: 1.5px solid var(--border);
  border-radius: var(--radius-sm);
  text-align: left;
  cursor: pointer;
  transition: border-color 0.13s, background 0.13s, box-shadow 0.13s;
  font-family: var(--font-sans);
}
.tile:hover { border-color: var(--border-strong); box-shadow: var(--shadow-1); }
.tile.on    { border-color: var(--tc); background: var(--tc-bg); box-shadow: var(--shadow-1); }

.tile-top   { display: flex; align-items: center; margin-bottom: 5px; }
.tile-icon  { font-size: 13px; line-height: 1; }
.tile-check {
  margin-left: auto;
  width: 14px; height: 14px;
  border-radius: 3px;
  border: 1.5px solid var(--border-strong);
  background: var(--bg-1);
  display: flex; align-items: center; justify-content: center;
  color: #fff;
  transition: all 0.13s;
  flex-shrink: 0;
}
.tile-check.checked { background: var(--tc); border-color: var(--tc); }
.tile-check svg     { width: 9px; height: 9px; }

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
.tile-foot { display: flex; align-items: center; gap: 4px; flex-wrap: nowrap; }
.tile-tag  {
  font-size: 9px; font-weight: 600;
  padding: 1px 5px; border-radius: 20px;
  border: 1px solid; white-space: nowrap;
}
.tile-port {
  font-family: var(--font-mono); font-size: 9px;
  color: var(--fg-2); background: var(--bg-2);
  padding: 1px 4px; border-radius: 3px;
  border: 1px solid var(--border);
}
.tile-live {
  margin-left: auto; flex-shrink: 0;
  font-size: 8px; font-weight: 700;
  padding: 1px 4px; border-radius: 20px;
  background: var(--ok-bg); color: var(--ok);
  border: 1px solid rgba(22,163,74,0.2);
  text-transform: uppercase;
}

/* Custom app tile */
.tile-add              { border-style: dashed; background: var(--bg-0); }
.tile-add:hover        { border-color: var(--accent); }
.tile-add.on           { border-color: var(--accent); border-style: solid; background: var(--accent-subtle); }
.tile-icon-add         { font-size: 16px; color: var(--fg-2); }
.tile-add.on .tile-icon-add { color: var(--accent); }
.tile-tag-custom       { background: var(--bg-2); color: var(--fg-2); border-color: var(--border); }

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
.cfg-title        { font-size: 12.5px; font-weight: 600; color: var(--fg-0); }
/* cfg-badge removed */
.cfg-badge-mode   { font-size: 9px; font-weight: 600; color: var(--fg-2); background: var(--bg-2); padding: 1px 6px; border-radius: 20px; border: 1px solid var(--border); }
.cfg-chevron      { margin-left: auto; color: var(--fg-2); font-size: 16px; transition: transform 0.13s; display: inline-block; line-height: 1; }
.cfg-chevron.open { transform: rotate(90deg); }
.cfg-body         { padding: 2px 12px 8px; border-top: 1px solid var(--border); }
.cfg-body input   { padding: 3px 7px; font-size: 11.5px; }

.cfg-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 5px; margin-top: 6px; }
.cfg-field        { display: flex; flex-direction: column; gap: 1px; min-width: 0; overflow: hidden; }
.cfg-field.span2  { grid-column: span 2; }
.cfg-field .cfg-label:empty, .cfg-label:only-child:empty { visibility: hidden; }
.cfg-label        { font-size: 11px; font-weight: 600; color: var(--fg-1); display: flex; align-items: center; gap: 6px; justify-content: space-between; min-width: 0; width: 100%; }
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
.deploy-row    { display: flex; align-items: center; gap: var(--space-2); margin-top: var(--space-3); margin-bottom: var(--space-3); }
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
.bottom-bar    { position: fixed; bottom: 0; left: 0; right: 0; background: var(--bg-1); border-top: 1.5px solid var(--border); padding: 10px 20px; display: flex; align-items: center; gap: 10px; z-index: 100; box-shadow: 0 -2px 12px rgba(0,0,0,0.06); }
.bottom-pills  { display: flex; gap: 5px; flex-wrap: wrap; flex: 1; }
.bottom-pill   { display: flex; align-items: center; gap: 4px; border: 1px solid; border-radius: 20px; padding: 3px 8px 3px 7px; font-size: 11.5px; font-weight: 500; font-family: var(--font-sans); }
.pill-remove   { cursor: pointer; opacity: 0.5; font-size: 9px; margin-left: 1px; }
.pill-remove:hover { opacity: 1; }
.bottom-deploy { flex-shrink: 0; }
.ml-auto       { margin-left: auto; }

/* ── Wide screen (≥1280px): two-column ──────────────────────────────────── */
@media (min-width: 1080px) {
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
    max-height: calc(100vh - 54px); /* 54px = App.vue topbar height */
    overflow-y: auto;
    border-left: 1.5px solid var(--border);
    padding-left: 28px;
    padding-bottom: 24px;
    scrollbar-width: thin;
    scrollbar-color: var(--border-strong) transparent;
    /* Reserve scrollbar gutter so appearing scrollbar doesn't reflow the grid */
    scrollbar-gutter: stable;
  }
  .bottom-bar {
    display: none; /* config panel always visible on wide */
  }
  .service-grid {
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  }
}

/* ── Ultra-wide (≥1800px) ────────────────────────────────────────────────── */
@media (min-width: 1600px) {
  .grid-panel { flex: 0 0 60%; }
  .service-grid {
    grid-template-columns: repeat(auto-fill, minmax(152px, 1fr));
  }
}
</style>
