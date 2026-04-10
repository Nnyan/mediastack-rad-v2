<template>
  <div class="page">

    <!-- Header -->
    <div class="page-header flex items-center gap-3">
      <div class="page-title">Traefik &amp; HTTPS</div>
      <div style="flex:1" />
      <button class="btn btn-sm" :disabled="statusLoading" @click="loadStatus">
        <span v-if="statusLoading" class="spinner" style="width:12px;height:12px" />
        <span v-else>↺</span> Refresh
      </button>
    </div>

    <!-- Traefik status pill -->
    <div style="display:flex;gap:10px;align-items:center;margin-bottom:18px;flex-wrap:wrap">
      <div :style="`display:inline-flex;align-items:center;gap:6px;padding:5px 12px;border-radius:20px;font-size:11px;font-weight:600;border:1px solid ${tStatusColor}40;background:${tStatusColor}15;color:${tStatusColor}`">
        <span style="width:7px;height:7px;border-radius:50%;background:currentColor;display:inline-block" />
        {{ tStatusLabel }}
      </div>
      <span v-if="status?.traefik?.version" style="font-size:11px;color:var(--muted)">v{{ status.traefik.version }}</span>
      <span v-if="status?.traefik?.total_routes != null" style="font-size:11px;color:var(--muted)">
        {{ status.traefik.total_routes }} active routes
      </span>
      <div style="flex:1" />
      <div v-if="status?.summary" style="display:flex;gap:12px">
        <span style="font-size:11px;color:var(--muted)">
          Configured: <strong style="color:var(--text)">{{ status.summary.configured }}/{{ status.summary.total }}</strong>
        </span>
        <span style="font-size:11px;color:var(--muted)">
          Verified: <strong style="color:var(--primary)">{{ status.summary.verified }}</strong>
        </span>
      </div>
    </div>

    <!-- Two-column layout -->
    <div style="display:grid;grid-template-columns:340px 1fr;gap:16px;align-items:start">

      <!-- LEFT: Config panel -->
      <div>
        <div class="card" style="margin-bottom:12px">
          <div class="section-title" style="margin-bottom:12px">Domain &amp; certificate</div>

          <label style="display:block;margin-bottom:10px">
            <div style="font-size:11px;color:var(--muted);margin-bottom:4px">Base domain</div>
            <input v-model="cfg.domain" class="search-input" style="width:100%;max-width:none"
              placeholder="example.com" @change="dirty=true" />
            <div style="font-size:10px;color:var(--muted);margin-top:3px">Apps will be served as app.example.com</div>
          </label>

          <div style="margin-bottom:10px">
            <div style="font-size:11px;color:var(--muted);margin-bottom:6px">Certificate type</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">
              <button v-for="opt in CERT_TYPES" :key="opt.val"
                :style="`padding:8px 10px;border-radius:6px;border:1px solid ${cfg.cert_type===opt.val?'var(--primary)':'var(--border)'};background:${cfg.cert_type===opt.val?'var(--primary-d)':'transparent'};color:${cfg.cert_type===opt.val?'#fff':'var(--text)'};cursor:pointer;font-size:11px;text-align:left`"
                @click="cfg.cert_type=opt.val;dirty=true">
                <div style="font-weight:600;margin-bottom:2px">{{ opt.label }}</div>
                <div style="font-size:10px;opacity:0.8">{{ opt.desc }}</div>
              </button>
            </div>
          </div>

          <label style="display:block;margin-bottom:10px" v-if="cfg.cert_type==='http'">
            <div style="font-size:11px;color:var(--muted);margin-bottom:4px">Cert resolver name</div>
            <input v-model="cfg.certresolver" class="search-input" style="width:100%;max-width:none"
              placeholder="letsencrypt" @change="dirty=true" />
            <div style="font-size:10px;color:var(--muted);margin-top:3px">Must match your Traefik certificatesResolvers config key</div>
          </label>

          <label style="display:block;margin-bottom:10px">
            <div style="font-size:11px;color:var(--muted);margin-bottom:4px">Traefik API URL</div>
            <input v-model="cfg.traefik_api_url" class="search-input" style="width:100%;max-width:none"
              placeholder="http://traefik:8080" @change="dirty=true" />
          </label>

          <label style="display:block;margin-bottom:10px">
            <div style="font-size:11px;color:var(--muted);margin-bottom:4px">HTTPS entrypoint name</div>
            <input v-model="cfg.entrypoint_https" class="search-input" style="width:100%;max-width:none"
              placeholder="websecure" @change="dirty=true" />
          </label>

          <label style="display:block;margin-bottom:14px">
            <div style="font-size:11px;color:var(--muted);margin-bottom:4px">Middleware (optional)</div>
            <input v-model="cfg.middleware" class="search-input" style="width:100%;max-width:none"
              placeholder="authelia@docker" @change="dirty=true" />
            <div style="font-size:10px;color:var(--muted);margin-top:3px">Applied to all generated routers (e.g. for SSO)</div>
          </label>

          <div style="display:flex;gap:8px">
            <button class="btn btn-primary btn-sm" :disabled="!dirty || saving" @click="saveCfg">
              <span v-if="saving" class="spinner" style="width:11px;height:11px" /> Save config
            </button>
            <span v-if="saveMsg" style="font-size:11px;color:var(--primary);align-self:center">{{ saveMsg }}</span>
          </div>
        </div>

        <!-- Wildcard DNS instructions -->
        <div v-if="cfg.cert_type==='wildcard'" class="card" style="margin-bottom:12px">
          <div class="section-title" style="margin-bottom:8px">Wildcard cert setup</div>
          <div style="font-size:11px;color:var(--muted);line-height:1.7">
            Wildcard certs require a <strong style="color:var(--text)">DNS-01 challenge</strong> — Traefik needs credentials for your DNS provider to create the <code>_acme-challenge</code> TXT record.<br><br>
            In your Traefik static config (traefik.yml):
          </div>
          <pre style="background:var(--bg);border:1px solid var(--border);border-radius:4px;padding:8px;font-size:10px;font-family:var(--mono);margin:8px 0;overflow-x:auto;line-height:1.6">certificatesResolvers:
  letsencrypt:
    acme:
      email: you@{{ cfg.domain || 'example.com' }}
      storage: /letsencrypt/acme.json
      dnsChallenge:
        provider: cloudflare   # or route53, digitalocean…
        resolvers:
          - "1.1.1.1:53"</pre>
          <div style="font-size:11px;color:var(--muted)">
            Set your DNS provider credentials as env vars on the Traefik container (e.g. <code>CF_DNS_API_TOKEN</code> for Cloudflare).
          </div>
        </div>

        <!-- HTTP challenge notes -->
        <div v-else class="card" style="margin-bottom:12px">
          <div class="section-title" style="margin-bottom:8px">HTTP-01 challenge setup</div>
          <div style="font-size:11px;color:var(--muted);line-height:1.7">
            Each app gets its own certificate. Requires port 80 reachable from the internet for the ACME challenge.<br><br>
            In your Traefik static config:
          </div>
          <pre style="background:var(--bg);border:1px solid var(--border);border-radius:4px;padding:8px;font-size:10px;font-family:var(--mono);margin:8px 0;overflow-x:auto;line-height:1.6">certificatesResolvers:
  {{ cfg.certresolver || 'letsencrypt' }}:
    acme:
      email: you@{{ cfg.domain || 'example.com' }}
      storage: /letsencrypt/acme.json
      httpChallenge:
        entryPoint: web</pre>
        </div>

        <!-- Export all labels -->
        <div class="card">
          <div class="section-title" style="margin-bottom:8px">Export labels for all apps</div>
          <div style="font-size:11px;color:var(--muted);margin-bottom:10px">
            Generates a compose-compatible YAML block with Traefik labels for every container. Paste into your existing docker-compose.yml under each service.
          </div>
          <button class="btn btn-sm" :disabled="composeLoading" @click="loadCompose">
            <span v-if="composeLoading" class="spinner" style="width:11px;height:11px" /> Generate compose snippet
          </button>
          <div v-if="composeYaml" style="margin-top:10px">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
              <span style="font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.06em">docker-compose.yml snippet</span>
              <button class="btn btn-sm" style="font-size:10px;padding:2px 8px" @click="copyText(composeYaml)">{{ copied ? '✓ Copied' : 'Copy' }}</button>
            </div>
            <pre style="background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:10px;font-size:10px;font-family:var(--mono);max-height:280px;overflow-y:auto;line-height:1.6;white-space:pre">{{ composeYaml }}</pre>
          </div>
        </div>
      </div>

      <!-- RIGHT: Container table -->
      <div>
        <div style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.07em;color:var(--muted);margin-bottom:8px">
          Container routing status
        </div>

        <div v-if="statusLoading && !status" class="flex items-center gap-2 text-muted">
          <span class="spinner" /> Checking Traefik routes…
        </div>

        <div v-else-if="!cfg.domain" class="alert alert-info" style="margin-bottom:0">
          Set a base domain above to generate routing labels.
        </div>

        <div v-else style="display:grid;gap:8px">
          <div v-for="c in (status?.containers || [])" :key="c.id"
            :style="`background:var(--surface);border:1px solid ${rowBorder(c)};border-radius:8px;overflow:hidden`">

            <!-- Row header -->
            <div style="padding:10px 14px;display:flex;align-items:center;gap:8px;cursor:pointer"
              @click="toggleExpand(c.id)">
              <div style="display:flex;align-items:center;gap:6px;flex:1;min-width:0">
                <!-- Traffic light -->
                <span :title="rowTitle(c)" :style="`width:9px;height:9px;border-radius:50%;flex-shrink:0;background:${rowDot(c)}`" />
                <span style="font-family:var(--mono);font-size:12px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
                  {{ c.name }}
                </span>
                <span v-if="c.status!=='running'" class="badge badge-exited" style="font-size:9px">stopped</span>
              </div>

              <div style="display:flex;align-items:center;gap:8px;flex-shrink:0">
                <a v-if="c.expected_url && c.route_live" :href="c.expected_url" target="_blank"
                  style="font-size:10px;color:var(--info,#388bfd);font-family:var(--mono)" @click.stop>
                  {{ c.expected_url }} ↗
                </a>
                <span v-else-if="c.expected_url" style="font-size:10px;color:var(--muted);font-family:var(--mono)">
                  {{ c.expected_url }}
                </span>
                <span :style="`font-size:10px;font-weight:600;padding:2px 8px;border-radius:20px;background:${routeStatBg(c)};color:${routeStatColor(c)}`">
                  {{ routeStatLabel(c) }}
                </span>
                <span style="color:var(--muted);font-size:11px">{{ expanded.has(c.id) ? '▲' : '▼' }}</span>
              </div>
            </div>

            <!-- Expanded detail -->
            <div v-if="expanded.has(c.id)" style="border-top:1px solid var(--border);padding:12px 14px;background:var(--surface2)">
              <!-- Label checklist -->
              <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:12px">
                <div v-for="check in labelChecks(c)" :key="check.label"
                  :style="`padding:6px 10px;border-radius:6px;border:1px solid ${check.ok?'#2ea04340':'#da363340'};background:${check.ok?'#2ea04312':'#da363312'};text-align:center`">
                  <div style="font-size:16px">{{ check.ok ? '✓' : '✗' }}</div>
                  <div style="font-size:10px;font-weight:600;color:var(--text);margin-top:2px">{{ check.label }}</div>
                </div>
              </div>

              <!-- Suggested labels YAML -->
              <div style="margin-bottom:10px">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
                  <span style="font-size:10px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:0.06em">
                    Labels to add to docker-compose.yml
                  </span>
                  <button class="btn btn-sm" style="font-size:10px;padding:2px 8px" @click="copyText(c.labels_yaml)">
                    {{ copiedId===c.id ? '✓ Copied' : 'Copy' }}
                  </button>
                </div>
                <pre style="background:var(--bg);border:1px solid var(--border);border-radius:4px;padding:8px;font-size:10px;font-family:var(--mono);margin:0;line-height:1.6;white-space:pre">{{ c.labels_yaml }}</pre>
              </div>

              <!-- How to apply -->
              <div style="background:#388bfd12;border:1px solid #388bfd30;border-radius:6px;padding:10px 12px;font-size:11px;color:var(--muted);line-height:1.7">
                <strong style="color:var(--info,#388bfd)">How to apply:</strong>
                Add the labels block above to the <code>{{ c.name }}</code> service in your docker-compose.yml, then run:<br>
                <code style="display:block;margin-top:6px;background:var(--bg);padding:5px 8px;border-radius:4px;font-size:10px">
                  docker compose up -d --no-deps {{ c.name }}
                </code>
                The container will be recreated with the new labels and Traefik will detect it automatically.
              </div>

              <!-- Verified badge -->
              <div v-if="c.route_live" style="margin-top:10px;display:flex;align-items:center;gap:6px;font-size:11px;color:var(--primary)">
                <span>✓</span> Route confirmed active in Traefik — status: <strong>{{ c.route_status }}</strong>
              </div>
              <div v-else-if="c.configured" style="margin-top:10px;font-size:11px;color:var(--warning)">
                Labels applied but route not yet visible in Traefik API. Traefik may still be processing, or the container needs restarting.
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";
import { API } from "@/composables/useApi.js";

