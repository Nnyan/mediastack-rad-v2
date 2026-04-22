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

    <!-- ── To-do ────────────────────────────────────────────────────────── -->
    <div class="section-head todo-head">
      <div>
        <h2 class="section-title">To-do</h2>
        <p class="section-sub">Setup tasks that disappear when complete.</p>
      </div>
      <div class="pill-count" v-if="total > 0">{{ total }} remaining</div>
    </div>

    <div v-if="checklistLoading" class="loading-state">
      <span class="spinner"></span> Checking system state…
    </div>

    <div v-else-if="checklistError" class="loading-state">
      <span style="color: var(--warn)">⚠</span>
      Could not load checklist — is the backend running?
    </div>

    <div v-else-if="total === 0" class="all-done">
      <div class="done-icon">✓</div>
      <div class="done-title">All set up</div>
      <div class="done-sub muted">Nothing left to configure. Check the Health tab for ongoing monitoring.</div>
    </div>

    <div v-else>
      <div v-for="cat in categories" :key="cat" class="task-section">
        <div class="task-section-label">
          <span class="section-dot" :class="cat"></span>
          {{ cat }}
          <span class="section-count">{{ itemsByCategory[cat]?.length }}</span>
        </div>
        <div class="task-list">
          <div
            v-for="item in itemsByCategory[cat]"
            :key="item.id"
            class="task"
            :class="[cat, { 'task-open': openTask === item.id }]"
            @click="openTask = openTask === item.id ? null : item.id"
          >
            <div class="task-main">
              <div class="task-title">{{ item.title }}</div>
              <a
                v-if="item.action_url && openTask !== item.id"
                :href="item.action_url"
                :target="item.action_url.startsWith('http') ? '_blank' : '_self'"
                class="task-action"
                @click.stop
              >{{ item.action_url.startsWith('http') ? 'Open ↗' : 'Go →' }}</a>
              <span class="task-chevron" :class="{ open: openTask === item.id }">›</span>
            </div>
            <div v-if="openTask === item.id" class="task-detail">
              {{ item.detail }}
              <a
                v-if="item.action_url"
                :href="item.action_url"
                :target="item.action_url.startsWith('http') ? '_blank' : '_self'"
                class="task-action task-action-inline"
                @click.stop
              >{{ item.action_url.startsWith('http') ? 'Open ↗' : 'Go →' }}</a>
            </div>
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

// ── Checklist ─────────────────────────────────────────────────────────────────
const items          = ref([])
const checklistLoading = ref(true)
const checklistError = ref(false)
const openTask       = ref(null)
let pollTimer        = null

const total = computed(() => items.value.length)
const itemsByCategory = computed(() => {
  const out = {}
  for (const it of items.value) (out[it.category] ||= []).push(it)
  return out
})
const categories = computed(() =>
  ['essential', 'recommended', 'optional'].filter(c => itemsByCategory.value[c]?.length > 0)
)

async function refreshChecklist() {
  try {
    const data = await fetch('/api/checklist').then(r => r.json())
    items.value = data
    checklistError.value = false
  } catch (e) {
    checklistError.value = true
    console.error('Checklist fetch failed:', e)
  } finally {
    checklistLoading.value = false
  }
}

onMounted(() => {
  loadSecrets()
  refreshChecklist()
  pollTimer = setInterval(refreshChecklist, 15000)
})
onUnmounted(() => { if (pollTimer) clearInterval(pollTimer) })
</script>

<style scoped>
.settings { max-width: 860px; }

/* ── Section heads ───────────────────────────────────────────────────────── */
.section-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: var(--space-4);
}
.todo-head { margin-top: var(--space-6); }
.section-title { font-size: 15px; font-weight: 700; margin: 0 0 3px; }
.section-sub { font-size: 12px; color: var(--fg-2); margin: 0; }
.section-sub code { font-family: var(--font-mono); font-size: 11px; background: var(--bg-2); padding: 1px 5px; border-radius: 3px; }

/* ── Secrets ─────────────────────────────────────────────────────────────── */
.empty-secrets {
  font-size: 13px; color: var(--fg-2);
  padding: var(--space-4) 0;
}
.secrets-grid { display: flex; flex-direction: column; gap: 10px; margin-bottom: var(--space-4); }

.secret-group {
  background: var(--bg-1);
  border: 1.5px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}
