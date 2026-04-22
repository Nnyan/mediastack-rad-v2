<template>
  <div class="health">

    <!-- ── Summary bar ──────────────────────────────────────────────────── -->
    <div class="summary-bar">
      <span class="summary-counts">
        <span v-if="errors"   class="count count-err">✗ {{ errors }} error{{ errors   !== 1 ? 's' : '' }}</span>
        <span v-if="warnings" class="count count-warn">⚠ {{ warnings }} warning{{ warnings !== 1 ? 's' : '' }}</span>
        <span class="count count-ok">✓ {{ passing }} passing</span>
      </span>
      <span class="summary-sep" v-if="report"></span>
      <span class="summary-time" v-if="report">
        last run {{ formatTime(report.checked_at) }} · {{ report.duration_ms }}ms · {{ totalChecks }} checks
      </span>
      <button class="rerun-btn" @click="refresh(true)" :disabled="refreshing">
        <span v-if="refreshing" class="spinner"></span>
        {{ refreshing ? 'Checking…' : 'Re-run checks' }}
      </button>
    </div>

    <!-- ── Loading ──────────────────────────────────────────────────────── -->
    <div v-if="!report" class="loading-state">
      <span class="spinner"></span>
      Running checks…
    </div>

    <!-- ── Check groups ─────────────────────────────────────────────────── -->
    <div v-else class="check-groups" :class="{ 'groups-refreshing': refreshing }">
      <div
        v-for="group in groups"
        :key="group.category"
        class="check-group"
      >
        <!-- Group header -->
        <div class="group-head">
          <span class="group-label">{{ group.category }}</span>
          <span class="group-count">
            {{ group.checks.filter(c => c.status === 'ok').length }}/{{ group.checks.length }} passing
          </span>
        </div>

        <!-- Check rows -->
        <div class="check-rows">
          <div
            v-for="check in group.checks"
            :key="check.id"
            class="check-row"
            :class="{ expanded: openId === check.id, clickable: !!(check.detail || check.fix_hint) }"
            @click="toggle(check)"
          >
            <!-- Collapsed row — always one line -->
            <div class="row-line">
              <span class="dot" :class="`dot-${check.status}`"></span>
              <span class="row-label">{{ check.label }}</span>
              <span class="row-result" :class="`result-${check.status}`">
                <span v-if="check.status !== 'ok'" class="sev-pill" :class="`pill-${check.status}`">
                  {{ check.status }}
                </span>
                <span class="result-text">{{ check.summary }}</span>
              </span>
              <span class="row-ts">{{ formatTime(report.checked_at) }}</span>
              <button
                v-if="check.auto_fix_available && openId !== check.id"
                class="fix-chip"
                @click.stop="runFix(check)"
                :disabled="fixing === check.id"
              >{{ fixing === check.id ? 'fixing…' : 'auto-fix' }}</button>
              <span v-if="check.detail || check.fix_hint" class="row-chevron" :class="{ open: openId === check.id }">›</span>
            </div>

            <!-- Expanded detail -->
            <div v-if="openId === check.id && (check.detail || check.fix_hint)" class="row-detail">
              <p v-if="check.detail"   class="detail-text">{{ check.detail }}</p>
              <p v-if="check.fix_hint" class="detail-hint">→ {{ check.fix_hint }}</p>
              <button
                v-if="check.auto_fix_available"
                class="fix-btn"
                @click.stop="runFix(check)"
                :disabled="fixing === check.id"
              >{{ fixing === check.id ? 'Applying fix…' : 'Apply auto-fix' }}</button>
            </div>
          </div>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, inject } from 'vue'

const showToast = inject('showToast')

const report    = ref(null)
const refreshing = ref(false)
const fixing    = ref(null)
const openId    = ref(null)
let pollTimer   = null

// ── Computed ─────────────────────────────────────────────────────────────────
const checks = computed(() => report.value?.checks || [])

const groups = computed(() => {
  const order = ['Docker', 'Config', 'Traefik', 'Auth', 'Security', 'System', 'internal', 'network']
  const map = {}
  for (const c of checks.value) {
    const cat = c.category || 'System'
    if (!map[cat]) map[cat] = { category: cat, checks: [] }
    map[cat].checks.push(c)
  }
  return Object.values(map).sort((a, b) => {
    const ai = order.indexOf(a.category)
    const bi = order.indexOf(b.category)
    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi)
  })
})

