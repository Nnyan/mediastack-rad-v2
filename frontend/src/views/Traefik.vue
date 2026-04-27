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

    <div class="card route-map-card">
      <div class="route-map-head">
        <div>
          <h3 class="section-title">Route Map</h3>
          <p class="small muted">Live topology from Cloudflare/DNS through Traefik to each app.</p>
        </div>
        <span class="small mono muted">{{ routers.length }} route{{ routers.length !== 1 ? 's' : '' }}</span>
      </div>
      <div class="route-map">
        <div v-for="r in routers" :key="`map-${r.name}`" class="route-lane" :class="routeOverallClass(r)">
          <div class="route-host">
            <strong>{{ r.host || r.name }}</strong>
            <span>{{ r.name }}</span>
          </div>
          <div class="topology-flow">
            <div class="topo-node" :class="statusClass(r.dns_status, 'dns')">
              <span>DNS</span><strong>{{ r.dns_status }}</strong>
            </div>
            <div class="topo-link" :class="statusClass(r.dns_status, 'dns')"></div>
            <div class="topo-node" :class="statusClass(r.tunnel_status, 'tunnel')">
              <span>Tunnel</span><strong>{{ r.tunnel_status }}</strong>
            </div>
            <div class="topo-link" :class="statusClass(r.tunnel_status, 'tunnel')"></div>
            <div class="topo-node" :class="statusClass(r.router_status, 'router')">
              <span>Traefik</span><strong>{{ r.router_status }}</strong>
            </div>
            <div class="topo-link" :class="statusClass(r.cert_status, 'cert')"></div>
            <div class="topo-node" :class="statusClass(r.cert_status, 'cert')">
              <span>Cert</span><strong>{{ r.cert_status }}</strong>
            </div>
            <div class="topo-link" :class="statusClass(r.router_status, 'router')"></div>
            <div class="topo-node service ok">
              <span>Service</span><strong>{{ r.service }}</strong>
            </div>
          </div>
        </div>
        <div v-if="!routers.length" class="muted route-empty">No route topology available yet.</div>
      </div>
    </div>

    <div class="card routes-card">
      <h3 class="section-title">Routes</h3>
      <p class="small muted mb-3">
        TLS Config means Traefik is configured for HTTPS. DNS, certificate
        coverage, and Cloudflare Tunnel status are checked separately.
      </p>
      <table>
        <thead>
          <tr>
            <th>Router</th>
            <th>Host</th>
            <th>Service</th>
            <th>Router</th>
            <th>TLS Config</th>
            <th>Cert</th>
            <th>DNS</th>
            <th>Tunnel</th>
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
              <span class="badge-status" :class="statusClass(r.router_status, 'router')">{{ r.router_status }}</span>
            </td>
            <td>
              <span class="badge-status" :class="statusClass(r.tls_config, 'tls')">{{ r.tls_config }}</span>
            </td>
            <td>
              <span class="badge-status" :class="statusClass(r.cert_status, 'cert')">{{ r.cert_status }}</span>
            </td>
            <td>
              <span class="badge-status" :class="statusClass(r.dns_status, 'dns')" :title="(r.dns_addresses || []).join(', ')">{{ r.dns_status }}</span>
            </td>
            <td>
              <span class="badge-status" :class="statusClass(r.tunnel_status, 'tunnel')" :title="r.tunnel_detail">{{ r.tunnel_status }}</span>
            </td>
          </tr>
          <tr v-if="routers.length === 0">
            <td colspan="8" class="muted">No routers registered yet.</td>
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

  // Fetch enriched route status through RAD so DNS/cert checks happen server-side.
  try {
    const r = await fetch('/api/traefik/route-status')
    if (r.ok) {
      const data = await r.json()
      routers.value = data.routes || []
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

function statusClass(value, kind) {
  if (['enabled', 'configured', 'covered', 'resolves'].includes(value)) return 'ok'
  if (['off', 'missing', 'disabled', 'stopped'].includes(value)) return kind === 'tls' ? 'off' : 'err'
  return 'warn'
}

function routeOverallClass(route) {
  const statuses = [
    statusClass(route.router_status, 'router'),
    statusClass(route.tls_config, 'tls'),
    statusClass(route.cert_status, 'cert'),
    statusClass(route.dns_status, 'dns'),
    statusClass(route.tunnel_status, 'tunnel'),
  ]
  if (statuses.includes('err')) return 'err'
  if (statuses.includes('warn')) return 'warn'
  return 'ok'
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
  margin: 0 0 4px;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--fg-2);
  font-weight: 600;
}

.status-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}
.status-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 7px;
  background: var(--bg-0);
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  flex: 1 1 180px;
  min-height: 22px;
  font-size: 11px;
}

