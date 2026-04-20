<template>
  <div class="container-card" @click="$emit('select')">
    <div class="container-card-header">
      <div class="container-card-name">{{ container.name }}</div>
      <StatusBadge :status="container.status" />

      <!-- Open Web UI button — only shown when a web UI port is known -->
      <a
        v-if="webUiUrl"
        :href="webUiUrl"
        target="_blank"
        rel="noopener noreferrer"
        class="btn btn-sm"
        style="padding:2px 7px;font-size:10px;text-decoration:none;color:var(--info,#388bfd);border-color:var(--info,#388bfd)40"
        title="Open web UI in new tab"
        @click.stop
      >↗ UI</a>

      <!-- Category menu -->
      <div style="position:relative" @click.stop>
        <button class="btn btn-sm" style="padding:2px 6px;font-size:10px" @click="showMenu=!showMenu" title="Change category">⋮</button>
        <div v-if="showMenu" style="position:absolute;right:0;top:100%;z-index:50;background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:4px 0;min-width:140px;margin-top:2px">
          <div style="font-size:10px;color:var(--muted);padding:4px 10px;text-transform:uppercase;letter-spacing:0.06em">Move to category</div>
          <button
            v-for="cat in categories" :key="cat"
            style="display:block;width:100%;text-align:left;padding:5px 10px;font-size:11px;background:transparent;border:none;color:var(--text);cursor:pointer"
            @mouseover="e=>e.target.style.background='var(--surface2)'"
            @mouseout="e=>e.target.style.background='transparent'"
            @click="choose(cat)"
          >{{ cat }}</button>
        </div>
      </div>
    </div>

    <div class="container-card-image">{{ container.image }}</div>

    <template v-if="container.status === 'running' && stats">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:6px">
        <div>
          <div class="stat-mini">CPU <span>{{ stats.cpu_percent }}%</span></div>
          <div class="progress-wrap mt-1"><div class="progress-bar progress-cpu" :style="`width:${Math.min(stats.cpu_percent,100)}%`" /></div>
        </div>
        <div>
          <div class="stat-mini">MEM <span>{{ stats.memory_mb }} MB</span></div>
          <div class="progress-wrap mt-1"><div class="progress-bar progress-mem" :style="`width:${memPct}%`" /></div>
        </div>
      </div>
    </template>

    <div class="container-card-footer">
      <span v-for="(hosts,cp) in Object.fromEntries(Object.entries(container.ports).slice(0,3))" :key="cp" class="port-pill">:{{ hosts[0] }}</span>
      <span class="card-id" style="margin-left:auto;color:var(--muted);font-size:10px;font-family:var(--mono)">{{ container.id }}</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from "vue";
import StatusBadge from "./StatusBadge.vue";

const props = defineProps({
  container: Object,
  stats: Object,
  categories: Array,
});
const emit = defineEmits(["select", "recategorize"]);

const showMenu = ref(false);

const memPct = computed(() => {
  if (!props.stats?.memory_limit_mb) return 0;
  return Math.min((props.stats.memory_mb / props.stats.memory_limit_mb) * 100, 100).toFixed(1);
});

function choose(cat) {
  showMenu.value = false;
  emit("recategorize", cat);
}

// ── Web UI URL resolution ──────────────────────────────────────────────────────
// Known apps where we must use a specific host port (not just the lowest)
const KNOWN_PORTS = {
  traefik: 8081,
  portainer: 9000,
};

// Known apps that need a specific path prefix to land on the right page
const KNOWN_PATHS = {
  plex:         "/web",
  sonarr:       "/",
  radarr:       "/",
  lidarr:       "/",
  readarr:      "/",
  prowlarr:     "/",
  bazarr:       "/",
  overseerr:    "/",
  jellyfin:     "/web",
  qbittorrent:  "/",
  sabnzbd:      "/sabnzbd",
  nzbget:       "/",
  autobrr:      "/",
  traefik:      "/dashboard/",
  portainer:    "/",
  heimdall:     "/",
  jellyseerr:   "/",
  overseerr:    "/",
  tautulli:     "/",
  requestrr:    "/",
  flaresolverr: "/",
  unpackerr:    "/",
};

// Ports that are NOT web UIs and should be skipped
const NON_WEB_PORTS = new Set([
  22,    // SSH
  53,    // DNS
  80,    // handled below
  443,   // HTTPS — usually not a local UI
  1194,  // OpenVPN
  1900,  // SSDP/UPnP
  3478,  // STUN
  4444,  // various
  5353,  // mDNS
  6881,  // BitTorrent
  6882,  // BitTorrent
  7359,  // Jellyfin discovery
  8443,  // HTTPS alt
  9091,  // Transmission — actually is a UI, added to known below
  32410, // Plex GDM
  32412, // Plex GDM
  32413, // Plex GDM
  32414, // Plex GDM
  32469, // Plex DLNA
  51413, // BitTorrent
]);

const webUiUrl = computed(() => {
  const ports = props.container.ports;
  if (!ports || !Object.keys(ports).length) return null;

  const host = window.location.hostname;
  const name  = props.container.name.toLowerCase().replace(/[-_]/g, "");
  const image = (props.container.image || "").toLowerCase();

  // Find the app name match in KNOWN_PATHS
  const knownKey = Object.keys(KNOWN_PATHS).find(k =>
    name.includes(k) || image.includes(k)
  );
  const path = knownKey ? KNOWN_PATHS[knownKey] : "/";

  // If we know the exact UI port for this app, use it directly
  const preferredPort = knownKey ? KNOWN_PORTS[knownKey] : null;

  // Pick the best port:
  // Prefer known UI ports, skip non-web ports, take the lowest numbered web port
  const candidatePorts = Object.entries(ports)
    .flatMap(([containerPort, hostBindings]) => {
      if (!hostBindings?.length) return [];
      const cp = parseInt(containerPort.split("/")[0]);
      const hp = parseInt(hostBindings[0]);
      if (NON_WEB_PORTS.has(hp)) return [];
      if (NON_WEB_PORTS.has(cp)) return [];
      return [{ hp, cp }];
    })
    .sort((a, b) => a.hp - b.hp);

  if (!candidatePorts.length) return null;

  // Use the preferred port if it's actually published, otherwise fall back to lowest
  const preferredEntry = preferredPort
    ? candidatePorts.find(p => p.hp === preferredPort)
    : null;

  const { hp } = preferredEntry || candidatePorts[0];
  const scheme = hp === 443 ? "https" : "http";
  return `${scheme}://${host}:${hp}${path}`;
});
</script>
