<template>
  <div class="page">

    <!-- Header -->
    <div class="page-header flex items-center gap-3">
      <div class="page-title">Traefik &amp; HTTPS</div>
      <div style="flex:1" />
      <button class="btn btn-sm" :disabled="statusLoading" @click="loadAll">
        <span v-if="statusLoading" class="spinner" style="width:12px;height:12px" />
        <span v-else>↺</span> Refresh
      </button>
    </div>

    <!-- Status row -->
    <div style="display:flex;gap:10px;align-items:center;margin-bottom:18px;flex-wrap:wrap">
      <div :style="`display:inline-flex;align-items:center;gap:6px;padding:5px 12px;border-radius:20px;font-size:11px;font-weight:600;border:1px solid ${tColor}40;background:${tColor}15;color:${tColor}`">
        <span style="width:7px;height:7px;border-radius:50%;background:currentColor;display:inline-block" />
        {{ tLabel }}
      </div>
      <span v-if="traefik?.version" style="font-size:11px;color:var(--muted)">v{{ traefik.version }}</span>
      <span v-if="traefik?.total_routes!=null" style="font-size:11px;color:var(--muted)">{{ traefik.total_routes }} active routes</span>
      <div style="display:flex;gap:6px;margin-left:auto;flex-wrap:wrap">
        <span v-for="p in systemPills" :key="p.label"
          :style="`font-size:10px;font-weight:600;padding:3px 9px;border-radius:20px;background:${p.ok?'#2ea04318':'#da363318'};color:${p.ok?'#2ea043':'#ff8080'};border:1px solid ${p.ok?'#2ea04340':'#da363340'}`">
          {{ p.ok ? '✓' : '✗' }} {{ p.label }}
        </span>
      </div>
    </div>

    <!-- System issues -->
    <div v-if="sys && !sys.ready" style="margin-bottom:16px">
      <div v-for="(issue,i) in sys.issues" :key="i"
        style="padding:10px 14px;background:#da363312;border:1px solid #da363340;border-radius:6px;font-size:12px;color:#ff8080;margin-bottom:6px;line-height:1.6">
        <strong>Setup required:</strong> {{ issue }}
      </div>
    </div>

    <div style="display:grid;grid-template-columns:320px 1fr;gap:16px;align-items:start">

      <!-- ─── LEFT ─── -->
      <div style="display:grid;gap:12px">

        <!-- Domain & cert -->
        <div class="card">
          <div class="section-title" style="margin-bottom:12px">Domain &amp; certificate</div>

          <label style="display:block;margin-bottom:10px">
            <div style="font-size:11px;color:var(--muted);margin-bottom:4px">Base domain</div>
            <input v-model="cfg.domain" class="search-input" style="width:100%;max-width:none"
              placeholder="example.com" @input="dirty=true" />
            <div style="font-size:10px;color:var(--muted);margin-top:2px">Apps served as <code>app.example.com</code></div>
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

          <label v-if="cfg.cert_type==='http'" style="display:block;margin-bottom:10px">
            <div style="font-size:11px;color:var(--muted);margin-bottom:4px">Cert resolver name</div>
            <input v-model="cfg.certresolver" class="search-input" style="width:100%;max-width:none"
              placeholder="letsencrypt" @input="dirty=true" />
            <div style="font-size:10px;color:var(--muted);margin-top:2px">Matches your <code>certificatesResolvers</code> key in Traefik</div>
          </label>

          <label style="display:block;margin-bottom:10px">
            <div style="font-size:11px;color:var(--muted);margin-bottom:4px">HTTPS entrypoint</div>
            <input v-model="cfg.entrypoint_https" class="search-input" style="width:100%;max-width:none" placeholder="websecure" @input="dirty=true" />
          </label>

          <label style="display:block;margin-bottom:10px">
            <div style="font-size:11px;color:var(--muted);margin-bottom:4px">Traefik API URL</div>
            <input v-model="cfg.traefik_api_url" class="search-input" style="width:100%;max-width:none" placeholder="http://traefik:8080" @input="dirty=true" />
          </label>

          <label style="display:block;margin-bottom:14px">
            <div style="font-size:11px;color:var(--muted);margin-bottom:4px">Middleware <span style="font-weight:400">(optional)</span></div>
            <input v-model="cfg.middleware" class="search-input" style="width:100%;max-width:none" placeholder="authelia@docker" @input="dirty=true" />
            <div style="font-size:10px;color:var(--muted);margin-top:2px">Applied to all routers (SSO / auth)</div>
          </label>

          <div style="display:flex;gap:8px;align-items:center">
            <button class="btn btn-primary btn-sm" :disabled="!dirty||saving" @click="saveCfg">
              <span v-if="saving" class="spinner" style="width:11px;height:11px" /> Save config
            </button>
            <span v-if="saveMsg" style="font-size:11px;color:var(--primary)">{{ saveMsg }}</span>
          </div>
        </div>

        <!-- Compose file status -->
        <div class="card">
          <div class="section-title" style="margin-bottom:8px">Compose file</div>
          <div v-if="sys?.compose_found">
            <div style="font-size:11px;color:var(--primary);font-weight:600;margin-bottom:4px">✓ Found</div>
            <code style="display:block;font-size:10px;background:var(--bg);padding:5px 8px;border-radius:4px;border:1px solid var(--border);word-break:break-all">{{ sys.compose_path }}</code>
            <div style="font-size:10px;color:var(--muted);margin-top:6px">A <code>.bak</code> backup is created before every write.</div>
          </div>
          <div v-else style="font-size:11px;color:var(--muted);line-height:1.7">
            Not mounted. Add to <code>.env</code> and rebuild:
            <code style="display:block;margin:6px 0;background:var(--bg);padding:5px 8px;border-radius:4px;border:1px solid var(--border);font-size:10px">COMPOSE_DIR=/opt/mediastack</code>
            <code style="display:block;background:var(--bg);padding:5px 8px;border-radius:4px;border:1px solid var(--border);font-size:10px">docker compose up -d --build</code>
          </div>
        </div>

        <!-- Apply all -->
        <div class="card">
          <div class="section-title" style="margin-bottom:8px">Apply to all containers</div>
          <div style="font-size:11px;color:var(--muted);margin-bottom:10px;line-height:1.7">
            Patches labels into the compose file for every container, then runs <code>docker compose up -d</code>.
          </div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px">
            <button class="btn btn-sm" :disabled="!sys?.ready||applyingAll" @click="doApplyAll(true)">Preview all</button>
            <button class="btn btn-primary btn-sm" :disabled="!sys?.ready||applyingAll" @click="confirmApplyAll">
              <span v-if="applyingAll" class="spinner" style="width:11px;height:11px" />
              Apply all &amp; recreate
            </button>
          </div>
          <div v-if="showConfirmAll" style="padding:10px;background:#d2992218;border:1px solid #d2992240;border-radius:6px;font-size:11px;line-height:1.7">
            <strong style="color:var(--warning)">⚠ All running containers will be briefly restarted.</strong><br>
            Compose file will be backed up first.
            <div style="display:flex;gap:8px;margin-top:8px">
              <button class="btn btn-danger btn-sm" @click="doApplyAll(false)">Confirm</button>
              <button class="btn btn-sm" @click="showConfirmAll=false">Cancel</button>
            </div>
          </div>
        </div>

        <!-- Cert setup snippet -->
        <div class="card">
          <div class="section-title" style="margin-bottom:8px">{{ cfg.cert_type==='wildcard' ? 'DNS-01 setup' : 'HTTP-01 setup' }}</div>
          <div style="font-size:11px;color:var(--muted);margin-bottom:6px;line-height:1.6">
            <span v-if="cfg.cert_type==='wildcard'">DNS-01 challenge requires your DNS provider credentials.</span>
            <span v-else>Port <strong>80</strong> must be reachable from the internet.</span>
            Add to <code>traefik.yml</code>:
          </div>
          <pre style="background:var(--bg);border:1px solid var(--border);border-radius:4px;padding:8px;font-size:10px;font-family:var(--mono);overflow-x:auto;line-height:1.6;white-space:pre">{{ certSnippet }}</pre>
        </div>

        <!-- Export snippet -->
        <div class="card">
          <div class="section-title" style="margin-bottom:8px">Export YAML snippet</div>
          <div style="font-size:11px;color:var(--muted);margin-bottom:10px">Full labels block for manual editing.</div>
          <button class="btn btn-sm" :disabled="composeLoading" @click="loadCompose">
            <span v-if="composeLoading" class="spinner" style="width:11px;height:11px" /> Generate
          </button>
          <div v-if="composeYaml" style="margin-top:10px">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
              <span style="font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.06em">Snippet</span>
              <button class="btn btn-sm" style="font-size:10px;padding:2px 8px" @click="copyText(composeYaml,'all')">{{ copiedKey==='all'?'✓ Copied':'Copy' }}</button>
            </div>
            <pre style="background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:10px;font-size:10px;font-family:var(--mono);max-height:220px;overflow-y:auto;line-height:1.6;white-space:pre">{{ composeYaml }}</pre>
          </div>
        </div>
      </div>

      <!-- ─── RIGHT: container table ─── -->
      <div>
        <div style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.07em;color:var(--muted);margin-bottom:8px">
          Container routing
        </div>

        <!-- Global output terminal -->
        <div v-if="lastOutput" style="margin-bottom:12px;border:1px solid var(--border);border-radius:8px;overflow:hidden">
          <div style="padding:8px 12px;background:var(--surface2);display:flex;align-items:center;gap:8px;border-bottom:1px solid var(--border)">
            <span style="font-size:11px;font-family:var(--mono);font-weight:600;flex:1">Operation output</span>
            <span :style="`font-size:11px;font-weight:700;color:${lastOutput.success?'var(--primary)':'var(--danger)'}`">
              {{ lastOutput.success ? '✓ success' : '✗ failed' }}
            </span>
            <button class="btn btn-sm" style="font-size:10px;padding:2px 8px" @click="lastOutput=null">✕</button>
          </div>
          <div class="log-viewer" style="max-height:160px;border-radius:0">
            <div v-if="lastOutput.command" style="color:#58a6ff;margin-bottom:6px">$ {{ lastOutput.command }}</div>
            <div v-if="lastOutput.stdout" style="white-space:pre-wrap">{{ lastOutput.stdout }}</div>
            <div v-if="lastOutput.stderr" style="color:#ff8080;white-space:pre-wrap">{{ lastOutput.stderr }}</div>
            <div v-if="lastOutput.error"  style="color:#ff8080">Error: {{ lastOutput.error }}</div>
            <div v-if="!lastOutput.stdout&&!lastOutput.stderr&&!lastOutput.error" style="color:#6e7681">(no output)</div>
          </div>
          <div v-if="lastOutput.backup_path" style="padding:6px 12px;font-size:10px;color:var(--muted);background:var(--surface2);border-top:1px solid var(--border);display:flex;align-items:center;gap:10px">
            <span>Backup: <code>{{ lastOutput.backup_path }}</code></span>
            <button class="btn btn-sm" style="font-size:10px;padding:1px 8px" @click="doRestore(lastOutput.container_id)">Restore</button>
          </div>
        </div>

        <div v-if="!cfg.domain" class="alert alert-info" style="margin-bottom:0">
          Set a base domain to see routing status.
        </div>

        <div v-else style="display:grid;gap:8px">
          <div v-for="c in (status?.containers||[])" :key="c.id"
            :style="`background:var(--surface);border:1px solid ${rowBorder(c)};border-radius:8px;overflow:hidden`">

            <!-- Row header -->
            <div style="padding:10px 14px;display:flex;align-items:center;gap:8px;cursor:pointer" @click="toggleExpand(c.id)">
              <span :style="`width:9px;height:9px;border-radius:50%;flex-shrink:0;background:${rowDot(c)}`" />
              <span style="font-family:var(--mono);font-size:12px;font-weight:600;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ c.name }}</span>
              <span v-if="c.status!=='running'" class="badge badge-exited" style="font-size:9px">stopped</span>
              <a v-if="c.expected_url&&c.route_live" :href="c.expected_url" target="_blank"
                style="font-size:10px;color:var(--info,#388bfd);font-family:var(--mono)" @click.stop>
                {{ c.expected_url }} ↗
              </a>
              <span v-else-if="c.expected_url" style="font-size:10px;color:var(--muted);font-family:var(--mono)">{{ c.expected_url }}</span>
              <span :style="`font-size:10px;font-weight:600;padding:2px 8px;border-radius:20px;background:${statBg(c)};color:${statColor(c)}`">{{ statLabel(c) }}</span>
              <span style="color:var(--muted);font-size:11px">{{ expanded.has(c.id)?'▲':'▼' }}</span>
            </div>

            <!-- Expanded -->
            <div v-if="expanded.has(c.id)" style="border-top:1px solid var(--border);padding:12px 14px;background:var(--surface2)">

              <!-- Checklist -->
              <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:12px">
                <div v-for="ck in labelChecks(c)" :key="ck.label"
                  :style="`padding:6px 8px;border-radius:6px;border:1px solid ${ck.ok?'#2ea04340':'#da363340'};background:${ck.ok?'#2ea04312':'#da363312'};text-align:center`">
                  <div style="font-size:15px">{{ ck.ok?'✓':'✗' }}</div>
                  <div style="font-size:10px;font-weight:600;color:var(--text);margin-top:2px">{{ ck.label }}</div>
                </div>
              </div>

              <!-- Labels YAML -->
              <div style="margin-bottom:12px">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
                  <span style="font-size:10px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:0.06em">Labels</span>
                  <button class="btn btn-sm" style="font-size:10px;padding:2px 8px" @click="copyText(c.labels_yaml,c.id)">
                    {{ copiedKey===c.id?'✓ Copied':'Copy YAML' }}
                  </button>
                </div>
                <pre style="background:var(--bg);border:1px solid var(--border);border-radius:4px;padding:8px;font-size:10px;font-family:var(--mono);margin:0;line-height:1.6;white-space:pre">{{ c.labels_yaml }}</pre>
              </div>

              <!-- Apply section -->
              <div style="background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:12px;margin-bottom:10px">
                <div style="font-size:11px;font-weight:600;color:var(--text);margin-bottom:8px">Auto-apply to compose file</div>
                <div v-if="!sys?.ready" style="font-size:11px;color:var(--warning);margin-bottom:8px">
                  ⚠ Setup required — see issues above.
                </div>
                <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:8px">
                  <button class="btn btn-sm" :disabled="!sys?.ready||applying[c.id]" @click="doPreview(c)">Preview changes</button>
                  <button class="btn btn-primary btn-sm" :disabled="!sys?.ready||applying[c.id]" @click="doApply(c)">
                    <span v-if="applying[c.id]" class="spinner" style="width:11px;height:11px" />
                    Apply &amp; recreate
                  </button>
                </div>
                <div style="font-size:10px;color:var(--muted)">
                  Runs: <code style="font-size:10px">docker compose up -d --no-deps {{ c.name }}</code>
                </div>

                <!-- Preview output -->
                <div v-if="previews[c.id]" style="margin-top:10px;font-size:11px;line-height:1.7;padding:8px 10px;background:var(--surface2);border:1px solid var(--border);border-radius:4px">
                  <div v-if="previews[c.id].error" style="color:var(--danger)">{{ previews[c.id].error }}</div>
                  <template v-else>
                    <div v-if="!previews[c.id].will_modify" style="color:var(--primary)">✓ Already up to date — no changes needed.</div>
                    <template v-else>
                      <div v-if="Object.keys(previews[c.id].added||{}).length" style="color:var(--primary)">
                        <strong>Adding:</strong> {{ Object.keys(previews[c.id].added).join(', ') }}
                      </div>
                      <div v-if="Object.keys(previews[c.id].changed||{}).length" style="color:var(--warning)">
                        <strong>Updating:</strong> {{ Object.keys(previews[c.id].changed).join(', ') }}
                      </div>
                      <div v-if="Object.keys(previews[c.id].unchanged||{}).length" style="color:var(--muted)">
                        <strong>Already set:</strong> {{ Object.keys(previews[c.id].unchanged).join(', ') }}
                      </div>
                    </template>
                  </template>
                </div>
              </div>

              <!-- Route status -->
              <div v-if="c.route_live" style="font-size:11px;color:var(--primary)">
                ✓ Route confirmed in Traefik — status: <strong>{{ c.route_status }}</strong>
              </div>
              <div v-else-if="c.configured" style="font-size:11px;color:var(--warning)">
                ⚠ Labels applied but not yet registered in Traefik. Container may need a recreate.
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

