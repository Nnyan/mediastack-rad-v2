<template>
  <div class="settings">

    <!-- ── Secrets ─────────────────────────────────────────────────────── -->
    <div class="section-head">
      <div>
        <h2 class="section-title">Secrets</h2>
        <p class="section-sub">Stored in <code>.env</code> on the server. Edit any time — redeploy the stack to apply changes.</p>
      </div>
    </div>

    <div v-if="secretsLoading" class="loading-state">
      <span class="spinner"></span> Loading…
    </div>

    <div v-else-if="!secrets.length" class="empty-secrets">
      No secrets needed yet — deploy a stack with Cloudflare Tunnel, Tinyauth, or Tailscale to see credentials here.
    </div>

    <div v-else class="secrets-grid">
      <div
        v-for="group in secretGroups"
        :key="group.service"
        class="secret-group"
      >
        <div class="secret-group-head">
          <span class="secret-service-icon">{{ serviceIcon(group.service) }}</span>
          <span class="secret-service-name">{{ serviceLabel(group.service) }}</span>
        </div>

        <div class="secret-rows">
          <div
            v-for="s in group.entries"
            :key="s.key"
            class="secret-row"
          >
            <div class="secret-info">
              <div class="secret-label-row">
                <span class="secret-label">{{ s.label }}</span>
                <span class="secret-status" :class="s.is_set ? 'set' : 'unset'">
                  {{ s.is_set ? '● set' : '○ not set' }}
                </span>
              </div>
              <div class="secret-hint">{{ s.hint }}</div>
            </div>

            <div class="secret-input-row">
              <input
                v-model="edits[s.key]"
                :type="revealed[s.key] ? 'text' : 'password'"
                :placeholder="s.is_set ? '••••••••  (leave blank to keep current)' : 'Enter value…'"
                class="secret-input"
                autocomplete="off"
              />
              <button class="eye-btn" @click="revealed[s.key] = !revealed[s.key]" :title="revealed[s.key] ? 'Hide' : 'Show'">
                {{ revealed[s.key] ? '🙈' : '👁' }}
              </button>
              <a v-if="s.link" :href="s.link" target="_blank" class="secret-link">↗</a>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="secrets-actions" v-if="secrets.length">
      <button
        class="primary"
        :disabled="saving || !hasEdits"
        @click="saveSecrets"
      >{{ saving ? 'Saving…' : 'Save secrets' }}</button>
      <span v-if="saveMsg" class="save-msg" :class="saveOk ? 'ok' : 'err'">
        {{ saveMsg }}
      </span>
    </div>

    <!-- ── Health ───────────────────────────────────────────────────────── -->
    <div class="section-head health-head">
      <div>
        <h2 class="section-title">Health</h2>
      </div>
      <button class="outline" :disabled="healthRefreshing" @click="loadHealth(true)">
        {{ healthRefreshing ? 'Checking…' : 'Re-run checks' }}
      </button>
    </div>

    <div v-if="healthLoading" class="loading-state">
      <span class="spinner"></span> Checking system health…
    </div>

    <div v-else-if="healthError" class="error-state">
      <span class="error-icon">⚠</span>
      Unable to load health report.
    </div>

    <div v-else class="health-section">
      <div class="health-summary">
        <div class="health-counts">
          <span class="health-count err">✗ {{ errorCount }} error{{ errorCount !== 1 ? 's' : '' }}</span>
          <span class="health-count warn">⚠ {{ warningCount }} warning{{ warningCount !== 1 ? 's' : '' }}</span>
          <span class="health-count ok">✓ {{ okCount }} passing</span>
        </div>
        <div class="health-meta">
          <span>Last run {{ formatHealthTime(lastCheckedAt) }}</span>
          <span class="bullet">·</span>
          <span>{{ totalChecks }} checks</span>
          <span v-if="durationLabel" class="bullet">·</span>
          <span v-if="durationLabel">{{ durationLabel }}</span>
        </div>
      </div>

      <div class="health-groups">
        <div v-for="group in healthGroups" :key="group.category" class="health-card">
          <div class="health-card-head">
            <span class="health-card-title">{{ group.category }}</span>
            <span class="health-card-meta">{{ group.passing }}/{{ group.total }} passing</span>
          </div>
          <div class="health-card-body">
            <div
              v-for="check in group.checks"
              :key="check.id"
              class="health-row"
              :class="check.status"
            >
              <div class="health-row-main">
                <span class="dot" :class="`dot-${check.status}`"></span>
                <span class="health-row-label">{{ check.label }}</span>
                <span class="health-row-result">{{ check.summary }}</span>
              </div>
              <div v-if="check.detail" class="health-row-detail">{{ check.detail }}</div>
              <div v-if="check.fix_hint" class="health-row-hint">{{ check.fix_hint }}</div>
            </div>
            <div v-if="!group.checks.length" class="health-row muted">No checks yet.</div>
          </div>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, inject } from 'vue'

