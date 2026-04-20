<template>
  <div class="page">
    <div class="page-header flex items-center gap-3">
      <div class="page-title">Containers</div>
      <div class="topbar-spacer" />
      <button class="btn btn-sm" @click="showImport=true">+ Add app</button>
      <button class="btn btn-sm" :disabled="loading" @click="refresh">
        <span v-if="loading" class="spinner" style="width:12px;height:12px" />
        <span v-else>↺</span> Refresh
      </button>
    </div>

    <div v-if="error" class="alert alert-error mb-3">{{ error }}</div>

    <div class="toolbar">
      <input v-model="search" class="search-input" placeholder="Search containers…" type="search" />
      <select v-model="filterStatus" class="filter-select">
        <option value="">All status</option>
        <option value="running">Running</option>
        <option value="exited">Stopped</option>
        <option value="paused">Paused</option>
      </select>
      <label style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--muted);cursor:pointer">
        <input type="checkbox" :checked="categoriesEnabled" @change="toggleCategories" style="cursor:pointer" />
        Group by category
      </label>
      <div class="count">{{ filtered.length }} / {{ containers.length }} containers</div>
    </div>

    <!-- Bulk action bar -->
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;flex-wrap:wrap">
      <label style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--muted);cursor:pointer">
        <input type="checkbox" :checked="allSelected" @change="toggleSelectAll" style="cursor:pointer" />
        <span>{{ selected.size ? `${selected.size} selected` : 'Select all' }}</span>
      </label>

      <template v-if="selected.size">
        <div style="width:1px;height:16px;background:var(--border)" />
        <button class="btn btn-sm" :disabled="bulkBusy" @click="doBulk('restart')">
          <span v-if="bulkAction==='restart'" class="spinner" style="width:11px;height:11px" />
          ↺ Restart
        </button>
        <button class="btn btn-sm" :disabled="bulkBusy" @click="doBulk('stop')">
          <span v-if="bulkAction==='stop'" class="spinner" style="width:11px;height:11px" />
          ■ Stop
        </button>
        <button class="btn btn-sm" :disabled="bulkBusy" @click="doBulk('start')">
          <span v-if="bulkAction==='start'" class="spinner" style="width:11px;height:11px" />
          ▶ Start
        </button>
        <button class="btn btn-primary btn-sm" :disabled="bulkBusy" @click="confirmUpdate=true">
          <span v-if="bulkAction==='update'" class="spinner" style="width:11px;height:11px" />
          ↑ Pull &amp; update
        </button>
        <button class="btn btn-sm" style="color:var(--muted)" @click="selected.clear();selected=new Set()">✕ Clear</button>
      </template>

      <template v-else>
        <div style="width:1px;height:16px;background:var(--border)" />
        <button class="btn btn-sm" :disabled="bulkBusy" @click="selectAllAndDo('restart')">↺ Restart all</button>
        <button class="btn btn-primary btn-sm" :disabled="bulkBusy" @click="confirmUpdateAll=true">↑ Update entire stack</button>
      </template>

      <span v-if="bulkMsg" :style="`font-size:11px;color:${bulkOk?'var(--primary)':'var(--danger)'}`">{{ bulkMsg }}</span>
    </div>

    <!-- Confirm update dialogs -->
    <div v-if="confirmUpdate||confirmUpdateAll"
      style="margin-bottom:12px;padding:10px 14px;background:#d2992218;border:1px solid #d2992240;border-radius:6px;font-size:11px;line-height:1.6">
      <strong style="color:var(--warning)">
        ⚠ {{ confirmUpdateAll ? 'Pull latest images for all containers and run docker compose up -d.' : `Pull latest images for ${selected.size} selected container(s) and recreate them.` }}
      </strong>
      Running containers will be briefly restarted.
      <div style="display:flex;gap:8px;margin-top:8px">
        <button class="btn btn-danger btn-sm" @click="confirmUpdate?doBulk('update'):doUpdateAll()">Confirm</button>
        <button class="btn btn-sm" @click="confirmUpdate=false;confirmUpdateAll=false">Cancel</button>
      </div>
    </div>

    <!-- Bulk output -->
    <div v-if="bulkOutput" style="margin-bottom:12px;border:1px solid var(--border);border-radius:8px;overflow:hidden">
      <div style="padding:7px 12px;background:var(--surface2);display:flex;align-items:center;gap:8px;border-bottom:1px solid var(--border)">
        <span style="font-size:11px;font-family:var(--mono);font-weight:600;flex:1">
          {{ bulkOutput.ok }}/{{ bulkOutput.total }} succeeded
        </span>
        <button class="btn btn-sm" style="font-size:10px;padding:2px 8px" @click="bulkOutput=null">✕</button>
      </div>
      <div style="padding:10px 12px;display:grid;gap:4px;max-height:200px;overflow-y:auto">
        <div v-for="r in bulkOutput.results" :key="r.name"
          style="display:flex;align-items:center;gap:8px;font-size:11px;font-family:var(--mono)">
          <span :style="`color:${r.ok?'var(--primary)':'var(--danger)'}`">{{ r.ok?'✓':'✗' }}</span>
          <span>{{ r.name }}</span>
          <span style="color:var(--muted)">{{ r.action }}</span>
          <span v-if="r.error" style="color:var(--danger)">— {{ r.error }}</span>
        </div>
        <div v-if="bulkOutput.compose_up" style="margin-top:6px;padding-top:6px;border-top:1px solid var(--border)">
          <div style="font-size:10px;color:var(--muted);margin-bottom:3px">$ {{ bulkOutput.compose_up.command }}</div>
          <div :style="`font-size:10px;color:${bulkOutput.compose_up.success?'var(--primary)':'var(--danger)'}`">
            {{ bulkOutput.compose_up.success ? '✓ docker compose up completed' : '✗ ' + bulkOutput.compose_up.stderr }}
          </div>
        </div>
      </div>
    </div>

    <div v-if="loading && !containers.length" class="flex items-center gap-2 text-muted mt-3">
      <span class="spinner" /> Loading containers…
    </div>
    <div v-else-if="!containers.length && !loading" class="alert alert-info">
      No containers found.
    </div>

    <template v-else-if="categoriesEnabled">
      <div v-for="cat in presentCategories" :key="cat">
        <div class="cat-header">
          {{ CAT_LABELS[cat] || cat }}
          <span style="font-size:10px;font-weight:400;color:var(--muted)">({{ byCategory[cat].length }})</span>
        </div>
        <div class="grid grid-3">
          <ContainerCard
            v-for="c in byCategory[cat]" :key="c.id"
            :container="c"
            :stats="liveStats[c.id]"
            :categories="CAT_OPTIONS"
            :selected="selected.has(c.id)"
            @select="openDetail(c.id)"
            @toggle-select="toggleSelect(c.id)"
            @recategorize="(cat) => setCategory(c.name, cat)"
          />
        </div>
      </div>
    </template>

    <div v-else class="grid grid-3">
      <ContainerCard
        v-for="c in filtered" :key="c.id"
        :container="c"
        :stats="liveStats[c.id]"
        :categories="CAT_OPTIONS"
        :selected="selected.has(c.id)"
        @select="openDetail(c.id)"
        @toggle-select="toggleSelect(c.id)"
        @recategorize="(cat) => setCategory(c.name, cat)"
      />
    </div>

    <ComposeImport :open="showImport" @close="showImport=false" />
  </div>
