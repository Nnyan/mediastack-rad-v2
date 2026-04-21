<template>
  <div>
    <h1 class="page-title">
      Stack Builder
      <span class="sub">select services · generate compose · deploy</span>
    </h1>

    <div class="card">
      <h3 class="section-title">1. Global settings</h3>
      <div class="settings-grid">
        <label>
          <span class="label">Base domain</span>
          <input v-model="req.domain" placeholder="example.com" />
          <span class="hint">Apps served as sonarr.{{ req.domain || 'example.com' }}</span>
        </label>
        <label>
          <span class="label">Timezone</span>
          <input v-model="req.timezone" placeholder="America/Los_Angeles" />
        </label>
        <label>
          <span class="label">PUID / PGID</span>
          <div class="flex gap-2">
            <input v-model.number="req.puid" type="number" />
            <input v-model.number="req.pgid" type="number" />
          </div>
        </label>
        <label>
          <span class="label">Config root</span>
          <input v-model="req.config_root" />
        </label>
        <label style="grid-column: span 2">
          <span class="label">Media root</span>
          <input v-model="req.media_root" />
          <span class="hint">Containing subdirs: tv, movies, downloads, etc.</span>
        </label>
        <label style="grid-column: span 2">
          <span class="label">Cloudflare API token</span>
          <input
            v-model="req.cloudflare_token"
            type="password"
            placeholder="token with Zone:DNS:Edit + Zone:Zone:Read"
          />
          <span class="hint">
            Generate at
            <a href="https://dash.cloudflare.com/profile/api-tokens" target="_blank">
              dash.cloudflare.com/profile/api-tokens
            </a>
          </span>
        </label>
        <label style="grid-column: span 2">
          <span class="label">External Plex URL (optional)</span>
          <input
            v-model="req.external_plex_url"
            placeholder="http://192.168.1.5:32400"
          />
          <span class="hint">Leave blank to include containerized Plex in the stack.</span>
        </label>
      </div>
    </div>

    <!-- Tailscale settings — only shown when tailscale is selected -->
    <div class="card" v-if="pick['tailscale']">
      <h3 class="section-title">Tailscale settings</h3>

      <div class="compat-note">
        <span class="compat-icon">ℹ</span>
        <div>
          <strong>Tailscale + Cloudflare Tunnel work together.</strong>
          They serve different purposes — run both if you need both.
          Use Cloudflare Tunnel for public-facing services (Overseerr, Plex).
          Use Tailscale for private access from your own devices (Sonarr, Radarr, RAD).
        </div>
      </div>

      <div class="settings-grid">
        <label style="grid-column: span 2">
          <span class="label">Auth key <span class="required">required</span></span>
          <input
            v-model="req.tailscale_auth_key"
            type="password"
            placeholder="tskey-auth-…"
          />
          <span class="hint">
            Generate a <strong>reusable, non-ephemeral</strong> key at
            <a href="https://login.tailscale.com/admin/settings/keys" target="_blank">
              login.tailscale.com/admin/settings/keys
            </a>.
            Tag it as <code>tag:server</code> if you use ACL tags.
          </span>
        </label>
        <label>
          <span class="label">Hostname</span>
          <input v-model="req.tailscale_hostname" placeholder="mediastack" />
          <span class="hint">How this node appears in your Tailscale admin console.</span>
        </label>
        <label>
          <span class="label">Subnet routes (optional)</span>
          <input v-model="req.tailscale_routes" placeholder="172.20.0.0/16" />
          <span class="hint">
            Advertise your Docker network so all containers are reachable
            from any tailnet device. Find your subnet:
            <code>docker network inspect mediastack | grep Subnet</code>
          </span>
        </label>
      </div>

      <div class="ts-steps">
        <div class="ts-step-title">After deploying, complete these steps in order:</div>
        <ol class="ts-step-list">
          <li>Check <code>docker logs tailscale</code> — you should see "Connected to tailnet"</li>
          <li>Go to
            <a href="https://login.tailscale.com/admin/machines" target="_blank">Tailscale admin → Machines</a>
            and confirm <strong>{{ req.tailscale_hostname || 'mediastack' }}</strong> is listed
          </li>
          <li v-if="req.tailscale_routes">
            Click the machine → Edit route settings → approve <strong>{{ req.tailscale_routes }}</strong>
          </li>
          <li>On any enrolled device, access your apps by their Docker IP or by
            enabling MagicDNS in
            <a href="https://login.tailscale.com/admin/dns" target="_blank">Tailscale DNS settings</a>
          </li>
          <li>Configure each *arr app's base URL settings if you plan to access them
            via the Tailscale hostname rather than IP (Settings → General → URL Base in Sonarr/Radarr)
          </li>
        </ol>
      </div>
    </div>

    <div class="card">
      <h3 class="section-title">2. Pick your services</h3>
      <div v-for="(items, cat) in catalog" :key="cat" class="category">
        <h4 class="cat-title">{{ cat }}</h4>
        <div class="services-grid">
          <label
            v-for="s in items"
            :key="s.key"
            class="service"
            :class="{ picked: pick[s.key], 'cf-warn': pick[s.key] && pick['cloudflared'] && s.cf_tunnel_unsuitable }"
          >
            <input type="checkbox" v-model="pick[s.key]" />
            <div>
              <div class="service-name mono">{{ s.key }}</div>
              <div class="service-desc">{{ s.description }}</div>
              <div class="service-image tiny muted mono">{{ s.image }}</div>
              <div
                v-if="pick[s.key] && pick['cloudflared'] && s.cf_tunnel_unsuitable"
                class="cf-warn-banner"
              >
                ⚠ {{ s.cf_tunnel_warning }}
              </div>
            </div>
          </label>
        </div>
      </div>
    </div>

    <div class="card">
      <h3 class="section-title">3. Review & deploy</h3>
      <div class="flex gap-3 mb-3">
        <button @click="preview">Preview compose.yml</button>
        <button class="primary" :disabled="deploying" @click="deploy">
          {{ deploying ? 'Deploying…' : 'Deploy Stack' }}
        </button>
        <span class="ml-auto muted small">
          {{ selectedServices.length }} services selected
        </span>
      </div>

      <pre v-if="previewText" class="preview mono">{{ previewText }}</pre>
      <pre v-if="deployOutput" class="preview mono" :class="deployOutputClass">{{ deployOutput }}</pre>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, inject } from 'vue'