const cfg     = ref({ domain:"", cert_type:"http", certresolver:"letsencrypt", entrypoint_https:"websecure", traefik_api_url:"http://traefik:8080", middleware:"" });
const status  = ref(null);
const sys     = ref(null);
const traefik = computed(() => status.value?.traefik);
const dirty   = ref(false);
const saving  = ref(false);
const saveMsg = ref("");
const statusLoading  = ref(false);
const composeYaml    = ref("");
const composeLoading = ref(false);
const expanded   = ref(new Set());
const copiedKey  = ref(null);
const applying   = ref({});
const applyingAll= ref(false);
const previews   = ref({});
const lastOutput = ref(null);
const showConfirmAll = ref(false);

const CERT_TYPES = [
  { val:"http",     label:"Per-app cert",  desc:"HTTP-01, one cert per subdomain" },
  { val:"wildcard", label:"Wildcard cert", desc:"DNS-01, *.domain.com shared cert" },
];

const certSnippet = computed(() => {
  const d = cfg.value.domain || "example.com";
  const r = cfg.value.certresolver || "letsencrypt";
  return cfg.value.cert_type === "wildcard"
    ? `certificatesResolvers:\n  ${r}:\n    acme:\n      email: you@${d}\n      storage: /letsencrypt/acme.json\n      dnsChallenge:\n        provider: cloudflare\n        resolvers: ["1.1.1.1:53"]`
    : `certificatesResolvers:\n  ${r}:\n    acme:\n      email: you@${d}\n      storage: /letsencrypt/acme.json\n      httpChallenge:\n        entryPoint: web`;
});