const cfg         = ref({ domain: "", cert_type: "http", certresolver: "letsencrypt", entrypoint_https: "websecure", traefik_api_url: "http://traefik:8080", middleware: "" });
const status      = ref(null);
const dirty       = ref(false);
const saving      = ref(false);
const saveMsg     = ref("");
const statusLoading = ref(false);
const composeYaml = ref("");
const composeLoading = ref(false);
const expanded    = ref(new Set());
const copied      = ref(false);
const copiedId    = ref(null);

const CERT_TYPES = [
  { val: "http",     label: "Per-app cert",  desc: "HTTP-01 challenge, one cert per subdomain" },
  { val: "wildcard", label: "Wildcard cert", desc: "DNS-01 challenge, *.domain.com shared cert" },
];

const tStatusLabel = computed(() => {
  if (!status.value) return "Checking…";
  const t = status.value.traefik;
  if (!t.running)       return "Traefik not running";
  if (!t.api_reachable) return "Traefik running — API unreachable";
  return "Traefik running & API connected";
});
const tStatusColor = computed(() => {
  if (!status.value) return "var(--muted)";
  const t = status.value.traefik;
  if (!t.running)       return "var(--danger)";
  if (!t.api_reachable) return "var(--warning)";
  return "var(--primary)";
});

function rowBorder(c) {
  if (c.route_live)   return "#2ea04340";
  if (c.configured)   return "#d2992240";
  return "var(--border)";
}
function rowDot(c) {
  if (c.route_live) return "var(--primary)";
  if (c.configured) return "var(--warning)";
  return "var(--muted)";
}
function rowTitle(c) {
  if (c.route_live) return "Route active in Traefik";
  if (c.configured) return "Labels applied but not yet verified";
  return "No Traefik labels applied";
}
function routeStatLabel(c) {
  if (c.route_live) return "✓ live";
  if (c.configured) return "⚠ pending";
  return "○ not set";
}
function routeStatBg(c) {
  if (c.route_live) return "#2ea04320";
  if (c.configured) return "#d2992220";
  return "#7d859020";
}
function routeStatColor(c) {
  if (c.route_live) return "var(--primary)";
  if (c.configured) return "var(--warning)";
  return "var(--muted)";
}
function labelChecks(c) {
  return [
    { label: "traefik.enable", ok: c.has_enable },
    { label: "router rule",    ok: c.has_rule },
    { label: "TLS",            ok: c.has_tls },
    { label: "port",           ok: c.has_port },
  ];
}

