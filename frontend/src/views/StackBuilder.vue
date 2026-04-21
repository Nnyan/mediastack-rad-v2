<template>
  <div class="builder">
    <div class="builder-header">
      <div>
        <h1 class="page-title">Stack Builder</h1>
        <p class="muted small">Configure your services, generate the compose file, and deploy.</p>
      </div>
      <div class="step-indicator">
        <span :class="['step', currentStep >= 1 ? 'active' : '']">1 Settings</span>
        <span class="step-sep">→</span>
        <span :class="['step', currentStep >= 2 ? 'active' : '']">2 Services</span>
        <span class="step-sep">→</span>
        <span :class="['step', currentStep >= 3 ? 'active' : '']">3 Deploy</span>
      </div>
    </div>

    <!-- Step 1: Settings -->
    <section class="card">
      <div class="card-head" @click="currentStep = 1">
        <div class="card-head-left">
          <span class="step-num">1</span>
          <h2 class="card-title">Global settings</h2>
        </div>
        <span class="chevron" :class="{ open: currentStep === 1 }">›</span>
      </div>

      <div class="card-body" v-show="currentStep === 1">
        <div class="settings-grid">
          <label class="field">
            <span class="field-label">Base domain</span>
            <input v-model="req.domain" placeholder="example.com" />
            <span class="field-hint">Apps served as sonarr.{{ req.domain || 'example.com' }}</span>
          </label>
          <label class="field">
            <span class="field-label">Timezone</span>
            <input v-model="req.timezone" placeholder="America/Los_Angeles" />
          </label>
          <label class="field">
            <span class="field-label">PUID</span>
            <input v-model.number="req.puid" type="number" />
          </label>
          <label class="field">
            <span class="field-label">PGID</span>
            <input v-model.number="req.pgid" type="number" />
          </label>
          <label class="field span2">
            <span class="field-label">Config root</span>
            <input v-model="req.config_root" />
          </label>
          <label class="field span2">
            <span class="field-label">Media root</span>
            <input v-model="req.media_root" />
            <span class="field-hint">Parent dir containing tv/, movies/, downloads/, etc.</span>
          </label>
          <label class="field span2">
            <span class="field-label">
              Cloudflare API token
              <a href="https://dash.cloudflare.com/profile/api-tokens" target="_blank" class="field-link">
                Get token ↗
              </a>
            </span>
            <input v-model="req.cloudflare_token" type="password" placeholder="Zone:DNS:Edit + Zone:Zone:Read" />
          </label>
          <label class="field span2">
            <span class="field-label">External Plex URL <span class="optional">optional</span></span>
            <input v-model="req.external_plex_url" placeholder="http://192.168.1.5:32400 — leave blank to include Plex" />
          </label>
        </div>
        <div class="card-actions">
          <button class="primary" @click="currentStep = 2">Next: Pick services →</button>
        </div>
      </div>
    </section>

    <!-- Step 2: Services -->
    <section class="card">
      <div class="card-head" @click="currentStep = 2">
        <div class="card-head-left">
          <span class="step-num">2</span>
          <h2 class="card-title">Services
            <span class="card-count">{{ selectedServices.length }} selected</span>
          </h2>
        </div>
        <span class="chevron" :class="{ open: currentStep === 2 }">›</span>
      </div>

      <div class="card-body" v-show="currentStep === 2">
        <!-- Category tabs -->
        <div class="cat-tabs">
          <button
            v-for="cat in catalogCategories"
            :key="cat"
            :class="['cat-tab', { active: activeCategory === cat }]"
            @click="activeCategory = cat"
          >
            {{ cat }}
            <span class="cat-count">{{ selectedInCategory(cat) }}/{{ catalog[cat]?.length }}</span>
          </button>
        </div>

        <!-- Service tiles -->
        <div class="tiles">
          <button
            v-for="s in catalog[activeCategory]"
            :key="s.key"
            :class="['tile', { 
              on: pick[s.key],
              warn: pick[s.key] && pick['cloudflared'] && s.cf_tunnel_unsuitable && !(s.key === 'plex' && req.external_plex_url)
            }]"
            :style="pick[s.key] ? { '--tile-color': catColor(activeCategory) } : {}"
            @click="toggle(s.key)"
            :title="s.description"
          >
            <div class="tile-top">
              <div class="tile-check" :class="{ checked: pick[s.key] }">
                <svg v-if="pick[s.key]" viewBox="0 0 12 12" fill="none">
                  <polyline points="2,6 5,9 10,3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
              </div>
              <span class="tile-name">{{ s.key }}</span>
              <span class="tile-port" v-if="s.web_port">:{{ s.web_port }}</span>
            </div>
            <div class="tile-desc">{{ s.description }}</div>
            <div
              v-if="pick[s.key] && pick['cloudflared'] && s.cf_tunnel_unsuitable && !(s.key === 'plex' && req.external_plex_url)"
              class="tile-warn"
            >⚠ Not compatible with Cloudflare Tunnel</div>
          </button>
        </div>

        <!-- Tailscale settings — shown inline when tailscale is selected -->
        <div class="ts-panel" v-if="pick['tailscale']">
          <div class="ts-compat-note">
            <span>ℹ</span>
            <div>
              <strong>Tailscale + Cloudflare Tunnel work together.</strong>
              Use Cloudflare Tunnel for public access (Overseerr, Plex relay).
              Use Tailscale for private admin access (Sonarr, Radarr, RAD, etc.)
            </div>
          </div>
          <div class="settings-grid mt-3">
            <label class="field span2">
              <span class="field-label">
                Tailscale auth key
                <span class="required">required</span>
                <a href="https://login.tailscale.com/admin/settings/keys" target="_blank" class="field-link">Get key ↗</a>
              </span>
              <input v-model="req.tailscale_auth_key" type="password" placeholder="tskey-auth-…  (reusable, non-ephemeral)" />
            </label>
            <label class="field">
              <span class="field-label">Hostname</span>
              <input v-model="req.tailscale_hostname" placeholder="mediastack" />
            </label>
            <label class="field">
              <span class="field-label">Subnet routes</span>
              <input v-model="req.tailscale_routes" placeholder="172.20.0.0/16" />
              <span class="field-hint">Advertise Docker network so all containers are reachable on tailnet</span>
            </label>
          </div>
        </div>

        <div class="card-actions">
          <button @click="currentStep = 1">← Back</button>
          <button class="primary" @click="currentStep = 3">Next: Review & deploy →</button>
        </div>
      </div>
    </section>

    <!-- Step 3: Deploy -->
    <section class="card">
      <div class="card-head" @click="currentStep = 3">
        <div class="card-head-left">
          <span class="step-num">3</span>
          <h2 class="card-title">Review & deploy</h2>
        </div>
        <span class="chevron" :class="{ open: currentStep === 3 }">›</span>
      </div>

      <div class="card-body" v-show="currentStep === 3">
        <div class="deploy-row">
          <button @click="preview" :disabled="previewLoading">
            {{ previewLoading ? 'Generating…' : 'Preview compose.yml' }}
          </button>
          <button class="primary" :disabled="deploying" @click="deploy">
            {{ deploying ? 'Deploying…' : 'Deploy Stack' }}
          </button>
          <span class="muted small ml-auto">{{ selectedServices.length }} services · {{ req.domain || 'no domain' }}</span>
        </div>

        <pre v-if="previewText" class="output mono">{{ previewText }}</pre>

        <div v-if="deployOutput" class="output-block" :class="deployOk ? 'ok' : 'err'">
          <div class="output-label">{{ deployOk ? '✓ Deploy complete' : '✗ Deploy failed' }}</div>
          <pre class="output mono">{{ deployOutput }}</pre>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch, inject } from 'vue'

