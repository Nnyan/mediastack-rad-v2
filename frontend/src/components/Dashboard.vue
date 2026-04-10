<template>
  <div class="page">
    <div class="page-header flex items-center gap-3">
      <div class="page-title">Containers</div>
      <div class="topbar-spacer" />
      <button class="btn btn-sm" :disabled="loading" @click="refresh">
        <span v-if="loading" class="spinner" style="width:12px;height:12px;" />
        <span v-else>↺</span>
        Refresh
      </button>
    </div>

    <div v-if="error" class="alert alert-error mb-3">{{ error }}</div>

    <div class="toolbar">
      <input
        v-model="search"
        class="search-input"
        placeholder="Search containers…"
        type="search"
      />
      <select v-model="filterStatus" class="filter-select">
        <option value="">All status</option>
        <option value="running">Running</option>
        <option value="exited">Stopped</option>
        <option value="paused">Paused</option>
      </select>
      <div class="text-muted text-sm" style="margin-left:auto;">
        {{ filtered.length }} / {{ containers.length }} containers
      </div>
    </div>

    <div v-if="loading && !containers.length" class="flex items-center gap-2 text-muted mt-3">
      <span class="spinner" /> Loading containers…
    </div>

    <div v-else-if="!containers.length && !loading" class="alert alert-info">
      No containers found. Start some Docker services to see them here.
    </div>

    <div v-else class="grid grid-3">
      <router-link
        v-for="c in filtered"
        :key="c.id"
        :to="`/container/${c.id}`"
        class="container-card"
      >
        <div class="container-card-header">
          <div class="container-card-name">{{ c.name }}</div>
          <StatusBadge :status="c.status" />
        </div>

        <div class="container-card-image">{{ c.image }}</div>

        <!-- Live stats for running containers -->
        <template v-if="c.status === 'running' && liveStats[c.id]">
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.5rem;margin-bottom:0.5rem;">
            <div>
              <div class="stat-mini">CPU <span>{{ liveStats[c.id].cpu_percent }}%</span></div>
              <div class="progress-wrap mt-1">
                <div class="progress-bar progress-cpu" :style="`width:${Math.min(liveStats[c.id].cpu_percent, 100)}%`" />
              </div>
            </div>
            <div>
              <div class="stat-mini">
                MEM <span>{{ liveStats[c.id].memory_mb }} MB</span>
              </div>
              <div class="progress-wrap mt-1">
                <div
                  class="progress-bar progress-mem"
                  :style="`width:${memPct(liveStats[c.id])}%`"
                />
              </div>
            </div>
          </div>
        </template>

        <div class="container-card-footer">
          <template v-if="Object.keys(c.ports).length">
            <span
              v-for="(hosts, cp) in c.ports"
              :key="cp"
              class="port-pill"
            >:{{ hosts[0] }}</span>
          </template>
          <span v-if="c.restart_policy && c.restart_policy !== 'no'" class="stat-mini">
            restart: <span>{{ c.restart_policy }}</span>
          </span>
          <span class="text-muted text-sm" style="margin-left:auto;font-size:0.7rem;">{{ c.id }}</span>
        </div>
      </router-link>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from "vue";
import { useContainers } from "@/composables/useContainers.js";
import StatusBadge from "./StatusBadge.vue";

const { containers, liveStats, loading, error, refresh } = useContainers();

const search       = ref("");
const filterStatus = ref("");

const filtered = computed(() => {
  let list = containers.value;
  if (filterStatus.value) list = list.filter(c => c.status === filterStatus.value);
  if (search.value.trim()) {
    const q = search.value.toLowerCase();
    list = list.filter(c =>
      c.name.toLowerCase().includes(q) ||
      c.image.toLowerCase().includes(q) ||
      c.id.includes(q)
    );
  }
  // Running first
  return [...list].sort((a, b) =>
    (b.status === "running" ? 1 : 0) - (a.status === "running" ? 1 : 0)
  );
});

function memPct(s) {
  if (!s.memory_limit_mb) return 0;
  return Math.min((s.memory_mb / s.memory_limit_mb) * 100, 100).toFixed(1);
}
</script>
