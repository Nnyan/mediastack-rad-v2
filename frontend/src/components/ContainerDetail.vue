<template>
  <div class="page">
    <router-link to="/" class="back-link">← All containers</router-link>

    <div v-if="loading" class="flex items-center gap-2 text-muted">
      <span class="spinner" /> Loading…
    </div>

    <div v-else-if="error" class="alert alert-error">{{ error }}</div>

    <template v-else-if="container">
      <!-- Header -->
      <div class="page-header">
        <div class="flex items-center gap-3">
          <div class="page-title mono">{{ container.name }}</div>
          <StatusBadge :status="container.status" />
        </div>
        <div class="text-muted text-sm mt-1 mono">{{ container.image }}</div>
      </div>

      <!-- Action buttons -->
      <div class="flex gap-2 mb-3" style="flex-wrap:wrap;">
        <button
          v-if="container.status !== 'running'"
          class="btn btn-primary btn-sm"
          :disabled="acting"
          @click="act('start')"
        >▶ Start</button>
        <button
          v-if="container.status === 'running'"
          class="btn btn-danger btn-sm"
          :disabled="acting"
          @click="act('stop')"
        >■ Stop</button>
        <button
          class="btn btn-sm"
          :disabled="acting"
          @click="act('restart')"
        >↺ Restart</button>
        <span v-if="acting" class="spinner" style="align-self:center;" />
        <div v-if="actionMsg" class="text-muted text-sm" style="align-self:center;">{{ actionMsg }}</div>
      </div>

      <!-- Live stats (running only) -->
      <template v-if="container.status === 'running'">
        <div class="section-title">Live Stats</div>
        <div class="stats-bar mb-3">
          <div class="stat-box">
            <div class="stat-box-label">CPU</div>
            <div class="stat-box-value" :style="cpuColor">{{ stats.cpu_percent ?? "—" }}%</div>
            <div class="progress-wrap mt-1" v-if="stats.cpu_percent !== undefined">
              <div class="progress-bar progress-cpu" :style="`width:${Math.min(stats.cpu_percent,100)}%`" />
            </div>
          </div>
          <div class="stat-box">
            <div class="stat-box-label">Memory</div>
            <div class="stat-box-value">{{ stats.memory_mb ?? "—" }} <small style="font-size:0.7rem;color:var(--muted)">MB</small></div>
            <div class="progress-wrap mt-1" v-if="stats.memory_limit_mb">
              <div class="progress-bar progress-mem" :style="`width:${memPct}%`" />
            </div>
          </div>
          <div class="stat-box">
            <div class="stat-box-label">Mem Limit</div>
            <div class="stat-box-value">{{ stats.memory_limit_mb ?? "—" }} <small style="font-size:0.7rem;color:var(--muted)">MB</small></div>
          </div>
          <div class="stat-box">
            <div class="stat-box-label">Mem Used</div>
            <div class="stat-box-value">{{ memPct }}<small style="font-size:0.7rem;color:var(--muted)">%</small></div>
          </div>
        </div>
      </template>

      <!-- Info grid -->
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.75rem;margin-bottom:1rem;">
        <!-- Ports -->
        <div class="card">
          <div class="section-title">Ports</div>
          <div v-if="Object.keys(container.ports).length" class="flex gap-2" style="flex-wrap:wrap;">
            <span v-for="(hosts, cp) in container.ports" :key="cp" class="port-pill">
              {{ hosts.join(", ") }} → {{ cp }}
            </span>
          </div>
          <div v-else class="text-muted text-sm">No published ports</div>
        </div>

        <!-- Networks -->
        <div class="card">
          <div class="section-title">Networks</div>
          <div class="flex gap-2" style="flex-wrap:wrap;">
            <span v-for="n in container.networks" :key="n" class="port-pill" style="color:var(--primary);">{{ n }}</span>
          </div>
        </div>

        <!-- Restart policy -->
        <div class="card">
          <div class="section-title">Restart Policy</div>
          <code>{{ container.restart_policy || "no" }}</code>
        </div>

        <!-- Container ID -->
        <div class="card">
          <div class="section-title">Container ID</div>
          <code>{{ container.id }}</code>
        </div>
      </div>

      <!-- Labels -->
      <div v-if="Object.keys(container.labels || {}).length" class="card mb-3">
        <div class="section-title">Labels</div>
        <div style="display:grid;gap:0.25rem;">
          <div
            v-for="(v, k) in container.labels"
            :key="k"
            class="text-sm mono"
            style="display:flex;gap:0.5rem;overflow:hidden;"
          >
            <span class="text-muted" style="min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{{ k }}</span>
            <span style="color:var(--info);min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{{ v }}</span>
          </div>
        </div>
      </div>

      <!-- Logs -->
      <div class="section-title flex items-center gap-2">
        Logs
        <button class="btn btn-sm" @click="fetchLogs" :disabled="logsLoading">
          <span v-if="logsLoading" class="spinner" style="width:10px;height:10px;" />
          <span v-else>↺</span>
          Refresh
        </button>
        <select class="filter-select" v-model="logTail" @change="fetchLogs" style="padding:0.2rem 0.5rem;">
          <option :value="50">50 lines</option>
          <option :value="100">100 lines</option>
          <option :value="200">200 lines</option>
          <option :value="500">500 lines</option>
        </select>
      </div>
      <div class="log-viewer" ref="logEl">
        <div v-if="logsLoading" class="text-muted">Loading logs…</div>
        <div v-else-if="!logs.length" class="text-muted">No log output</div>
        <div v-for="(line, i) in logs" :key="i">{{ line }}</div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from "vue";