const systemPills = computed(() => [
  { label:"compose file", ok: sys.value?.compose_found },
  { label:"docker CLI",   ok: sys.value?.docker_available },
  { label:"socket write", ok: sys.value?.socket_writable },
]);

const tLabel = computed(() => {
  if (!traefik.value) return "Checking…";
  if (!traefik.value.running) return "Traefik not running";
  if (!traefik.value.api_reachable) return "Traefik running — API unreachable";
  return "Traefik running & connected";
});
const tColor = computed(() => {
  if (!traefik.value) return "var(--muted)";
  if (!traefik.value.running) return "var(--danger)";
  if (!traefik.value.api_reachable) return "var(--warning)";
  return "var(--primary)";
});

function rowBorder(c){ return c.route_live?"#2ea04340":c.configured?"#d2992240":"var(--border)"; }
function rowDot(c)   { return c.route_live?"var(--primary)":c.configured?"var(--warning)":"var(--muted)"; }
function statLabel(c){ return c.route_live?"✓ live":c.configured?"⚠ pending":"○ not set"; }
function statBg(c)   { return c.route_live?"#2ea04320":c.configured?"#d2992220":"#7d859020"; }
function statColor(c){ return c.route_live?"var(--primary)":c.configured?"var(--warning)":"var(--muted)"; }
function labelChecks(c){ return [
  {label:"traefik.enable",ok:c.has_enable},
  {label:"router rule",   ok:c.has_rule},
  {label:"TLS",           ok:c.has_tls},
  {label:"port",          ok:c.has_port},
]; }