const showToast = inject('showToast')

// ── Secrets ───────────────────────────────────────────────────────────────────
const secrets        = ref([])
const secretsLoading = ref(true)
const edits          = reactive({})
const revealed       = reactive({})
const saving         = ref(false)
const saveMsg        = ref('')
const saveOk         = ref(true)

const SERVICE_ICONS  = { cloudflared: '☁️', tinyauth: '🔒', tailscale: '🔗', plex: '🎬' }
const SERVICE_LABELS = { cloudflared: 'Cloudflare Tunnel', tinyauth: 'Tinyauth', tailscale: 'Tailscale', plex: 'Plex' }
const serviceIcon  = k => SERVICE_ICONS[k]  || '🔑'
const serviceLabel = k => SERVICE_LABELS[k] || k

const secretGroups = computed(() => {
  const map = {}
  for (const s of secrets.value) {
    if (!map[s.service]) map[s.service] = { service: s.service, entries: [] }
    map[s.service].entries.push(s)
  }
  return Object.values(map)
})

const hasEdits = computed(() =>
  Object.values(edits).some(v => v && v.trim())
)

async function loadSecrets() {
  try {
    secrets.value = await fetch('/api/settings/secrets').then(r => r.json())
  } catch (e) {
    console.error('Secrets load failed:', e)
  } finally {
    secretsLoading.value = false
  }
}

async function saveSecrets() {
  const payload = {}
  for (const [k, v] of Object.entries(edits)) {
    if (v && v.trim()) payload[k] = v.trim()
  }
  if (!Object.keys(payload).length) return

  saving.value = true
  saveMsg.value = ''
  try {
    const r = await fetch('/api/settings/secrets', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const data = await r.json()
    if (r.ok) {
      saveOk.value = true
      saveMsg.value = `Saved: ${data.saved.join(', ')}`
      showToast(`${data.saved.length} secret(s) saved to .env`, 'ok')
      // Clear edits and refresh status
      for (const k of data.saved) { edits[k] = ''; revealed[k] = false }
      await loadSecrets()
    } else {
      saveOk.value = false
      saveMsg.value = data.detail || 'Save failed'
      showToast('Failed to save secrets', 'err')
    }
  } catch (e) {
    saveOk.value = false
    saveMsg.value = e.message
    showToast(`Save error: ${e.message}`, 'err')
  } finally {
    saving.value = false
    setTimeout(() => { saveMsg.value = '' }, 5000)
  }
}

// ── Health ────────────────────────────────────────────────────────────────────
const healthReport     = ref(null)
const healthLoading    = ref(true)
const healthRefreshing = ref(false)
const healthError      = ref(false)
let pollTimer          = null

const healthChecks = computed(() => healthReport.value?.checks || [])
const errorCount = computed(() => healthChecks.value.filter(c => c.status === 'error').length)
const warningCount = computed(() => healthChecks.value.filter(c => c.status === 'warning').length)
const okCount = computed(() => healthChecks.value.filter(c => c.status === 'ok').length)
const totalChecks = computed(() => healthChecks.value.length)
const lastCheckedAt = computed(() => healthReport.value?.checked_at || null)
const durationLabel = computed(() => {
  const ms = healthReport.value?.duration_ms
  return ms == null ? '' : `${ms}ms`
})

const healthGroups = computed(() => {
  const order = ['Docker', 'Config', 'Traefik', 'Network', 'Auth', 'Security', 'System', 'internal']
  const map = {}
  for (const check of healthChecks.value) {
    const category = check.category || 'System'
    if (!map[category]) map[category] = { category, checks: [], passing: 0, total: 0 }
    map[category].checks.push(check)
    map[category].total += 1
    if (check.status === 'ok') map[category].passing += 1
  }
  return Object.values(map).sort((a, b) => {
    const ai = order.indexOf(a.category)
    const bi = order.indexOf(b.category)
    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi)
  })
})