const showToast = inject('showToast')

const catalog = ref({})
const pick = reactive({})
const currentStep = ref(1)
const activeCategory = ref('')

const previewText = ref('')
const previewLoading = ref(false)
const deployOutput = ref('')
const deployOk = ref(false)
const deploying = ref(false)

const STORAGE_KEY = 'rad-stack-builder-v2'
const defaults = {
  domain: '', timezone: 'UTC', puid: 1000, pgid: 1000,
  config_root: '/home/stack/mediacenter/config',
  media_root: '/mnt/media',
  cloudflare_token: '', external_plex_url: '',
  tailscale_auth_key: '', tailscale_routes: '', tailscale_hostname: 'mediastack',
}
const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')
const req = reactive({ ...defaults, ...stored })

watch(req, v => localStorage.setItem(STORAGE_KEY, JSON.stringify(v)), { deep: true })

const catalogCategories = computed(() => Object.keys(catalog.value))

const selectedServices = computed(() =>
  Object.entries(pick).filter(([, on]) => on).map(([k]) => k)
)

function selectedInCategory(cat) {
  return (catalog.value[cat] || []).filter(s => pick[s.key]).length
}

function catColor(cat) {
  const map = {
    media: 'var(--cat-media)',
    indexers: 'var(--cat-indexers)',
    downloaders: 'var(--cat-downloaders)',
    requests: 'var(--cat-requests)',
    infra: 'var(--cat-infra)',
  }
  return map[cat] || 'var(--accent)'
}

