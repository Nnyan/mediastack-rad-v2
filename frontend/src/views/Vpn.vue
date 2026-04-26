<template>
  <div class="vpn-page">
    <h1 class="page-title">
      VPN
      <span class="sub">private ingress and app egress routing</span>
    </h1>

    <div class="vpn-grid">
      <section class="vpn-card tailscale" :class="tailscaleState">
        <div class="vpn-card-head">
          <div>
            <h2>Tailscale</h2>
            <p>Private access into the stack from enrolled devices.</p>
          </div>
          <span class="status-pill" :class="tailscaleState">{{ tailscaleLabel }}</span>
        </div>

        <div class="signal-row">
          <div class="signal" :class="okClass(ts.present)"><span>Container</span><strong>{{ ts.status || 'missing' }}</strong></div>
          <div class="signal" :class="okClass(ts.kernel_mode)"><span>Kernel Mode</span><strong>{{ ts.kernel_mode ? 'on' : 'off' }}</strong></div>
          <div class="signal" :class="okClass(ts.has_net_admin && ts.has_net_raw && ts.has_tun_device)"><span>TUN Access</span><strong>{{ tunLabel }}</strong></div>
          <div class="signal" :class="okClass(ts.online !== false && (ts.tailscale_ips || []).length)"><span>Tunnel</span><strong>{{ tunnelLabel }}</strong></div>
        </div>

        <div class="info-grid">
          <div><span>Hostname</span><strong>{{ ts.hostname || 'not set' }}</strong></div>
          <div><span>Backend</span><strong>{{ ts.backend_state || 'unknown' }}</strong></div>
          <div><span>Tailscale IPs</span><strong>{{ list(ts.tailscale_ips) }}</strong></div>
          <div><span>Peers</span><strong>{{ ts.peer_count ?? 0 }}</strong></div>
          <div class="wide"><span>Configured Routes</span><strong>{{ list(ts.configured_routes) }}</strong></div>
          <div class="wide"><span>Active Routes</span><strong>{{ list(ts.active_routes) }}</strong></div>
        </div>

        <div v-if="ts.issues?.length" class="issues">
          <div v-for="issue in ts.issues" :key="issue">{{ issue }}</div>
        </div>
      </section>

      <section class="vpn-card egress" :class="egressState">
        <div class="vpn-card-head">
          <div>
            <h2>Egress VPN</h2>
            <p>Outbound VPN routing for selected apps, such as ProtonVPN.</p>
          </div>
          <span class="status-pill" :class="egressState">{{ egressLabel }}</span>
        </div>

        <div v-if="eg.providers?.length" class="provider-list">
          <div v-for="provider in eg.providers" :key="provider.name" class="provider-row">
            <span class="provider-dot" :class="provider.status === 'running' ? 'ok' : 'warn'"></span>
            <div>
              <strong>{{ provider.name }}</strong>
              <span>{{ provider.image }}</span>
            </div>
            <em>{{ provider.status }}</em>
          </div>
        </div>
        <div v-else class="empty-vpn">
          No egress VPN provider is configured yet. Add Gluetun from Stack Builder to enable ProtonVPN-backed app routing.
        </div>

        <div class="routed-apps">
          <div class="mini-title">Routed Apps</div>
          <div v-if="eg.routed_apps?.length" class="routed-list">
            <div v-for="app in eg.routed_apps" :key="app.name" class="routed-row" :class="app.actual ? 'ok' : 'warn'">
              <strong>{{ app.name }}</strong>
              <span>{{ app.actual ? 'using Gluetun' : 'expected but not routed' }}</span>
            </div>
          </div>
          <div v-else class="empty-mini">No apps are marked for Gluetun routing yet.</div>
          <div v-if="eg.routing_issues?.length" class="issues">
            <div v-for="issue in eg.routing_issues" :key="issue">{{ issue }}</div>
          </div>
        </div>

        <div class="future-flow">
          <span>Selected App</span>
          <span class="flow-link"></span>
          <span>VPN Provider</span>
          <span class="flow-link"></span>
          <span>Internet</span>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

const status = ref({ tailscale: {}, egress_vpn: {} })
let timer = null

const ts = computed(() => status.value.tailscale || {})
const eg = computed(() => status.value.egress_vpn || {})

const tailscaleState = computed(() => {
  if (!ts.value.present || ts.value.status !== 'running') return 'err'
  if (!ts.value.kernel_mode || !ts.value.has_net_admin || !ts.value.has_net_raw || !ts.value.has_tun_device) return 'warn'
  if (ts.value.online === false || !(ts.value.tailscale_ips || []).length) return 'warn'
  return 'ok'
})
const tailscaleLabel = computed(() => tailscaleState.value === 'ok' ? 'connected' : tailscaleState.value === 'warn' ? 'attention' : 'offline')
const tunnelLabel = computed(() => (ts.value.tailscale_ips || []).length ? 'connected' : 'not connected')
const tunLabel = computed(() => ts.value.has_net_admin && ts.value.has_net_raw && ts.value.has_tun_device ? 'ready' : 'missing')
const egressState = computed(() => eg.value.status === 'running' ? 'ok' : eg.value.present ? 'warn' : 'off')
const egressLabel = computed(() => eg.value.status === 'running' ? 'running' : eg.value.present ? 'stopped' : 'planned')