</template>

<script setup>
import { ref, computed } from "vue";
import { useRouter } from "vue-router";
import { useContainers } from "@/composables/useContainers.js";
import { useCategories } from "@/composables/useCategories.js";
import { API } from "@/composables/useApi.js";
import ContainerCard from "./ContainerCard.vue";
import ComposeImport from "./ComposeImport.vue";

const router = useRouter();
const { containers, liveStats, loading, error, refresh } = useContainers();
const { assignments, enabled: categoriesEnabled, setCategory, getCategory, toggleEnabled: toggleCategories } = useCategories();

const search        = ref("");
const filterStatus  = ref("");
const showImport    = ref(false);
const selected      = ref(new Set());
const bulkBusy      = ref(false);
const bulkAction    = ref("");
const bulkMsg       = ref("");
const bulkOk        = ref(true);
const bulkOutput    = ref(null);
const confirmUpdate    = ref(false);
const confirmUpdateAll = ref(false);

const CAT_LABELS = {
  infrastructure: "Infrastructure",
  media:          "Media servers",
  management:     "Media management",
  download:       "Download clients",
  other:          "Other",
};
const CAT_OPTIONS = Object.keys(CAT_LABELS);

function guessCategory(name, image) {
  const text = (name + " " + image).toLowerCase();
  if (/plex|emby|jellyfin|kodi/.test(text))                          return "media";
  if (/torrent|nzb|sab|usenet|download|qbit|deluge/.test(text))     return "download";
  if (/traefik|nginx|caddy|cloudflare|wireguard|pihole/.test(text)) return "infrastructure";
  if (/sonarr|radarr|lidarr|prowlarr|bazarr|overseerr|autobrr|unpackerr/.test(text)) return "management";
  return "other";
}