function toggle(key) {
  pick[key] = !pick[key]
}

async function loadCatalog() {
  catalog.value = await fetch('/api/catalog').then(r => r.json())
  if (Object.keys(pick).length === 0) {
    ['traefik', 'prowlarr', 'sonarr', 'radarr', 'bazarr', 'overseerr',
     'qbittorrent', 'plex', 'cloudflared'].forEach(k => { pick[k] = true })
  }
  if (catalogCategories.value.length) activeCategory.value = catalogCategories.value[0]
}

function buildRequest() {
  return {
    ...req,
    services: selectedServices.value.map(k => ({ key: k, enabled: true })),
  }
}

async function preview() {
  previewLoading.value = true
  previewText.value = ''
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

onMounted(loadCatalog)
</script>

<style scoped>
.builder { max-width: 960px; }
.builder-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: var(--space-4);
}
.step-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--fg-2);
}
.step { padding: 3px 10px; border-radius: 12px; background: var(--bg-2); }
.step.active { background: var(--accent); color: #0a1a0a; font-weight: 600; }
.step-sep { color: var(--border-strong); }

/* Cards */
.card { margin-bottom: var(--space-3); }
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
  padding: var(--space-3) var(--space-4);
  user-select: none;
}
.card-head:hover { background: var(--bg-2); border-radius: var(--radius); }
.card-head-left { display: flex; align-items: center; gap: var(--space-3); }
.card-title {
  font-size: 14px;
  font-weight: 600;
  margin: 0;
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.card-count {
  font-size: 11px;
  font-weight: 400;
  color: var(--fg-2);
  font-family: var(--font-mono);
}
.step-num {
  width: 22px; height: 22px;
  border-radius: 50%;
  background: var(--bg-3);
  color: var(--fg-2);
  font-size: 11px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.chevron {
  color: var(--fg-2);
  font-size: 18px;
  transition: transform 0.15s;
  display: inline-block;
}
.chevron.open { transform: rotate(90deg); }
.card-body { padding: 0 var(--space-4) var(--space-4); }

/* Settings grid */
.settings-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-3);
}
.field { display: flex; flex-direction: column; gap: 4px; }
.field.span2 { grid-column: span 2; }
.field-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--fg-1);
  display: flex;
  align-items: center;
  gap: 6px;
}
.field-hint { font-size: 11px; color: var(--fg-2); }
.field-link { font-size: 11px; color: var(--accent); margin-left: auto; }
.optional {
  font-size: 10px; padding: 1px 6px; border-radius: 3px;
  background: var(--bg-3); color: var(--fg-2);
}
.required {
  font-size: 10px; padding: 1px 6px; border-radius: 3px;
  background: var(--err-dim); color: var(--err); font-weight: 600;
}