function list(value) {
  return Array.isArray(value) && value.length ? value.join(', ') : 'none'
}
function okClass(value) { return value ? 'ok' : 'warn' }

async function refresh() {
  try {
    status.value = await fetch('/api/vpn/status').then(r => r.json())
  } catch (e) {
    status.value = { tailscale: { present: false, status: 'unreachable', issues: [String(e)] }, egress_vpn: {} }
  }
}

onMounted(() => { refresh(); timer = setInterval(refresh, 10000) })
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>

<style scoped>
.vpn-page { max-width: 820px; margin: 0 auto; }
.vpn-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: var(--space-3); }
.vpn-card {
  background: var(--bg-1); border: 1.5px solid var(--border); border-radius: var(--radius);
  padding: 8px 12px 10px; box-shadow: var(--shadow-1); display: flex; flex-direction: column; gap: 8px;
}
.vpn-card.ok { border-color: rgba(22,163,74,0.35); background: linear-gradient(135deg, var(--ok-bg), var(--bg-1)); }
.vpn-card.warn { border-color: rgba(217,119,6,0.4); background: linear-gradient(135deg, var(--warn-bg), var(--bg-1)); }
.vpn-card.err { border-color: rgba(220,38,38,0.4); background: linear-gradient(135deg, var(--err-bg), var(--bg-1)); }
.vpn-card-head { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--space-2); }
.vpn-card h2 { margin: 0 0 2px; font-size: 13px; }
.vpn-card p { margin: 0; color: var(--fg-2); font-size: 10.5px; line-height: 1.25; }
.status-pill { font-size: 9px; font-weight: 800; text-transform: uppercase; padding: 2px 7px; border-radius: 999px; background: var(--bg-2); }
.status-pill.ok { color: var(--ok); background: var(--ok-bg); }
.status-pill.warn { color: var(--warn); background: var(--warn-bg); }
.status-pill.err { color: var(--err); background: var(--err-bg); }
.status-pill.off { color: var(--fg-2); }
.signal-row { display: grid; grid-template-columns: repeat(2, 1fr); gap: 5px; }
.signal { border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 5px 7px; background: var(--bg-0); }
.signal.ok { border-color: rgba(22,163,74,0.35); }
.signal.warn { border-color: rgba(217,119,6,0.35); }
.signal span, .info-grid span { display: block; font-size: 8.5px; color: var(--fg-2); text-transform: uppercase; letter-spacing: 0.06em; }
.signal strong, .info-grid strong { display: block; margin-top: 2px; font-size: 10.5px; color: var(--fg-0); word-break: break-word; }
.info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 5px; }
.info-grid > div { background: var(--bg-0); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 5px 7px; }
.info-grid .wide { grid-column: 1 / -1; }
.issues { color: var(--warn); font-size: 10.5px; display: grid; gap: 3px; }
.provider-list { display: grid; gap: 5px; }
.provider-row { display: grid; grid-template-columns: auto 1fr auto; gap: 8px; align-items: center; background: var(--bg-0); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 5px 7px; }
.provider-row span:not(.provider-dot) { display: block; color: var(--fg-2); font-size: 11px; margin-top: 2px; }
.provider-dot { width: 9px; height: 9px; border-radius: 50%; background: var(--warn); }
.provider-dot.ok { background: var(--ok); }
.empty-vpn, .empty-mini { color: var(--fg-2); font-size: 11px; background: var(--bg-0); border: 1px dashed var(--border-strong); border-radius: var(--radius-sm); padding: 8px; }
.mini-title { font-size: 10px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.07em; color: var(--fg-2); margin-bottom: 5px; }
.routed-list { display: grid; gap: 4px; }
.routed-row { display: flex; justify-content: space-between; gap: 8px; font-size: 11px; padding: 5px 7px; border-radius: var(--radius-sm); border: 1px solid var(--border); background: var(--bg-0); }
.routed-row.ok { border-color: rgba(22,163,74,0.35); }
.routed-row.warn { border-color: rgba(217,119,6,0.35); color: var(--warn); }
.future-flow { display: flex; align-items: center; justify-content: center; gap: 6px; color: var(--fg-1); font-size: 10.5px; }
.flow-link { width: 42px; height: 3px; border-radius: 999px; background: linear-gradient(90deg, var(--purple), var(--blue)); }
@media (max-width: 720px) { .signal-row { grid-template-columns: 1fr 1fr; } }
</style>