.badge-status {
  font-family: var(--font-mono);
  font-size: 10px;
  padding: 1px 6px;
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
  gap: var(--space-2);
  margin-bottom: var(--space-3);
}
.card-row .card {
  flex: 1 1 320px;
  margin-bottom: 0;
  padding: 7px 9px;
}
.status-card,
.tools-card {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.tools-card p {
  margin: 0;
  line-height: 1.2;
  font-size: 11px;
}
.tool-actions {
  display: flex;
  flex-wrap: nowrap;
  gap: 5px;
}
.tool-actions button {
  flex: 1 1 50%;
  white-space: nowrap;
  padding: 3px 7px;
  font-size: 11px;
}
.routes-card { margin-top: 0; }
.routes-card table { width: 100%; border-collapse: collapse; }
.routes-card thead th {
  font-size: 10px;
  letter-spacing: 0.04em;
  padding: 6px 8px;
}
.routes-card tbody td {
  padding: 5px 8px;
  font-size: 11px;
  line-height: 1.2;
}

.route-map-card { margin-bottom: var(--space-3); }
.route-map-head { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--space-3); }
.route-map-head p { margin: 0; }
.route-map { display: grid; gap: 6px; }
.route-lane {
  display: grid;
  grid-template-columns: minmax(160px, 240px) 1fr;
  gap: 10px;
  align-items: center;
  padding: 8px;
  border-radius: var(--radius);
  border: 1px solid var(--border);
  background: var(--bg-0);
}
.route-lane.ok { border-color: rgba(22,163,74,0.28); background: linear-gradient(90deg, var(--ok-bg), var(--bg-0)); }
.route-lane.warn { border-color: rgba(217,119,6,0.35); background: linear-gradient(90deg, var(--warn-bg), var(--bg-0)); }
.route-lane.err { border-color: rgba(220,38,38,0.35); background: linear-gradient(90deg, var(--err-bg), var(--bg-0)); }
.route-host { min-width: 0; }
.route-host strong { display: block; font-size: 12px; color: var(--fg-0); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.route-host span { display: block; margin-top: 2px; font-family: var(--font-mono); font-size: 10px; color: var(--fg-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.topology-flow { display: grid; grid-template-columns: auto 1fr auto 1fr auto 1fr auto 1fr auto; align-items: center; gap: 4px; min-width: 0; }
.topo-node {
  min-width: 64px;
  padding: 4px 6px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: var(--bg-1);
  text-align: center;
  box-shadow: var(--shadow-1);
}
.topo-node span { display: block; font-size: 8.5px; color: var(--fg-2); text-transform: uppercase; letter-spacing: 0.06em; }
.topo-node strong { display: block; margin-top: 1px; font-size: 10.5px; color: var(--fg-0); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 96px; }
.topo-node.ok { border-color: rgba(22,163,74,0.45); background: var(--ok-bg); }
.topo-node.warn { border-color: rgba(217,119,6,0.5); background: var(--warn-bg); }
.topo-node.err { border-color: rgba(220,38,38,0.5); background: var(--err-bg); }
.topo-node.off { opacity: 0.65; }
.topo-link { height: 3px; border-radius: 999px; background: var(--border-strong); min-width: 20px; position: relative; overflow: hidden; }
.topo-link.ok { background: linear-gradient(90deg, #22c55e, #16a34a); box-shadow: 0 0 8px rgba(22,163,74,0.35); }
.topo-link.warn { background: linear-gradient(90deg, #f59e0b, #d97706); box-shadow: 0 0 8px rgba(217,119,6,0.25); }
.topo-link.err { background: linear-gradient(90deg, #ef4444, #dc2626); box-shadow: 0 0 8px rgba(220,38,38,0.25); }
.topo-link.off { background: var(--border); }
.route-empty { padding: var(--space-3); text-align: center; }

@media (max-width: 900px) {
  .route-lane { grid-template-columns: 1fr; }
  .topology-flow { grid-template-columns: 1fr; }
  .topo-link { width: 4px; height: 18px; justify-self: center; }
}

@media (max-width: 640px) {
  .status-grid { flex-wrap: wrap; }
  .tool-actions { flex-wrap: wrap; }
  .tool-actions button { flex: 1 1 100%; }
}
</style>