function formatHealthTime(unix) {
  if (!unix) return 'never'
  return new Date(unix * 1000).toLocaleTimeString([], {
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}

async function loadHealth(force = false) {
  if (force) healthRefreshing.value = true
  try {
    const report = await fetch(`/api/health${force ? '?refresh=true' : ''}`).then(r => r.json())
    healthReport.value = report
    healthError.value = false
    if (force) {
      const errs = (report.checks || []).filter(c => c.status === 'error').length
      const warns = (report.checks || []).filter(c => c.status === 'warning').length
      showToast(errs || warns ? `${errs} error(s), ${warns} warning(s)` : 'All health checks passed', errs ? 'err' : warns ? 'warn' : 'ok')
    }
  } catch (e) {
    healthError.value = true
    console.error('Health load failed:', e)
    if (force) showToast('Health check failed', 'err')
  } finally {
    healthLoading.value = false
    healthRefreshing.value = false
  }
}

onMounted(() => {
  loadSecrets()
  loadHealth()
  pollTimer = setInterval(loadHealth, 20000)
})
onUnmounted(() => { if (pollTimer) clearInterval(pollTimer) })
</script>

<style scoped>
.settings { max-width: 820px; margin: 0 auto; }

/* ── Section heads ───────────────────────────────────────────────────────── */
.section-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: var(--space-3);
}
.todo-head { margin-top: var(--space-5); }
.section-title { font-size: 14.5px; font-weight: 700; margin: 0 0 2px; }
.section-sub { font-size: 11.5px; color: var(--fg-2); margin: 0; }
.section-sub code { font-family: var(--font-mono); font-size: 11px; background: var(--bg-2); padding: 1px 5px; border-radius: 3px; }

/* ── Secrets ─────────────────────────────────────────────────────────────── */
.empty-secrets {
  font-size: 13px; color: var(--fg-2);
  padding: var(--space-4) 0;
}
.secrets-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}

.secret-group {
  background: var(--bg-1);
  border: 1.5px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}
.secret-group-head {
  display: flex; align-items: center; gap: 7px;
  padding: 6px 12px;
  background: var(--bg-0);
  border-bottom: 1px solid var(--border);
}
.secret-service-icon { font-size: 13px; }
.secret-service-name { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.07em; color: var(--fg-2); }

.secret-rows {
  padding: 6px 12px 10px;
  display: flex; flex-direction: column; gap: 8px;
}
.secret-row { padding-top: 6px; border-top: 1px solid var(--border); }
.secret-row:first-child { border-top: none; padding-top: 4px; }

.secret-info { margin-bottom: 4px; }
.secret-label-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 1px; }
.secret-label { font-size: 12px; font-weight: 600; color: var(--fg-0); }
.secret-status { font-size: 10.5px; font-weight: 600; }
.secret-status.set   { color: var(--ok); }
.secret-status.unset { color: var(--fg-2); }
.secret-hint { font-size: 10px; color: var(--fg-2); line-height: 1.3; font-style: italic; }