const errors      = computed(() => checks.value.filter(c => c.status === 'error').length)
const warnings    = computed(() => checks.value.filter(c => c.status === 'warning').length)
const passing     = computed(() => checks.value.filter(c => c.status === 'ok').length)
const totalChecks = computed(() => checks.value.length)

// ── Helpers ───────────────────────────────────────────────────────────────────
function formatTime(unix) {
  if (!unix) return '—'
  return new Date(unix * 1000).toLocaleTimeString([], {
    hour: '2-digit', minute: '2-digit', second: '2-digit'
  })
}

function toggle(check) {
  if (!check.detail && !check.fix_hint) return
  openId.value = openId.value === check.id ? null : check.id
}

// ── API ───────────────────────────────────────────────────────────────────────
async function refresh(force = false) {
  if (force) refreshing.value = true
  try {
    // Run the fetch and a minimum 600ms delay concurrently so the spinner
    // is always visible long enough for the user to see it
    const [r] = await Promise.all([
      fetch(`/api/health${force ? '?refresh=true' : ''}`),
      force ? new Promise(res => setTimeout(res, 600)) : Promise.resolve(),
    ])
    const data = await r.json()
    report.value = data

    // Toast after manual re-run so it's clear something happened
    if (force) {
      const errs  = (data.checks || []).filter(c => c.status === 'error').length
      const warns = (data.checks || []).filter(c => c.status === 'warning').length
      if (errs === 0 && warns === 0) {
        showToast(`All ${(data.checks || []).length} checks passed`, 'ok')
      } else if (errs > 0) {
        showToast(`${errs} error${errs !== 1 ? 's' : ''}, ${warns} warning${warns !== 1 ? 's' : ''}`, 'err')
      } else {
        showToast(`${warns} warning${warns !== 1 ? 's' : ''} — check Health tab`, 'warn')
      }
    }
  } catch (e) {
    console.error('Health refresh failed:', e)
    if (force) showToast('Health check failed — backend unreachable', 'err')
  } finally {
    refreshing.value = false
  }
}

async function runFix(check) {
  fixing.value = check.id
  try {
    const r = await fetch(`/api/health/fix/${encodeURIComponent(check.id)}`, { method: 'POST' })
    const data = await r.json()
    showToast(data.message, data.ok ? 'ok' : 'err')
    if (data.ok) {
      openId.value = null
      await refresh(true)
    }
  } catch (e) {
    showToast(`Fix failed: ${e.message}`, 'err')
  } finally {
    fixing.value = null
  }
}

onMounted(() => {
  refresh()
  pollTimer = setInterval(() => refresh(false), 20000)
})
onUnmounted(() => { if (pollTimer) clearInterval(pollTimer) })
</script>

<style scoped>
.health { max-width: 860px; }

/* ── Summary bar ─────────────────────────────────────────────────────────── */
.summary-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 9px 14px;
  background: var(--bg-1);
  border: 1.5px solid var(--border);
  border-radius: var(--radius);
  margin-bottom: var(--space-4);
  flex-wrap: wrap;
}
.summary-counts { display: flex; align-items: center; gap: 10px; }
.count { font-size: 12px; font-weight: 600; }
.count-err  { color: var(--err); }
.count-warn { color: var(--warn); }
.count-ok   { color: var(--ok); }
.summary-sep {
  width: 1px; height: 14px;
  background: var(--border-strong);
  flex-shrink: 0;
}
.summary-time {
  font-size: 11.5px;
  color: var(--fg-2);
  font-family: var(--font-mono);
}
.rerun-btn {
  margin-left: auto;
  display: flex; align-items: center; gap: 6px;
  font-size: 12px; font-weight: 500; font-family: var(--font-sans);
  padding: 5px 12px; border-radius: 6px;
  border: 1.5px solid var(--border); background: var(--bg-1);
  color: var(--fg-1); cursor: pointer; transition: all 0.13s;
}
.rerun-btn:hover:not(:disabled) { border-color: var(--border-strong); background: var(--bg-2); }
.rerun-btn:disabled { opacity: 0.6; cursor: default; }

/* ── Loading ─────────────────────────────────────────────────────────────── */
.loading-state {
  display: flex; align-items: center; gap: 10px;
  color: var(--fg-2); padding: var(--space-5) 0;
  font-size: 13px;
}

/* ── Check groups ────────────────────────────────────────────────────────── */
.check-groups { display: flex; flex-direction: column; gap: 8px; }
.check-group {
  background: var(--bg-1);
  border: 1.5px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}
