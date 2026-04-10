<template>
  <div class="page">
    <router-link to="/" class="back-link">← All containers</router-link>

    <div v-if="loading" class="flex items-center gap-2 text-muted"><span class="spinner" /> Loading…</div>
    <div v-else-if="error" class="alert alert-error">{{ error }}</div>

    <template v-else-if="container">
      <div class="page-header">
        <div class="flex items-center gap-3">
          <div class="page-title mono">{{ container.name }}</div>
          <StatusBadge :status="container.status" />
        </div>
        <div class="text-muted text-sm mt-1 mono">{{ container.image }}</div>
      </div>

      <div class="flex gap-2 mb-3" style="flex-wrap:wrap">
        <button v-if="container.status!=='running'" class="btn btn-primary btn-sm" :disabled="acting" @click="act('start')">▶ Start</button>
        <button v-if="container.status==='running'"  class="btn btn-danger btn-sm"  :disabled="acting" @click="act('stop')">■ Stop</button>
        <button class="btn btn-sm" :disabled="acting" @click="act('restart')">↺ Restart</button>
        <span v-if="acting" class="spinner" style="align-self:center" />
        <span v-if="actionMsg" class="text-muted text-sm" style="align-self:center">{{ actionMsg }}</span>
      </div>

      <template v-if="container.status==='running'">
        <div class="section-title">Live stats</div>
        <div class="stats-bar mb-3">
          <div class="stat-box">
            <div class="stat-box-label">CPU</div>
            <div class="stat-box-value" :style="cpuColor">{{ stats.cpu_percent ?? '—' }}%</div>
            <div class="progress-wrap mt-1" v-if="stats.cpu_percent!=null"><div class="progress-bar progress-cpu" :style="`width:${Math.min(stats.cpu_percent,100)}%`" /></div>
          </div>
          <div class="stat-box">
            <div class="stat-box-label">Memory</div>
            <div class="stat-box-value">{{ stats.memory_mb ?? '—' }} <small style="font-size:0.7rem;color:var(--muted)">MB</small></div>
            <div class="progress-wrap mt-1" v-if="stats.memory_limit_mb"><div class="progress-bar progress-mem" :style="`width:${memPct}%`" /></div>
          </div>
          <div class="stat-box"><div class="stat-box-label">Limit</div><div class="stat-box-value">{{ stats.memory_limit_mb ?? '—' }} <small style="font-size:0.7rem;color:var(--muted)">MB</small></div></div>
          <div class="stat-box"><div class="stat-box-label">Mem %</div><div class="stat-box-value">{{ memPct }}<small style="font-size:0.7rem;color:var(--muted)">%</small></div></div>
        </div>
      </template>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:12px">
        <div class="card">
          <div class="section-title">Ports</div>
          <div v-if="Object.keys(container.ports).length" class="flex gap-2" style="flex-wrap:wrap">
            <span v-for="(hosts,cp) in container.ports" :key="cp" class="port-pill">{{ hosts.join(',') }} → {{ cp }}</span>
          </div>
          <div v-else class="text-muted text-sm">No published ports</div>
        </div>
        <div class="card">
          <div class="section-title">Networks</div>
          <div class="flex gap-2" style="flex-wrap:wrap">
            <span v-for="n in container.networks" :key="n" class="port-pill" style="color:var(--primary)">{{ n }}</span>
          </div>
        </div>
        <div class="card"><div class="section-title">Restart policy</div><code>{{ container.restart_policy||'no' }}</code></div>
        <div class="card"><div class="section-title">Container ID</div><code>{{ container.id }}</code></div>
      </div>

      <div v-if="Object.keys(container.labels||{}).length" class="card mb-3">
        <div class="section-title">Labels</div>
        <div style="display:grid;gap:3px">
          <div v-for="(v,k) in container.labels" :key="k" style="display:flex;gap:8px;overflow:hidden">
            <span class="text-muted mono" style="min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:11px">{{ k }}</span>
            <span style="color:var(--info,#388bfd);font-family:var(--mono);font-size:11px;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ v }}</span>
          </div>
        </div>
      </div>

      <div style="border:1px solid var(--border);border-radius:8px;overflow:hidden;margin-bottom:12px">
        <div style="display:flex;border-bottom:1px solid var(--border);background:var(--surface)">
          <button v-for="t in TABS" :key="t"
            :style="`padding:8px 14px;font-size:12px;background:${activeTab===t?'var(--surface2)':'transparent'};border:none;color:${activeTab===t?'var(--text)':'var(--muted)'};cursor:pointer;border-right:1px solid var(--border);font-weight:${activeTab===t?500:400}`"
            @click="switchTab(t)">{{ t }}</button>
        </div>
        <div style="padding:12px 14px;background:var(--surface2)">
          <div v-if="activeTab==='Logs'">
            <div class="flex gap-2 mb-2">
              <select class="filter-select" v-model="logTail" @change="fetchLogs">
                <option :value="50">50 lines</option>
                <option :value="100">100 lines</option>
                <option :value="200">200 lines</option>
                <option :value="500">500 lines</option>
              </select>
              <button class="btn btn-sm" @click="fetchLogs" :disabled="logsLoading">
                <span v-if="logsLoading" class="spinner" style="width:10px;height:10px" /> ↺ Refresh
              </button>
            </div>
            <div class="log-viewer" ref="logEl">
              <div v-if="logsLoading" class="text-muted">Loading…</div>
              <div v-else-if="!logs.length" class="text-muted">No log output</div>
              <div v-for="(line,i) in logs" :key="i">{{ line }}</div>
            </div>
          </div>

          <div v-if="activeTab==='Troubleshoot'">
            <div class="flex gap-2 mb-3">
              <button class="btn btn-primary btn-sm" @click="troubleshootRef?.run()">Run diagnostics</button>
              <span style="font-size:11px;color:var(--muted);align-self:center">Analyses logs, volumes, exit codes, and known error patterns</span>
            </div>
            <Troubleshoot ref="troubleshootRef" :container-id="id" />
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from "vue";
import { useRoute } from "vue-router";
import { API, connectStatsWs } from "@/composables/useApi.js";
import StatusBadge from "./StatusBadge.vue";
import Troubleshoot from "./Troubleshoot.vue";

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
const activeTab   = ref("Logs");
const troubleshootRef = ref(null);
const TABS = ["Logs", "Troubleshoot"];

let wsCleanup = null;
let pollTimer = null;

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
  } catch { logs.value = ["(failed to load logs)"]; }
  finally { logsLoading.value = false; }
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

function switchTab(t) {
  activeTab.value = t;
}

const cpuColor = computed(() => {
  const p = stats.value.cpu_percent ?? 0;
  if (p > 80) return "color:var(--danger)";
  if (p > 50) return "color:var(--warning)";
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
  wsCleanup = connectStatsWs((data) => { if (data[id]) stats.value = data[id]; });
});
onUnmounted(() => { clearInterval(pollTimer); wsCleanup?.(); });
</script>