const showToast = inject('showToast')

const catalog = ref({})
const pick = reactive({})
const previewText = ref('')
const deployOutput = ref('')
const deployOutputClass = ref('')
const deploying = ref(false)

// Form state — persisted to localStorage so users don't lose it
// when they accidentally refresh mid-config.
const STORAGE_KEY = 'rad-stack-builder-v2'
const defaults = {
  domain: '',
  timezone: 'UTC',
  puid: 1000,
  pgid: 1000,
  config_root: '/home/stack/mediacenter/config',
  media_root: '/mnt/media',
  cloudflare_token: '',
  external_plex_url: '',
  tailscale_auth_key: '',
  tailscale_routes: '',
  tailscale_hostname: 'mediastack',
}
const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')
const req = reactive({ ...defaults, ...stored })

// Persist on every change
import { watch } from 'vue'
watch(req, (v) => {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(v))
}, { deep: true })

const selectedServices = computed(() =>
  Object.entries(pick)
    .filter(([, on]) => on)
    .map(([k]) => k)
)

async function loadCatalog() {
  catalog.value = await fetch('/api/catalog').then(r => r.json())
  // Default-enable the common selections if nothing picked yet.
  if (Object.keys(pick).length === 0) {
    ['traefik', 'prowlarr', 'sonarr', 'radarr', 'bazarr', 'overseerr',
     'qbittorrent', 'plex', 'cloudflared'].forEach(k => { pick[k] = true })
  }
}

function buildRequest() {
  return {
    ...req,
    services: selectedServices.value.map(k => ({ key: k, enabled: true })),
  }
}