function toggleExpand(id){
  const s = new Set(expanded.value);
  s.has(id) ? s.delete(id) : s.add(id);
  expanded.value = s;
}
async function copyText(text, key){
  try{ await navigator.clipboard.writeText(text); }catch{}
  copiedKey.value = key;
  setTimeout(()=>{ copiedKey.value = null; }, 2000);
}

async function loadAll(){
  statusLoading.value = true;
  await Promise.all([loadSys(), loadStatus()]);
  statusLoading.value = false;
}
async function loadSys(){ try{ sys.value = await API.get("/traefik/system"); }catch{} }
async function loadStatus(){ try{ status.value = await API.get("/traefik/status"); }catch{} }

async function saveCfg(){
  saving.value = true;
  try{
    await API.post("/traefik/config", cfg.value);
    dirty.value = false;
    saveMsg.value = "Saved ✓";
    setTimeout(()=>{ saveMsg.value=""; }, 2500);
    await loadAll();
  }catch(e){ saveMsg.value = `Error: ${e.message}`; }
  finally{ saving.value=false; }
}

async function loadCompose(){
  composeLoading.value = true;
  try{ const r = await API.get("/traefik/compose"); composeYaml.value = r.yaml; }
  catch{} finally{ composeLoading.value=false; }
}

async function doPreview(c){
  try{
    const r = await API.post(`/traefik/apply/${c.id}`, {dry_run:true});
    previews.value = {...previews.value, [c.id]: r};
  }catch(e){ previews.value = {...previews.value, [c.id]: {error:e.message}}; }
}