.secret-group-head {
  display: flex; align-items: center; gap: 7px;
  padding: 7px 14px;
  background: var(--bg-0);
  border-bottom: 1px solid var(--border);
}
.secret-service-icon { font-size: 13px; }
.secret-service-name { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.07em; color: var(--fg-2); }

.secret-rows { padding: 4px 14px 10px; display: flex; flex-direction: column; gap: 10px; }
.secret-row { padding-top: 8px; border-top: 1px solid var(--border); }
.secret-row:first-child { border-top: none; padding-top: 4px; }

.secret-info { margin-bottom: 5px; }
.secret-label-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 1px; }
.secret-label { font-size: 12px; font-weight: 600; color: var(--fg-0); }
.secret-status { font-size: 10.5px; font-weight: 600; }
.secret-status.set   { color: var(--ok); }
.secret-status.unset { color: var(--fg-2); }
.secret-hint { font-size: 10px; color: var(--fg-2); line-height: 1.3; font-style: italic; }

.secret-input-row { display: flex; align-items: center; gap: 6px; }
.secret-input {
  flex: 1; font-family: var(--font-mono); font-size: 12px;
  padding: 5px 9px; border-radius: 6px;
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

.secrets-actions { display: flex; align-items: center; gap: 12px; margin-bottom: var(--space-5); }
.save-msg { font-size: 12px; font-weight: 500; }
.save-msg.ok  { color: var(--ok); }
.save-msg.err { color: var(--err); }

/* ── Checklist ───────────────────────────────────────────────────────────── */
.pill-count {
  font-family: var(--font-mono); font-size: 12px;
  padding: 4px 12px; border-radius: 12px;
  background: var(--bg-2); border: 1px solid var(--border); color: var(--fg-1);
}
.loading-state { display: flex; align-items: center; gap: var(--space-3); color: var(--fg-2); padding: var(--space-5) 0; font-size: 13px; }
.all-done { text-align: center; padding: var(--space-6) 0; }
.done-icon { font-size: 48px; color: var(--ok); margin-bottom: var(--space-3); }
.done-title { font-size: 20px; font-weight: 600; margin-bottom: var(--space-2); }

.task-section { margin-bottom: var(--space-4); }
.task-section-label {
  display: flex; align-items: center; gap: var(--space-2);
  font-size: 11px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.08em; color: var(--fg-2); margin-bottom: var(--space-2);
}
.section-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--fg-2); }
.section-dot.essential   { background: var(--err); }
.section-dot.recommended { background: var(--warn); }
.section-count { font-size: 10px; padding: 1px 6px; border-radius: 8px; background: var(--bg-2); color: var(--fg-2); font-weight: 600; }

.task-list { display: flex; flex-direction: column; gap: 2px; }
.task {
  background: var(--bg-1); border: 1px solid var(--border);
  border-left: 3px solid transparent; border-radius: var(--radius);
  cursor: pointer; transition: background 0.1s; overflow: hidden;
}
.task:hover { background: var(--bg-2); }
.task.essential   { border-left-color: var(--err-dim); }
.task.recommended { border-left-color: var(--warn-dim); }

.task-main {
  display: flex; align-items: center; gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
}
.task-title { font-weight: 500; font-size: 13.5px; flex: 1; }
.task-chevron { font-size: 14px; color: var(--fg-2); flex-shrink: 0; transition: transform 0.13s; display: inline-block; }
.task-chevron.open { transform: rotate(90deg); }

.task-detail {
  padding: 0 var(--space-4) var(--space-3);
  font-size: 12px; color: var(--fg-1);
  line-height: 1.55; display: flex; flex-direction: column; gap: 8px;
}

.task-action {
  font-family: var(--font-mono); font-size: 12px;
  color: var(--accent); white-space: nowrap; flex-shrink: 0;
  padding: 4px 10px; border: 1px solid var(--border);
  border-radius: var(--radius); transition: background 0.1s;
  text-decoration: none; align-self: flex-start;
}
.task-action:hover { background: var(--bg-2); text-decoration: none; }
.task-action-inline { margin-top: 2px; }

/* Spinner */
.spinner { display: inline-block; width: 14px; height: 14px; border: 1.5px solid var(--border-strong); border-top-color: var(--accent); border-radius: 50%; animation: spin 0.7s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