import { useRoute } from "vue-router";
import { API, connectStatsWs } from "@/composables/useApi.js";
import StatusBadge from "./StatusBadge.vue";

const route = useRoute();
const id    = route.params.id;

const container   = ref(null);
const stats       = ref({});
const logs        = ref([]);
const loading     = ref(true);
const error       = ref(null);
const acting      = ref(false);
const actionMsg   = ref("");
const logsLoading = ref(false);
const logTail     = ref(100);
const logEl       = ref(null);

let wsCleanup   = null;
let pollTimer   = null;

async function fetchContainer() {
  try {
    container.value = await API.containers.get(id);
    error.value = null;
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

async function fetchLogs() {
  logsLoading.value = true;
  try {
    const res = await API.containers.logs(id, logTail.value);
    logs.value = res.lines;
    await nextTick();
    if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight;
  } catch {
    logs.value = ["(failed to load logs)"];
  } finally {
    logsLoading.value = false;
  }
}

async function act(action) {
  acting.value = true;
  actionMsg.value = "";
  try {
    await API.containers[action](id);
    actionMsg.value = `${action} successful`;
    await fetchContainer();
    if (action !== "stop") await fetchLogs();
  } catch (e) {
    actionMsg.value = `Error: ${e.message}`;
  } finally {
    acting.value = false;
    setTimeout(() => { actionMsg.value = ""; }, 3000);
  }
}

const cpuColor = computed(() => {
  const pct = stats.value.cpu_percent ?? 0;
  if (pct > 80) return "color:var(--danger)";
  if (pct > 50) return "color:var(--warning)";
  return "color:var(--text)";
});

const memPct = computed(() => {
  const { memory_mb, memory_limit_mb } = stats.value;
  if (!memory_limit_mb) return 0;
  return Math.min((memory_mb / memory_limit_mb) * 100, 100).toFixed(1);
});

onMounted(async () => {
  await fetchContainer();
  await fetchLogs();
  pollTimer = setInterval(fetchContainer, 5000);

  // Subscribe to live stats stream and pluck our container's data
  wsCleanup = connectStatsWs((data) => {
    if (data[id]) stats.value = data[id];
  });
});

onUnmounted(() => {
  clearInterval(pollTimer);
  wsCleanup?.();
});
</script>