/* Category tabs */
.cat-tabs {
  display: flex;
  gap: 6px;
  margin-bottom: var(--space-4);
  flex-wrap: wrap;
}
.cat-tab {
  padding: 6px 16px;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 500;
  background: var(--bg-0);
  border: 1.5px solid var(--border);
  color: var(--fg-2);
  transition: all 0.15s;
  display: flex;
  align-items: center;
  gap: 7px;
  text-transform: capitalize;
  cursor: pointer;
}
.cat-tab:hover { color: var(--fg-0); border-color: var(--border-strong); background: var(--bg-2); }
.cat-tab.active {
  background: var(--bg-1);
  border-color: var(--border-strong);
  color: var(--fg-0);
  font-weight: 600;
  box-shadow: var(--shadow-1);
}
.cat-count {
  font-family: var(--font-mono);
  font-size: 10.5px;
  color: var(--fg-2);
  background: var(--bg-2);
  padding: 1px 6px;
  border-radius: 10px;
}
.cat-tab.active .cat-count { background: var(--accent-dim); color: var(--accent); }

/* Service tiles */
.tiles {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(175px, 1fr));
  gap: var(--space-2);
  margin-bottom: var(--space-4);
}
.tile {
  --tile-color: var(--accent);
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding: var(--space-3);
  background: var(--bg-0);
  border: 1.5px solid var(--border);
  border-radius: var(--radius);
  text-align: left;
  cursor: pointer;
  transition: all 0.15s;
  min-height: 76px;
  position: relative;
  overflow: hidden;
}
.tile::before {
  content: '';
  position: absolute;
  left: 0; top: 0; bottom: 0;
  width: 3px;
  background: var(--tile-color);
  opacity: 0;
  transition: opacity 0.15s;
  border-radius: 2px 0 0 2px;
}
.tile:hover { border-color: var(--border-strong); background: var(--bg-1); box-shadow: var(--shadow-1); }
.tile.on {
  border-color: var(--tile-color);
  background: var(--bg-1);
  box-shadow: var(--shadow-1);
}
.tile.on::before { opacity: 1; }
.tile.warn { border-color: var(--warn) !important; }

.tile-top {
  display: flex;
  align-items: center;
  gap: 7px;
}
.tile-check {
  width: 17px; height: 17px;
  border-radius: 5px;
  border: 1.5px solid var(--border-strong);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.15s;
  background: var(--bg-1);
}
.tile-check.checked {
  background: var(--tile-color);
  border-color: var(--tile-color);
  color: #fff;
}
.tile-check svg { width: 10px; height: 10px; }

.tile-name {
  font-family: var(--font-mono);
  font-size: 12.5px;
  font-weight: 600;
  color: var(--fg-0);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tile-port {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--fg-2);
  background: var(--bg-2);
  padding: 1px 5px;
  border-radius: 4px;
  flex-shrink: 0;
}
.tile-desc {
  font-size: 11.5px;
  color: var(--fg-2);
  line-height: 1.4;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.tile-warn {
  font-size: 10.5px;
  color: var(--warn);
  background: var(--warn-bg);
  padding: 2px 6px;
  border-radius: 4px;
  margin-top: 2px;
  font-weight: 500;
}

/* Tailscale panel */
.ts-panel {
  background: var(--bg-0);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: var(--space-4);
  margin-bottom: var(--space-4);
}
.ts-compat-note {
  display: flex;
  gap: var(--space-3);
  font-size: 13px;
  color: var(--fg-1);
  line-height: 1.5;
  margin-bottom: var(--space-3);
}
.ts-compat-note span { color: var(--info); font-size: 16px; flex-shrink: 0; }
.ts-compat-note strong { color: var(--fg-0); }
.mt-3 { margin-top: var(--space-3); }

/* Actions */
.card-actions {
  display: flex;
  gap: var(--space-2);
  margin-top: var(--space-4);
  padding-top: var(--space-3);
  border-top: 1px solid var(--border);
}

/* Deploy */
.deploy-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
}
.output {
  max-height: 400px;
  overflow: auto;
  background: var(--bg-0);
  padding: var(--space-3);
  border-radius: var(--radius);
  font-size: 12px;
  line-height: 1.4;
  white-space: pre;
  border: 1px solid var(--border);
  margin: 0;
}
.output-block { border-radius: var(--radius); overflow: hidden; }
.output-label {
  padding: 6px 12px;
  font-size: 12px;
  font-weight: 600;
}
.output-block.ok .output-label { background: var(--ok-dim); color: var(--ok); }
.output-block.err .output-label { background: var(--err-dim); color: var(--err); }
.output-block .output { border-top: none; border-radius: 0; }

.ml-auto { margin-left: auto; }
</style>