.secret-input-row { display: flex; align-items: center; gap: 5px; }
.secret-input {
  flex: 1; font-family: var(--font-mono); font-size: 11.5px;
  padding: 4px 8px; border-radius: 6px;
  border: 1.5px solid var(--border); background: var(--bg-0);
  color: var(--fg-0); outline: none; min-width: 0;
}
.secret-input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-dim); }
.eye-btn {
  font-size: 14px; padding: 0 4px; border: none;
  background: none; cursor: pointer; flex-shrink: 0; line-height: 1;
}
.secret-link {
  font-size: 11px; font-weight: 600; color: var(--accent);
  text-decoration: none; flex-shrink: 0; padding: 3px 6px;
  border: 1px solid var(--accent-dim); border-radius: 5px;
  background: var(--accent-subtle);
}
.secret-link:hover { background: var(--accent); color: #fff; }

.secrets-actions { display: flex; align-items: center; gap: 10px; margin-bottom: var(--space-4); }
.save-msg { font-size: 12px; font-weight: 500; }
.save-msg.ok  { color: var(--ok); }
.save-msg.err { color: var(--err); }

/* ── Health ──────────────────────────────────────────────────────────────── */
.health-head { margin-top: var(--space-5); align-items: center; }
.loading-state { display: flex; align-items: center; gap: var(--space-3); color: var(--fg-2); padding: var(--space-5) 0; font-size: 13px; }
.error-state { display: flex; align-items: center; gap: var(--space-2); color: var(--warn); padding: var(--space-4) 0; font-size: 13px; }

.health-section { display: flex; flex-direction: column; gap: var(--space-3); }
.health-summary {
  display: flex; align-items: center; justify-content: space-between; gap: var(--space-3);
  padding: 10px 14px; background: var(--bg-1); border: 1.5px solid var(--border);
  border-radius: var(--radius); flex-wrap: wrap;
}
.health-counts { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.health-count { font-size: 12px; font-weight: 700; white-space: nowrap; }
.health-count.err { color: var(--err); }
.health-count.warn { color: var(--warn); }
.health-count.ok { color: var(--ok); }
.health-meta { display: flex; align-items: center; gap: 6px; color: var(--fg-2); font-family: var(--font-mono); font-size: 11.5px; white-space: nowrap; }
.bullet { color: var(--border-strong); }

.health-groups { display: flex; flex-direction: column; gap: 8px; }
.health-card {
  background: var(--bg-1); border: 1.5px solid var(--border);
  border-radius: var(--radius); overflow: hidden;
}
.health-card-head {
  display: flex; align-items: center; justify-content: space-between; gap: var(--space-2);
  padding: 7px 14px; background: var(--bg-0); border-bottom: 1px solid var(--border);
}
.health-card-title { font-size: 10.5px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.07em; color: var(--fg-2); }
.health-card-meta { font-family: var(--font-mono); font-size: 10.5px; color: var(--fg-2); }
.health-card-body { padding: 3px 14px 5px; }
.health-row { padding: 7px 0; border-top: 1px solid var(--border); }
.health-row:first-child { border-top: none; }
.health-row-main { display: grid; grid-template-columns: 10px 175px 1fr; align-items: center; gap: 9px; min-width: 0; }
.health-row-label { font-size: 12.5px; font-weight: 600; color: var(--fg-0); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.health-row-result { font-size: 12.5px; color: var(--fg-1); min-width: 0; }
.health-row-detail, .health-row-hint { margin: 5px 0 0 194px; font-size: 11.5px; line-height: 1.45; color: var(--fg-2); }
.health-row.warning .health-row-result, .health-row.warning .health-row-detail { color: var(--warn); }
.health-row.error .health-row-result, .health-row.error .health-row-detail { color: var(--err); }
.health-row-hint { font-style: italic; }

.dot { width: 7px; height: 7px; border-radius: 50%; display: inline-block; }
.dot-ok { background: var(--ok); box-shadow: 0 0 4px rgba(22,163,74,0.5); }
.dot-warning { background: var(--warn); box-shadow: 0 0 4px rgba(217,119,6,0.5); }
.dot-error { background: var(--err); box-shadow: 0 0 4px rgba(220,38,38,0.5); }

@media (max-width: 700px) {
  .health-row-main { grid-template-columns: 10px 1fr; }
  .health-row-result { grid-column: 2; }
  .health-row-detail, .health-row-hint { margin-left: 19px; }
  .health-meta { white-space: normal; }
}

/* Spinner */
.spinner { display: inline-block; width: 14px; height: 14px; border: 1.5px solid var(--border-strong); border-top-color: var(--accent); border-radius: 50%; animation: spin 0.7s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
