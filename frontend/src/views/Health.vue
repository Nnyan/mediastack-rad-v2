<template>
  <div>
    <h1 class="page-title">
      System Health
      <span class="sub">
        {{ report?.summary?.error || 0 }} errors ·
        {{ report?.summary?.warning || 0 }} warnings ·
        {{ report?.summary?.info || 0 }} info
      </span>
    </h1>

    <div class="flex items-center gap-3 mb-3">
      <button @click="refresh(true)" :disabled="refreshing">
        {{ refreshing ? 'Checking…' : 'Re-run checks' }}
      </button>
      <span class="small muted" v-if="report">
        Last check: {{ formatTime(report.checked_at) }}
        · {{ report.duration_ms }}ms
      </span>
      <span class="ml-auto">
        <span v-if="report?.ok" class="status-pill ok">
          <span class="dot ok"></span> all clear
        </span>
        <span v-else class="status-pill err">
          <span class="dot err"></span> needs attention
        </span>
      </span>
    </div>

    <div v-if="!report" class="card muted">Loading…</div>

    <div v-else>
      <!-- Group by category for at-a-glance scanning -->
      <div v-for="(issues, cat) in grouped" :key="cat" class="card">
        <h3 class="section-title">{{ cat }}</h3>
        <div v-for="issue in issues" :key="issue.id" class="issue">
          <div class="issue-head">
            <span class="dot" :class="sevClass(issue.severity)"></span>
            <strong>{{ issue.title }}</strong>
            <span class="issue-sev">{{ issue.severity }}</span>
            <button
              v-if="issue.auto_fix_available"
              class="ml-auto"
              @click="fix(issue.id)"
              :disabled="fixing === issue.id"
            >
              {{ fixing === issue.id ? 'fixing…' : 'auto-fix' }}
            </button>
          </div>
          <div class="issue-detail">{{ issue.detail }}</div>
          <div class="issue-fix mono small muted" v-if="issue.fix_hint">
            → {{ issue.fix_hint }}
          </div>
        </div>
      </div>

      <div v-if="report.issues.length === 0" class="card flex items-center gap-3">
        <span class="dot ok" style="width: 12px; height: 12px"></span>
        <span>No issues detected. Every check passed.</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, inject } from 'vue'

const showToast = inject('showToast')

const report = ref(null)
const refreshing = ref(false)
const fixing = ref(null)

let pollTimer = null

const grouped = computed(() => {
  if (!report.value) return {}
  const out = {}
  for (const i of report.value.issues) {
    (out[i.category] ||= []).push(i)
  }
  // Errors first within each group
  const rank = { error: 0, warning: 1, info: 2 }
  for (const k in out) {
    out[k].sort((a, b) => rank[a.severity] - rank[b.severity])
  }
  return out
})

function sevClass(s) {
  if (s === 'error') return 'err'
  if (s === 'warning') return 'warn'
  return 'off'
}

function formatTime(unix) {
  return new Date(unix * 1000).toLocaleTimeString()
}

async function refresh(force = false) {
  if (force) refreshing.value = true
  try {
    const r = await fetch(`/api/health${force ? '?refresh=true' : ''}`)
    report.value = await r.json()
  } finally {
    refreshing.value = false
  }
}

async function fix(issueId) {
  fixing.value = issueId
  try {
    const r = await fetch(
      `/api/health/fix/${encodeURIComponent(issueId)}`,
      { method: 'POST' }
    )
    const data = await r.json()
    showToast(data.message, data.ok ? 'ok' : 'err')
    if (data.ok) await refresh(true)
  } finally {
    fixing.value = null
  }
}

onMounted(() => {
  refresh()
  pollTimer = setInterval(() => refresh(false), 20000)
})
onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.section-title {
  margin: 0 0 var(--space-3);
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--fg-2);
  font-weight: 600;
}

.issue {
  padding: var(--space-3) 0;
  border-top: 1px solid var(--border);
}
.issue:first-child { border-top: none; padding-top: 0; }
.issue-head {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.issue-sev {
  font-family: var(--font-mono);
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 3px;
  background: var(--bg-2);
  color: var(--fg-2);
  text-transform: uppercase;
}
.issue-detail {
  margin: 6px 0 4px 18px;
  color: var(--fg-1);
  font-size: 13px;
}
.issue-fix { margin-left: 18px; }

.status-pill {
  font-size: 12px;
  font-family: var(--font-mono);
  padding: 4px 10px;
  border-radius: 12px;
  background: var(--bg-2);
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.status-pill.ok { background: var(--ok-bg); color: var(--ok); font-weight: 600; }
.status-pill.err { background: var(--err-bg); color: var(--err); font-weight: 600; }
</style>
