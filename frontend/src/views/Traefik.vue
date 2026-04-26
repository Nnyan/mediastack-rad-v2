<template>
  <div>
    <h1 class="page-title">
      Traefik & HTTPS
      <span class="sub">routing, certificates, DNS</span>
    </h1>

    <div class="card-row">
      <div class="card status-card">
        <h3 class="section-title">Status</h3>
        <div class="status-grid">
          <div class="status-item">
            <span class="dot" :class="pingClass"></span>
            <span>Traefik API</span>
            <span class="mono small muted">{{ pingMsg }}</span>
          </div>
          <div class="status-item">
            <span class="dot" :class="apiVersionClass"></span>
            <span>Cloudflare API</span>
            <span class="mono small muted">{{ cfMsg }}</span>
          </div>
          <div class="status-item">
            <span class="dot" :class="acmeClass"></span>
            <span>ACME storage</span>
            <span class="mono small muted">{{ acmeMsg }}</span>
          </div>
        </div>
      </div>

      <div class="card tools-card">
        <h3 class="section-title">Cleanup tools</h3>
        <p class="small muted mb-2">
          If DNS-01 challenges are failing with "time limit exceeded",
          stale <code>_acme-challenge</code> TXT records in Cloudflare can
          poison propagation checks. Use the cleanup button to wipe them.
        </p>
        <div class="tool-actions">
          <button @click="cleanupAcmeJson">Fix acme.json permissions</button>
          <button @click="restartTraefik">Restart Traefik</button>
        </div>
        <pre v-if="toolOutput" class="mono preview mt-3">{{ toolOutput }}</pre>
      </div>
    </div>

    <div class="card routes-card">
      <h3 class="section-title">Routes</h3>
      <p class="small muted mb-3">
        These are the hosts Traefik is currently serving. A green dot
        means the router is up and has a valid cert; amber means the
        router exists but no cert is issued yet; red means something is
        wrong (check Settings → Health).
      </p>
      <table>
        <thead>
          <tr>
            <th>Router</th>
            <th>Host</th>
            <th>Service</th>
            <th>TLS</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in routers" :key="r.name">
            <td class="mono">{{ r.name }}</td>
            <td class="mono">
              <a :href="`https://${r.host}`" target="_blank" v-if="r.host">
                {{ r.host }}
              </a>
              <span v-else class="muted">—</span>
            </td>
            <td class="mono small">{{ r.service }}</td>
            <td>
              <span v-if="r.tls" class="dot ok"></span>
              <span v-else class="dot off"></span>
              <span class="small mono">{{ r.tls ? 'on' : 'off' }}</span>
            </td>
            <td>
              <span class="badge-status" :class="r.statusClass">{{ r.status }}</span>
            </td>
          </tr>
          <tr v-if="routers.length === 0">
            <td colspan="5" class="muted">No routers registered yet.</td>
          </tr>
        </tbody>
      </table>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, inject } from 'vue'

const showToast = inject('showToast')

// Traefik API runs on port 8081 of the Traefik container. We call
// through the RAD backend which proxies — or, in the simple case,
// directly via window.location since Traefik is on the same host.
// To stay simple we expose a small relay endpoint if needed.

const routers = ref([])
const pingMsg = ref('checking…')
const pingClass = ref('off')
const cfMsg = ref('checking…')
const apiVersionClass = ref('off')
const acmeMsg = ref('checking…')
const acmeClass = ref('off')
const toolOutput = ref('')

let pollTimer = null

