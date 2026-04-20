<template>
  <div class="page">

    <div class="page-header flex items-center gap-3">
      <div class="page-title">Stack builder</div>
      <div style="flex:1" />
      <span style="font-size:11px;color:var(--muted)">
        {{ selected.size }} service{{ selected.size !== 1 ? 's' : '' }} selected
      </span>
    </div>

    <div style="display:grid;grid-template-columns:1fr 300px;gap:16px;align-items:start">

      <!-- ── LEFT: service picker ── -->
      <div>
        <div v-for="cat in CATEGORY_ORDER" :key="cat">
          <div v-if="byCategory[cat]?.length" class="cat-header">
            {{ CAT_LABELS[cat] }}
            <span style="font-size:10px;font-weight:400">({{ byCategory[cat].length }})</span>
          </div>
          <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px;margin-bottom:4px">
            <div v-for="svc in byCategory[cat]" :key="svc.id"
              :style="`background:var(--surface);border:1px solid ${selected.has(svc.id)?'var(--primary)':'var(--border)'};border-radius:8px;padding:10px 12px;cursor:pointer;transition:border-color 0.15s`"
              @click="toggleService(svc.id)">
              <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
                <div :style="`width:14px;height:14px;border-radius:3px;border:2px solid ${selected.has(svc.id)?'var(--primary)':'var(--border)'};background:${selected.has(svc.id)?'var(--primary)':'transparent'};flex-shrink:0;display:flex;align-items:center;justify-content:center`">
                  <span v-if="selected.has(svc.id)" style="color:#fff;font-size:10px;line-height:1">✓</span>
                </div>
                <span style="font-family:var(--mono);font-size:12px;font-weight:600">{{ svc.id }}</span>
                <span v-if="isAutoAdded(svc.id)" style="font-size:9px;color:var(--muted);margin-left:auto">auto</span>
              </div>
              <div style="font-size:11px;color:var(--muted);line-height:1.4;padding-left:22px">{{ svc.description }}</div>
              <div v-if="svc.ports.length" style="padding-left:22px;margin-top:4px;display:flex;gap:4px;flex-wrap:wrap">
                <span v-for="p in svc.ports.slice(0,2)" :key="p" class="port-pill">:{{ p.split(':')[0] }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ── RIGHT: options + deploy panel ── -->
      <div style="position:sticky;top:70px;display:grid;gap:12px">

        <!-- Options -->
        <div class="card">
          <div class="section-title" style="margin-bottom:10px">Options</div>

          <label style="display:block;margin-bottom:8px">
            <div style="font-size:11px;color:var(--muted);margin-bottom:3px">Data directory</div>
            <input v-model="opts.base_data" class="search-input" style="width:100%;max-width:none;font-size:11px" placeholder="/opt/mediastack" />
          </label>
          <label style="display:block;margin-bottom:8px">
            <div style="font-size:11px;color:var(--muted);margin-bottom:3px">Media directory</div>
            <input v-model="opts.media_path" class="search-input" style="width:100%;max-width:none;font-size:11px" placeholder="/mnt/media" />
          </label>
          <label style="display:block;margin-bottom:8px">
            <div style="font-size:11px;color:var(--muted);margin-bottom:3px">Network name</div>
            <input v-model="opts.network" class="search-input" style="width:100%;max-width:none;font-size:11px" placeholder="mediastack" />
          </label>
          <label style="display:block;margin-bottom:8px">
            <div style="font-size:11px;color:var(--muted);margin-bottom:3px">Timezone</div>
            <input v-model="opts.timezone" class="search-input" style="width:100%;max-width:none;font-size:11px" placeholder="UTC" />
          </label>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px">
            <label style="display:block">
              <div style="font-size:11px;color:var(--muted);margin-bottom:3px">PUID</div>
              <input v-model="opts.puid" class="search-input" style="width:100%;max-width:none;font-size:11px" placeholder="1000" type="number" />
            </label>
            <label style="display:block">
              <div style="font-size:11px;color:var(--muted);margin-bottom:3px">PGID</div>
              <input v-model="opts.pgid" class="search-input" style="width:100%;max-width:none;font-size:11px" placeholder="1000" type="number" />
            </label>
          </div>

          <!-- External Plex -->
          <div style="border-top:1px solid var(--border);padding-top:10px;margin-top:2px">
            <label style="display:flex;align-items:center;gap:8px;cursor:pointer;margin-bottom:8px">
              <input type="checkbox" v-model="opts.use_external_plex" style="cursor:pointer" />
              <span style="font-size:11px;color:var(--text);font-weight:500">Use existing Plex server</span>
            </label>
            <template v-if="opts.use_external_plex">
              <div style="font-size:11px;color:var(--muted);margin-bottom:4px">Plex server URL</div>
              <input v-model="opts.external_plex_url" class="search-input" style="width:100%;max-width:none;font-size:11px"
                placeholder="http://10.0.1.60:32400 or http://plex:32400" />
              <div style="font-size:10px;color:var(--muted);margin-top:3px;line-height:1.5">
                Plex will not be added as a container. Overseerr will be configured to connect to this URL.
                Use the server's IP if Plex is on a different machine.
              </div>
            </template>
          </div>
        </div>

        <!-- Actions -->
        <div class="card">
          <div class="section-title" style="margin-bottom:10px">Deploy</div>

          <div style="font-size:11px;color:var(--muted);margin-bottom:10px;line-height:1.6">
            Generates a complete <code>docker-compose.yml</code> and saves it to
            <code>{{ composePath }}</code>, then runs <code>docker compose up -d</code>.
          </div>

          <div style="display:grid;gap:6px">
            <button class="btn btn-sm" :disabled="!selected.size || previewing" @click="doPreview">
              <span v-if="previewing" class="spinner" style="width:11px;height:11px" />
              Preview YAML
            </button>
            <button class="btn btn-primary btn-sm" :disabled="!selected.size || deploying || !sys?.compose_dir_ready || (portReport && portReport.critical > 0)" @click="confirmDeploy=true">
              <span v-if="deploying" class="spinner" style="width:11px;height:11px" />
              Save &amp; deploy stack
            </button>
            <div v-if="!sys?.compose_dir_ready" style="font-size:10px;color:var(--warning);margin-top:2px">
              ⚠ Compose directory not mounted — set COMPOSE_DIR in .env
            </div>
          </div>

          <!-- Confirm -->
          <div v-if="confirmDeploy" style="margin-top:10px;padding:10px;background:#d2992218;border:1px solid #d2992240;border-radius:6px;font-size:11px;line-height:1.6">
            <strong style="color:var(--warning)">⚠ This will write and start {{ resolvedServices.length }} containers.</strong>
            Any existing compose file at that path will be backed up to <code>.bak</code>.
            <div style="display:flex;gap:8px;margin-top:8px">
              <button class="btn btn-danger btn-sm" @click="doDeploy">Confirm &amp; deploy</button>
              <button class="btn btn-sm" @click="confirmDeploy=false">Cancel</button>
            </div>
          </div>
        </div>

        <!-- Selected list -->
        <div v-if="resolvedServices.length" class="card">
          <div class="section-title" style="margin-bottom:8px">Will deploy ({{ resolvedServices.length }})</div>
          <div v-if="opts.use_external_plex && opts.external_plex_url" style="font-size:10px;color:var(--info,#388bfd);margin-bottom:8px;padding:5px 8px;background:#388bfd12;border:1px solid #388bfd30;border-radius:4px">
            Plex: using external server at {{ opts.external_plex_url }}
          </div>
          <div style="display:grid;gap:3px">
            <div v-for="id in resolvedServices" :key="id"
              style="font-family:var(--mono);font-size:11px;display:flex;align-items:center;gap:6px">
              <span :style="`color:${isAutoAdded(id)?'var(--muted)':'var(--primary)'}`">{{ isAutoAdded(id) ? '↳' : '✓' }}</span>
              <span>{{ id }}</span>
              <span v-if="isAutoAdded(id)" style="font-size:9px;color:var(--muted)">(required dep)</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Port conflict report -->
    <div v-if="portReport && portReport.conflicts.length" style="margin-top:16px;border:1px solid var(--border);border-radius:8px;overflow:hidden">
      <div style="padding:8px 14px;background:var(--surface2);display:flex;align-items:center;gap:8px;border-bottom:1px solid var(--border)">
        <span style="font-size:12px;font-family:var(--mono);font-weight:600;flex:1">Port conflicts detected</span>
        <span v-if="portReport.critical" style="font-size:11px;font-weight:700;color:var(--danger)">
          {{ portReport.critical }} critical
        </span>
        <span v-if="portReport.warnings" style="font-size:11px;font-weight:700;color:var(--warning);margin-left:8px">
          {{ portReport.warnings }} warning{{ portReport.warnings !== 1 ? "s" : "" }}
        </span>
      </div>
      <div style="padding:12px 14px;display:grid;gap:8px">
        <div v-for="(c, i) in portReport.conflicts" :key="i"
          :style="`padding:10px 12px;border-radius:6px;border:1px solid ${c.severity==='critical'?'#da363340':'#d2992240'};background:${c.severity==='critical'?'#da363312':'#d2992212'}`">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
            <span :style="`font-size:10px;font-weight:700;text-transform:uppercase;padding:2px 7px;border-radius:20px;background:${c.severity==='critical'?'#da363325':'#d2992225'};color:${c.severity==='critical'?'#ff8080':'#d29922'}`">
              {{ c.severity }}
            </span>
            <span style="font-family:var(--mono);font-size:11px;font-weight:600">Port {{ c.port }}</span>
            <span v-for="svc in c.services" :key="svc" class="port-pill" style="font-size:10px">{{ svc }}</span>
            <span v-if="c.running_container" style="font-size:10px;color:var(--muted)">
              conflicts with running container: <strong>{{ c.running_container }}</strong>
            </span>
          </div>
          <div style="font-size:11px;color:var(--muted);margin-bottom:6px">{{ c.message }}</div>
          <div style="font-size:11px;color:var(--info,#388bfd);font-family:var(--mono);background:#388bfd12;padding:5px 8px;border-radius:4px">
            Fix: {{ c.fix }}
          </div>
        </div>
      </div>
    </div>

    <div v-else-if="portReport && portReport.ok && selected.size" style="margin-top:12px;display:flex;align-items:center;gap:6px;font-size:11px;color:var(--primary)">
      <span>✓</span> No port conflicts detected across {{ portReport.port_map ? Object.keys(portReport.port_map).length : 0 }} ports
    </div>

    <!-- Output terminal -->
    <div v-if="output" style="margin-top:16px;border:1px solid var(--border);border-radius:8px;overflow:hidden">
      <div style="padding:8px 14px;background:var(--surface2);display:flex;align-items:center;gap:8px;border-bottom:1px solid var(--border)">
        <span style="font-size:12px;font-family:var(--mono);font-weight:600;flex:1">Output</span>
        <span v-if="output.success!=null" :style="`font-size:11px;font-weight:700;color:${output.success?'var(--primary)':'var(--danger)'}`">
          {{ output.success ? '✓ success' : '✗ failed' }}
        </span>
        <button class="btn btn-sm" style="font-size:10px;padding:2px 8px" @click="output=null">✕</button>
      </div>
      <div class="log-viewer" style="max-height:200px;border-radius:0">
        <div v-if="output.command" style="color:#58a6ff;margin-bottom:6px">$ {{ output.command }}</div>
        <div v-if="output.stdout" style="white-space:pre-wrap">{{ output.stdout }}</div>
        <div v-if="output.stderr" style="color:#ff8080;white-space:pre-wrap">{{ output.stderr }}</div>
        <div v-if="output.error"  style="color:#ff8080">Error: {{ output.error }}</div>
      </div>
      <div v-if="output.saved_path" style="padding:6px 14px;font-size:10px;color:var(--muted);background:var(--surface2);border-top:1px solid var(--border)">
        Saved to: <code>{{ output.saved_path }}</code>
      </div>
    </div>

    <!-- YAML preview modal -->
    <div v-if="previewYaml" style="position:fixed;inset:0;background:rgba(0,0,0,0.6);display:flex;align-items:center;justify-content:center;z-index:200;padding:24px">
      <div style="background:var(--surface);border:1px solid var(--border);border-radius:10px;width:100%;max-width:800px;max-height:90vh;display:flex;flex-direction:column;overflow:hidden">
        <div style="padding:12px 16px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px">
          <span style="font-family:var(--mono);font-size:13px;font-weight:600;flex:1">docker-compose.yml preview</span>
          <button class="btn btn-sm" style="font-size:10px;padding:2px 10px" @click="copyYaml">{{ copied?'✓ Copied':'Copy' }}</button>
          <button class="btn btn-sm" @click="previewYaml=null">✕ Close</button>
        </div>
        <pre style="flex:1;overflow-y:auto;padding:14px 16px;font-size:10px;font-family:var(--mono);line-height:1.7;margin:0;background:var(--bg);white-space:pre">{{ previewYaml }}</pre>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from "vue";
import { API } from "@/composables/useApi.js";

const catalog  = ref({});
const selected = ref(loadSelected());
const OPTS_KEY     = "msr-builder-opts";
const SELECTED_KEY = "msr-builder-selected";

function loadOpts() {
  try {
    const saved = localStorage.getItem(OPTS_KEY);
    if (saved) return { base_data: "/opt/mediastack", media_path: "/mnt/media", network: "mediastack", timezone: "UTC", puid: 1000, pgid: 1000, external_plex_url: "", use_external_plex: false, ...JSON.parse(saved) };
  } catch {}
  return { base_data: "/opt/mediastack", media_path: "/mnt/media", network: "mediastack", timezone: "UTC", puid: 1000, pgid: 1000, external_plex_url: "", use_external_plex: false };
}

function loadSelected() {
  try {
    const saved = localStorage.getItem(SELECTED_KEY);
    if (saved) return new Set(JSON.parse(saved));
  } catch {}
  return new Set();
}

const opts     = ref(loadOpts());

const sys      = ref(null);
const previewing   = ref(false);
const deploying    = ref(false);
const confirmDeploy= ref(false);
const previewYaml  = ref(null);
const output       = ref(null);
const copied       = ref(false);

const CATEGORY_ORDER = ["infrastructure", "media", "management", "download"];
const CAT_LABELS = {
  infrastructure: "Infrastructure",
  media:          "Media servers",
  management:     "Media management",
  download:       "Download clients",
};

const composePath = computed(() =>
  import.meta.env?.VITE_COMPOSE_PATH || "/compose/docker-compose.yml"
);

const byCategory = computed(() => {
  const groups = {};
  for (const svc of Object.values(catalog.value)) {
    if (!groups[svc.category]) groups[svc.category] = [];
    groups[svc.category].push(svc);
  }
  return groups;
});

const resolvedServices = computed(() => {
  if (!selected.value.size) return [];
  const all = new Set(selected.value);
  for (const id of selected.value) {
    for (const dep of (catalog.value[id]?.depends_on || [])) {
      if (catalog.value[dep]) all.add(dep);
    }
  }
  return [...all];
});

function isAutoAdded(id) {
  return resolvedServices.value.includes(id) && !selected.value.has(id);
}

function toggleService(id) {
  const s = new Set(selected.value);
  s.has(id) ? s.delete(id) : s.add(id);
  selected.value = s;
}

async function doPreview() {
  previewing.value = true;
  try {
    const options = { ...opts.value, external_plex_url: opts.value.use_external_plex ? opts.value.external_plex_url : "" };
    const r = await API.post("/generator/preview", {
      selected: [...selected.value],
      options,
    });
    previewYaml.value = r.yaml;
  } catch (e) {
    output.value = { success: false, error: e.message };
  } finally {
    previewing.value = false;
  }
}

async function doDeploy() {
  confirmDeploy.value = false;
  deploying.value = true;
  try {
    const options = { ...opts.value, external_plex_url: opts.value.use_external_plex ? opts.value.external_plex_url : "" };
    const r = await API.post("/generator/deploy", {
      selected: [...selected.value],
      options,
      dry_run: false,
    });
    output.value = r;
  } catch (e) {
    output.value = { success: false, error: e.message };
  } finally {
    deploying.value = false;
  }
}

async function copyYaml() {
  try { await navigator.clipboard.writeText(previewYaml.value); } catch {}
  copied.value = true;
  setTimeout(() => { copied.value = false; }, 2000);
}

const portReport  = ref(null);
const portChecking = ref(false);

async function checkPorts() {
  if (!selected.value.size) { portReport.value = null; return; }
  portChecking.value = true;
  try {
    const r = await API.post("/ports/check", {
      selected: [...selected.value],
      extra_ports: {},
    });
    portReport.value = r;
  } catch { portReport.value = null; }
  finally { portChecking.value = false; }
}

watch(selected, checkPorts, { deep: true });
watch(selected, (s) => { try { localStorage.setItem(SELECTED_KEY, JSON.stringify([...s])); } catch {} }, { deep: true });
watch(opts, (o) => { try { localStorage.setItem(OPTS_KEY, JSON.stringify(o)); } catch {} }, { deep: true });

onMounted(async () => {
  try {
    const [cat, s] = await Promise.all([
      API.get("/generator/catalog"),
      API.get("/traefik/system"),
    ]);
    catalog.value = cat;
    sys.value = s;
  } catch (e) {
    console.error(e);
  }
});
</script>