function toggleExpand(id) {
  const s = new Set(expanded.value);
  s.has(id) ? s.delete(id) : s.add(id);
  expanded.value = s;
}

async function copyText(text) {
  try { await navigator.clipboard.writeText(text); } catch { }
  copied.value = true;
  setTimeout(() => { copied.value = false; }, 2000);
}
async function copyFor(id, text) {
  try { await navigator.clipboard.writeText(text); } catch { }
  copiedId.value = id;
  setTimeout(() => { copiedId.value = null; }, 2000);
}

async function saveCfg() {
  saving.value = true;
  try {
    await API.post("/traefik/config", cfg.value);
    dirty.value = false;
    saveMsg.value = "Saved";
    setTimeout(() => { saveMsg.value = ""; }, 2500);
    await loadStatus();
  } catch (e) {
    saveMsg.value = `Error: ${e.message}`;
  } finally {
    saving.value = false;
  }
}

async function loadStatus() {
  statusLoading.value = true;
  try {
    status.value = await API.get("/traefik/status");
  } catch { } finally {
    statusLoading.value = false;
  }
}

async function loadCompose() {
  composeLoading.value = true;
  try {
    const res = await API.get("/traefik/compose");
    composeYaml.value = res.yaml;
  } catch { } finally {
    composeLoading.value = false;
  }
}

onMounted(async () => {
  try {
    const c = await API.get("/traefik/config");
    cfg.value = { ...cfg.value, ...c };
  } catch { }
  await loadStatus();
});
</script>