async function doApply(c){
  applying.value = {...applying.value, [c.id]: true};
  previews.value = {...previews.value, [c.id]: null};
  try{
    const r = await API.post(`/traefik/apply/${c.id}`, {dry_run:false});
    lastOutput.value = {...r, container_id: c.id};
    await loadStatus();
  }catch(e){ lastOutput.value = {success:false, error:e.message, container_id:c.id}; }
  finally{ applying.value = {...applying.value, [c.id]: false}; }
}

function confirmApplyAll(){ showConfirmAll.value = true; }

async function doApplyAll(dry_run){
  showConfirmAll.value = false;
  applyingAll.value = !dry_run;
  try{
    const r = await API.post("/traefik/apply-all", {dry_run});
    lastOutput.value = dry_run
      ? {success:true, command:"(preview — no changes made)", stdout:JSON.stringify(r,null,2), stderr:""}
      : r;
    if(!dry_run) await loadStatus();
  }catch(e){ lastOutput.value = {success:false, error:e.message}; }
  finally{ applyingAll.value=false; }
}

async function doRestore(containerId){
  try{
    await API.post(`/traefik/restore/${containerId||"backup"}`);
    lastOutput.value = {success:true, command:"Restore", stdout:"Backup restored. Run docker compose up to apply.", stderr:""};
  }catch(e){ lastOutput.value = {success:false, error:e.message}; }
}

onMounted(async ()=>{
  try{ const c = await API.get("/traefik/config"); cfg.value = {...cfg.value,...c}; }catch{}
  await loadAll();
});
</script>
