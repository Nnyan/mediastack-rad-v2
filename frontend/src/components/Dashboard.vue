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
      <div class="count" id="countEl">{{ filtered.length }} / {{ containers.length }} containers</div>
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
            @select="openDetail(c.id)"
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
        @select="openDetail(c.id)"
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
import ContainerCard from "./ContainerCard.vue";
import ComposeImport from "./ComposeImport.vue";

const router = useRouter();
const { containers, liveStats, loading, error, refresh } = useContainers();
const { assignments, enabled: categoriesEnabled, setCategory, getCategory, toggleEnabled: toggleCategories } = useCategories();

const search       = ref("");
const filterStatus = ref("");
const showImport   = ref(false);

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
  return list.sort((a, b) => (b.status === "running" ? 1 : 0) - (a.status === "running" ? 1 : 0));
});

const byCategory = computed(() => {
  const groups = {};
  for (const c of filtered.value) {
    const cat = getCategory(c.name, guessCategory(c.name, c.image));
    if (!groups[cat]) groups[cat] = [];
    groups[cat].push(c);
  }
  return groups;
});

const presentCategories = computed(() =>
  CAT_OPTIONS.filter(cat => byCategory.value[cat]?.length)
    .concat(Object.keys(byCategory.value).filter(k => !CAT_OPTIONS.includes(k)))
);

function openDetail(id) {
  router.push(`/container/${id}`);
}
</script>
