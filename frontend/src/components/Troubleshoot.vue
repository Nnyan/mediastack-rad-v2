<template>
  <div>
    <div v-if="loading" class="flex items-center gap-2 text-muted mt-2">
      <span class="spinner" /> Analysing container…
    </div>
    <div v-else-if="error" class="alert alert-error">{{ error }}</div>
    <template v-else-if="result">
      <div :style="`padding:10px 14px;border-radius:6px;border:1px solid ${result.healthy?'#2ea04340':'#da363360'};background:${result.healthy?'#2ea04312':'#da363312'};margin-bottom:12px;font-size:12px;color:${result.healthy?'#2ea043':'#ff8080'}`">
        {{ result.summary }}
      </div>
      <div v-if="!result.findings.length" style="font-size:12px;color:var(--muted);text-align:center;padding:20px 0">
        No issues automatically detected. Check the Logs tab for more detail.
      </div>
      <div v-for="(f,i) in result.findings" :key="i" style="margin-bottom:10px">
        <div :style="`background:var(--surface2);border:1px solid ${severityBorder(f.severity)};border-radius:6px;overflow:hidden`">
          <div :style="`padding:8px 12px;display:flex;align-items:center;gap:8px;border-bottom:1px solid var(--border);background:${severityBg(f.severity)}`">
            <span :style="`font-size:10px;font-weight:700;text-transform:uppercase;padding:2px 7px;border-radius:20px;background:${severityBg2(f.severity)};color:${severityColor(f.severity)}`">
              {{ f.severity }}
            </span>
            <span style="font-size:12px;font-weight:600;font-family:var(--mono)">{{ f.title }}</span>
          </div>
          <div style="padding:10px 12px">
            <div style="font-size:12px;color:var(--muted);margin-bottom:8px">{{ f.cause }}</div>
            <div style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;color:var(--muted);margin-bottom:6px">Remediation steps</div>
            <ol style="padding-left:16px;margin:0;display:grid;gap:4px">
              <li v-for="(step,si) in f.steps" :key="si" style="font-size:12px;color:var(--text);line-height:1.5">{{ step }}</li>
            </ol>
          </div>
        </div>
      </div>
    </template>
    <div v-if="!result && !loading && !error" style="font-size:12px;color:var(--muted);text-align:center;padding:20px 0">
      Click "Analyse" to run diagnostics.
    </div>
  </div>
</template>

<script setup>
import { ref } from "vue";
import { API } from "@/composables/useApi.js";

const props = defineProps({ containerId: String });

const result  = ref(null);
const loading = ref(false);
const error   = ref(null);

async function run() {
  loading.value = true;
  error.value = null;
  result.value = null;
  try {
    result.value = await API.containers.troubleshoot(props.containerId);
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

defineExpose({ run });

function severityBorder(s) {
  return { critical: "#da363360", high: "#d2992260", medium: "#388bfd40", info: "#388bfd30" }[s] || "var(--border)";
}
function severityBg(s) {
  return { critical: "#da363308", high: "#d2992208", medium: "#388bfd08", info: "#388bfd08" }[s] || "transparent";
}
function severityBg2(s) {
  return { critical: "#da363325", high: "#d2992225", medium: "#388bfd25", info: "#388bfd25" }[s] || "#7d859025";
}
function severityColor(s) {
  return { critical: "#ff8080", high: "#d29922", medium: "#388bfd", info: "#388bfd" }[s] || "var(--muted)";
}
</script>