const filtered = computed(() => {
  let list = containers.value.slice();
  if (filterStatus.value) list = list.filter(c => c.status === filterStatus.value);
  if (search.value.trim()) {
    const q = search.value.toLowerCase();
    list = list.filter(c => c.name.toLowerCase().includes(q) || c.image.toLowerCase().includes(q) || c.id.includes(q));
  }
  return list.sort((a, b) => {
    const aRunning = a.status === "running" ? 0 : 1;
    const bRunning = b.status === "running" ? 0 : 1;
    if (aRunning !== bRunning) return aRunning - bRunning;
    return a.name.localeCompare(b.name);
  });
});

const byCategory = computed(() => {
  const groups = {};
  for (const c of filtered.value) {
    const cat = getCategory(c.name, guessCategory(c.name, c.image));
    if (!groups[cat]) groups[cat] = [];
    groups[cat].push(c);
  }
  for (const cat of Object.keys(groups)) {
    groups[cat].sort((a, b) => {
      const aRunning = a.status === "running" ? 0 : 1;
      const bRunning = b.status === "running" ? 0 : 1;
      if (aRunning !== bRunning) return aRunning - bRunning;
      return a.name.localeCompare(b.name);
    });
  }
  return groups;
});

const presentCategories = computed(() =>
  CAT_OPTIONS.filter(cat => byCategory.value[cat]?.length)
    .concat(Object.keys(byCategory.value).filter(k => !CAT_OPTIONS.includes(k)))
);

const allSelected = computed(() =>
  filtered.value.length > 0 && filtered.value.every(c => selected.value.has(c.id))
);

function toggleSelect(id) {
  const s = new Set(selected.value);
  s.has(id) ? s.delete(id) : s.add(id);
  selected.value = s;
}

function toggleSelectAll() {
  if (allSelected.value) {
    selected.value = new Set();
  } else {
    selected.value = new Set(filtered.value.map(c => c.id));
  }
}

function openDetail(id) {
  router.push(`/container/${id}`);
}

async function doBulk(action) {
  confirmUpdate.value = false;
  bulkBusy.value  = true;
  bulkAction.value = action;
  bulkMsg.value    = "";
  bulkOutput.value = null;
  try {
    const ids = [...selected.value];
    const r = await API.containers.bulk(action, ids);
    bulkOutput.value = r;
    bulkOk.value  = r.ok === r.total;
    bulkMsg.value = `${r.ok}/${r.total} ${action}ed`;
    await refresh();
  } catch (e) {
    bulkMsg.value = e.message;
    bulkOk.value  = false;
  } finally {
    bulkBusy.value   = false;
    bulkAction.value = "";
  }
}

async function doUpdateAll() {
  confirmUpdateAll.value = false;
  bulkBusy.value   = true;
  bulkAction.value = "update";
  bulkMsg.value    = "";
  bulkOutput.value = null;
  try {
    const r = await API.containers.bulk("update", []);
    bulkOutput.value = r;
    bulkOk.value  = r.ok === r.total;
    bulkMsg.value = `${r.ok}/${r.total} updated`;
    await refresh();
  } catch (e) {
    bulkMsg.value = e.message;
    bulkOk.value  = false;
  } finally {
    bulkBusy.value   = false;
    bulkAction.value = "";
  }
}

function selectAllAndDo(action) {
  selected.value = new Set(filtered.value.map(c => c.id));
  doBulk(action);
}
</script>
