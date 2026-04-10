<template>
  <div class="page">
    <div class="page-header flex items-center gap-3">
      <div class="page-title">Stack health</div>
      <div style="flex:1" />
      <button class="btn btn-sm" :disabled="loading" @click="load">
        <span v-if="loading" class="spinner" style="width:12px;height:12px" />
        <span v-else>↺</span> Refresh
      </button>
    </div>

    <div v-if="loading && !report" class="flex items-center gap-2 text-muted mt-3">
      <span class="spinner" /> Analysing stack…
    </div>

    <div v-else-if="error" class="alert alert-error mb-3">{{ error }}</div>

    <template v-else-if="report">
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:16px">
        <div class="stat-box">
          <div class="stat-box-label">Critical issues</div>
          <div class="stat-box-value" :style="report.summary.critical?'color:var(--danger)':'color:var(--text)'">
            {{ report.summary.critical }}
          </div>
        </div>
        <div class="stat-box">
          <div class="stat-box-label">Warnings</div>
          <div class="stat-box-value" :style="report.summary.warnings?'color:var(--warning)':'color:var(--text)'">
            {{ report.summary.warnings }}
          </div>
        </div>
        <div class="stat-box">
          <div class="stat-box-label">Checks passed</div>
          <div class="stat-box-value" style="color:var(--primary)">{{ report.summary.ok }}</div>
        </div>
      </div>

      <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap">
        <button v-for="f in FILTERS" :key="f.val"
          :class="['btn btn-sm', filter===f.val?'btn-primary':'']"
          @click="filter=f.val">{{ f.label }}</button>
      </div>

      <div style="display:grid;gap:8px">
        <div v-for="(r,i) in filtered" :key="i"
          :style="`background:var(--surface);border:1px solid ${severityBorder(r.severity)};border-radius:8px;padding:12px 14px`">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
            <span :style="`font-size:10px;font-weight:700;text-transform:uppercase;padding:2px 7px;border-radius:20px;background:${severityBg(r.severity)};color:${severityColor(r.severity)}`">
              {{ r.severity }}
            </span>
            <span style="font-size:12px;font-family:var(--mono);font-weight:600;color:var(--text)">{{ r.service }}</span>
            <span v-if="r.target" style="color:var(--muted);font-size:12px">→ {{ r.target }}</span>
            <span style="margin-left:auto;font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.06em">{{ r.type }}</span>
          </div>
          <div style="font-size:12px;color:var(--muted);margin-bottom:6px">{{ r.message }}</div>
          <div v-if="r.fix" style="font-size:11px;color:var(--info,#388bfd);background:#388bfd12;border:1px solid #388bfd30;border-radius:4px;padding:6px 10px;font-family:var(--mono)">
            Fix: {{ r.fix }}
          </div>
        </div>

        <div v-if="!filtered.length" class="alert alert-info" style="text-align:center">
          No {{ filter === 'all' ? '' : filter + ' ' }}issues found.
        </div>
      </div>

      <div v-if="report.key_hints && Object.keys(report.key_hints).length" style="margin-top:20px">
        <div class="section-title">Where to find API keys</div>
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px;margin-top:8px">
          <div v-for="(hint,app) in report.key_hints" :key="app"
            style="background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:10px 12px">
            <div style="font-family:var(--mono);font-size:12px;font-weight:600;margin-bottom:4px;text-transform:capitalize">{{ app }}</div>
            <div style="font-size:11px;color:var(--muted)">{{ hint }}</div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";
import { API } from "@/composables/useApi.js";

const report  = ref(null);
const loading = ref(true);
const error   = ref(null);
const filter  = ref("all");

const FILTERS = [
  { val: "all",      label: "All" },
  { val: "critical", label: "Critical" },
  { val: "warning",  label: "Warnings" },
  { val: "ok",       label: "Passed" },
];

const filtered = computed(() => {
  if (!report.value) return [];
  const r = report.value.results;
  return filter.value === "all" ? r : r.filter(x => x.severity === filter.value);
});

function severityBorder(s) {
  return { critical: "#da363360", warning: "#d2992260", ok: "#2ea04340", info: "#388bfd40" }[s] || "var(--border)";
}
function severityBg(s) {
  return { critical: "#da363320", warning: "#d2992220", ok: "#2ea04320", info: "#388bfd20" }[s] || "var(--surface2)";
}
function severityColor(s) {
  return { critical: "#ff8080", warning: "#d29922", ok: "#2ea043", info: "#388bfd" }[s] || "var(--muted)";
}

async function load() {
  loading.value = true;
  error.value = null;
  try {
    report.value = await API.stack.health();
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>