.group-head {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 14px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-0);
}
.group-label {
  font-size: 10.5px; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.07em;
  color: var(--fg-2);
}
.group-count {
  font-size: 10px; color: var(--fg-2);
  font-family: var(--font-mono);
}

/* ── Check rows ──────────────────────────────────────────────────────────── */
.check-rows { padding: 2px 14px 4px; }
.check-row { border-top: 1px solid var(--border); }
.check-row:first-child { border-top: none; }
.check-row.clickable .row-line { cursor: pointer; }
.check-row.clickable .row-line:hover { background: var(--bg-0); border-radius: 5px; }

.row-line {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 2px;
  min-width: 0;
}

/* Status dot */
.dot {
  width: 7px; height: 7px;
  border-radius: 50%; flex-shrink: 0;
}
.dot-ok   { background: var(--ok);   box-shadow: 0 0 4px rgba(22,163,74,0.5); }
.dot-warn { background: var(--warn); box-shadow: 0 0 4px rgba(217,119,6,0.5); }
.dot-error { background: var(--err); box-shadow: 0 0 4px rgba(220,38,38,0.5); }

/* Label — fixed width so result column aligns */
.row-label {
  font-size: 12.5px;
  font-weight: 500;
  color: var(--fg-0);
  flex: 0 0 175px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Result — fills remaining space, never wraps */
.row-result {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  overflow: hidden;
}
.result-text {
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.result-ok   .result-text { color: var(--fg-2); }
.result-warn .result-text { color: var(--warn); font-weight: 500; }
.result-error .result-text { color: var(--err); font-weight: 500; }

.sev-pill {
  font-size: 9.5px; font-weight: 700;
  padding: 1px 6px; border-radius: 20px;
  flex-shrink: 0;
}
.pill-warn  { background: var(--warn-bg); color: var(--warn); border: 1px solid rgba(217,119,6,0.2); }
.pill-error { background: var(--err-bg);  color: var(--err);  border: 1px solid rgba(220,38,38,0.2); }

/* Timestamp */
.row-ts {
  font-size: 10.5px;
  color: var(--fg-2);
  font-family: var(--font-mono);
  flex-shrink: 0;
}

/* Auto-fix chip — inline in collapsed row */
.fix-chip {
  font-size: 10.5px; font-weight: 600;
  padding: 2px 9px; border-radius: 20px; flex-shrink: 0;
  background: var(--accent-subtle); color: var(--accent);
  border: 1px solid var(--accent-dim);
  cursor: pointer; font-family: var(--font-sans);
  transition: all 0.13s;
}
.fix-chip:hover:not(:disabled) { background: var(--accent); color: #fff; }
.fix-chip:disabled { opacity: 0.5; cursor: default; }

/* Chevron */
.row-chevron {
  font-size: 14px; color: var(--fg-2); flex-shrink: 0;
  transition: transform 0.13s; display: inline-block;
}
.row-chevron.open { transform: rotate(90deg); }

/* ── Expanded detail ─────────────────────────────────────────────────────── */
.row-detail {
  margin: 0 0 8px 17px;
  padding: 8px 12px;
  border-radius: 7px;
  background: var(--bg-0);
  border: 1px solid var(--border);
}
.detail-text {
  font-size: 12px; color: var(--fg-1);
  margin: 0 0 5px; line-height: 1.5;
}
.detail-hint {
  font-size: 11.5px; color: var(--fg-2);
  font-style: italic; margin: 0 0 8px;
}
.detail-hint:last-child { margin-bottom: 0; }
.fix-btn {
  font-size: 12px; font-weight: 600;
  padding: 5px 14px; border-radius: 6px; border: none;
  background: var(--accent); color: #fff;
  cursor: pointer; font-family: var(--font-sans);
  transition: opacity 0.13s;
}
.fix-btn:disabled { opacity: 0.6; cursor: default; }

/* Refreshing overlay on check groups */
.groups-refreshing {
  opacity: 0.5;
  pointer-events: none;
  transition: opacity 0.15s;
}
.groups-refreshing .dot {
  background: var(--warn) !important;
  box-shadow: 0 0 4px rgba(217,119,6,0.5) !important;
  animation: pulse 1s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 0.5; }
  50%       { opacity: 1;   }
}

/* Spinner */
.spinner {
  display: inline-block;
  width: 11px; height: 11px;
  border: 1.5px solid var(--border-strong);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