async function preview() {
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
    showToast(`Generated ${data.bytes} bytes`)
  } catch (e) {
    showToast(`Generate failed: ${e.message}`, 'err')
  }
}

async function deploy() {
  if (!confirm('Deploy this stack? Existing containers may be recreated.')) return
  deploying.value = true
  deployOutput.value = 'Deploying…'
  deployOutputClass.value = ''
  try {
    const r = await fetch('/api/stack/deploy', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildRequest()),
    })
    const data = await r.json()
    deployOutput.value = (data.stdout || '') + (data.stderr ? '\n--- stderr ---\n' + data.stderr : '')
    deployOutputClass.value = data.ok ? 'ok' : 'err'
    showToast(data.ok ? 'Deploy complete' : 'Deploy failed — see output', data.ok ? 'ok' : 'err', 5000)
  } catch (e) {
    deployOutput.value = String(e)
    deployOutputClass.value = 'err'
    showToast(`Deploy error: ${e.message}`, 'err')
  } finally {
    deploying.value = false
  }
}

onMounted(loadCatalog)
</script>

<style scoped>
.section-title {
  margin: 0 0 var(--space-3);
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--fg-2);
  font-weight: 600;
}

.settings-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-3) var(--space-4);
}
.settings-grid label { display: flex; flex-direction: column; gap: 4px; }
.label { font-size: 12px; color: var(--fg-1); }
.hint { font-size: 11px; color: var(--fg-2); }
.hint a { color: var(--accent); }

.category { margin-bottom: var(--space-4); }
.cat-title {
  margin: 0 0 var(--space-2);
  font-size: 12px;
  color: var(--fg-2);
  text-transform: capitalize;
}
.services-grid {
  display: grid;
  gap: var(--space-2);
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
}
.service {
  display: flex;
  gap: var(--space-3);
  padding: var(--space-3);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  cursor: pointer;
  background: var(--bg-0);
}
.service:hover { border-color: var(--border-strong); }
.service.picked {
  border-color: var(--accent);
  background: var(--bg-2);
}
.service input { width: auto; margin-top: 2px; }
.service-name { font-weight: 600; font-size: 13px; }
.service-desc { font-size: 12px; color: var(--fg-1); }

.service.cf-warn {
  border-color: var(--warn);
  background: var(--bg-2);
}
.cf-warn-banner {
  margin-top: 6px;
  font-size: 11px;
  color: var(--warn);
  line-height: 1.4;
  padding: 4px 6px;
  background: var(--warn-dim);
  border-radius: 3px;
}

.preview {
  max-height: 500px;
  overflow: auto;
  background: var(--bg-0);
  padding: var(--space-3);
  border-radius: var(--radius);
  border: 1px solid var(--border);
  font-size: 12px;
  line-height: 1.4;
  white-space: pre;
}
.preview.ok { border-left: 3px solid var(--ok); }
.preview.err { border-left: 3px solid var(--err); }

.compat-note {
  display: flex;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  background: var(--bg-0);
  border: 1px solid var(--border);
  border-left: 3px solid var(--info);
  border-radius: var(--radius);
  font-size: 13px;
  color: var(--fg-1);
  margin-bottom: var(--space-4);
  line-height: 1.5;
}
.compat-icon {
  color: var(--info);
  font-size: 16px;
  flex-shrink: 0;
  margin-top: 1px;
}
.compat-note strong { color: var(--fg-0); }

.required {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 3px;
  background: var(--err-dim);
  color: var(--err);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-left: 4px;
  vertical-align: middle;
}

.ts-steps {
  margin-top: var(--space-4);
  padding: var(--space-3) var(--space-4);
  background: var(--bg-0);
  border-radius: var(--radius);
  border: 1px solid var(--border);
}
.ts-step-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--fg-2);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: var(--space-2);
}
.ts-step-list {
  margin: 0;
  padding-left: var(--space-5);
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.ts-step-list li {
  font-size: 13px;
  color: var(--fg-1);
  line-height: 1.5;
}
.ts-step-list code {
  background: var(--bg-2);
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 12px;
}
</style>