async function refresh() {
  // Pull the current health report — it already checks CF token and ACME.
  try {
    const h = await fetch('/api/health').then(r => r.json())
    const cfIssue = (h.issues || []).find(i => i.id.startsWith('cloudflare.'))
    if (cfIssue) {
      cfMsg.value = cfIssue.title
      apiVersionClass.value = cfIssue.severity === 'error' ? 'err' : 'warn'
    } else {
      cfMsg.value = 'valid'
      apiVersionClass.value = 'ok'
    }
    const acmeIssue = (h.issues || []).find(i => i.id.startsWith('acme.'))
    if (acmeIssue) {
      acmeMsg.value = acmeIssue.title
      acmeClass.value = 'err'
    } else {
      acmeMsg.value = 'mode 0600'
      acmeClass.value = 'ok'
    }
  } catch (e) {
    cfMsg.value           = 'check failed'
    apiVersionClass.value = 'warn'
    acmeMsg.value         = 'check failed'
    acmeClass.value       = 'warn'
    console.error('Traefik health check failed:', e)
  }

  // Fetch Traefik routers through the RAD backend proxy (/api/traefik/routers)
  // rather than directly at http://host:8081. Direct http:// fetches are blocked
  // as mixed content when RAD is served over HTTPS.
  try {
    const r = await fetch('/api/traefik/routers')
    if (r.ok) {
      const data = await r.json()
      routers.value = data
        .filter(router => !router.name.endsWith('@internal'))
        .map(router => ({
          name:        router.name,
          host:        extractHost(router.rule),
          service:     router.service,
          tls:         !!router.tls,
          status:      router.status,
          statusClass: router.status === 'enabled' ? 'ok' : 'warn',
        }))
      pingMsg.value   = `${routers.value.length} routers`
      pingClass.value = 'ok'
    } else {
      pingMsg.value   = `HTTP ${r.status}`
      pingClass.value = 'err'
    }
  } catch (e) {
    pingMsg.value   = 'unreachable'
    pingClass.value = 'off'
  }
}

function extractHost(rule) {
  // rule looks like: Host(`sonarr.example.com`)
  const m = /Host\(`([^`]+)`\)/.exec(rule || '')
  return m ? m[1] : ''
}

async function cleanupAcmeJson() {
  if (!confirm('Fix acme.json permissions? This sets the file to mode 0600 as required by Traefik.')) return
  try {
    const r = await fetch('/api/health/fix/acme.perms', { method: 'POST' })
    const data = await r.json()
    toolOutput.value = data.message
    showToast(data.ok ? 'acme.json permissions set to 0600' : data.message,
              data.ok ? 'ok' : 'err')
  } catch (e) {
    toolOutput.value = String(e)
  }
}

async function restartTraefik() {
  try {
    const r = await fetch('/api/containers/traefik/restart', { method: 'POST' })
    if (r.ok) {
      showToast('Traefik restarted')
      setTimeout(refresh, 3000)
    } else {
      showToast('Restart failed', 'err')
    }
  } catch (e) {
    showToast(`Error: ${e.message}`, 'err')
  }
}

onMounted(() => {
  refresh()
  pollTimer = setInterval(refresh, 10000)
})
onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
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

.status-grid {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}
.status-item {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: 6px 12px;
  background: var(--bg-0);
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  flex: 1 1 180px;
  min-height: 38px;
}

.badge-status {
  font-family: var(--font-mono);
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  background: var(--bg-2);
  color: var(--fg-1);
}
.badge-status.ok { background: var(--ok-dim); color: var(--ok); }
.badge-status.warn { background: var(--warn-dim); color: var(--warn); }
.badge-status.err { background: var(--err-dim); color: var(--err); }

.preview {
  max-height: 260px;
  overflow: auto;
  background: var(--bg-0);
  padding: var(--space-3);
  border-radius: var(--radius);
  border: 1px solid var(--border);
  font-size: 12px;
}
.mt-3 { margin-top: var(--space-3); }

.card-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}
.card-row .card {
  flex: 1 1 320px;
  margin-bottom: 0;
}
.status-card,
.tools-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.tool-actions {
  display: flex;
  flex-wrap: nowrap;
  gap: var(--space-2);
}
.tool-actions button {
  flex: 1 1 50%;
  white-space: nowrap;
}
.routes-card { margin-top: 0; }

@media (max-width: 640px) {
  .status-grid { flex-wrap: wrap; }
  .tool-actions { flex-wrap: wrap; }
  .tool-actions button { flex: 1 1 100%; }
}
</style>
