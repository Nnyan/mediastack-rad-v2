<template>
  <div>
    <div class="page-head">
      <div>
        <h1 class="page-title">Setup Checklist</h1>
        <p class="muted small">Only incomplete items are shown. Items disappear automatically when resolved.</p>
      </div>
      <div class="pill-count" v-if="total > 0">{{ total }} remaining</div>
    </div>

    <div v-if="loading" class="empty-state">
      <div class="spinner"></div>
      <span>Checking system state…</span>
    </div>

    <div v-else-if="loadError" class="empty-state error-state">
      <span class="error-icon">⚠</span>
      <span>Could not load checklist — is the backend running?</span>
    </div>

    <div v-else-if="total === 0" class="all-done">
      <div class="done-icon">✓</div>
      <div class="done-title">All set up</div>
      <div class="done-sub muted">Nothing left to configure. Check the Health tab for ongoing monitoring.</div>
    </div>

    <div v-else>
      <div v-for="cat in categories" :key="cat" class="section">
        <div class="section-label">
          <span class="section-dot" :class="cat"></span>
          {{ cat }}
          <span class="section-count">{{ itemsByCategory[cat]?.length }}</span>
        </div>
        <div class="task-list">
          <div v-for="item in itemsByCategory[cat]" :key="item.id" class="task" :class="cat">
            <div class="task-content">
              <div class="task-title">{{ item.title }}</div>
              <div class="task-detail">{{ item.detail }}</div>
            </div>
            <a
              v-if="item.action_url"
              :href="item.action_url"
              :target="item.action_url.startsWith('http') ? '_blank' : '_self'"
              class="task-action"
            >{{ item.action_url.startsWith('http') ? 'Open ↗' : 'Go →' }}</a>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

const items = ref([])
const loading = ref(true)
const loadError = ref(false)
let pollTimer = null

const total = computed(() => items.value.length)
const itemsByCategory = computed(() => {
  const out = {}
  for (const it of items.value) (out[it.category] ||= []).push(it)
  return out
})
const categories = computed(() =>
  ['essential', 'recommended', 'optional'].filter(c => itemsByCategory.value[c]?.length > 0)
)

async function refresh() {
  try {
    const data = await fetch('/api/checklist').then(r => r.json())
    items.value = data
    loadError.value = false
  } catch (e) {
    loadError.value = true
    console.error('Checklist fetch failed:', e)
  } finally {
    loading.value = false
  }
}

onMounted(() => { refresh(); pollTimer = setInterval(refresh, 15000) })
onUnmounted(() => { if (pollTimer) clearInterval(pollTimer) })
</script>

<style scoped>
.page-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: var(--space-5);
}
.pill-count {
  font-family: var(--font-mono);
  font-size: 12px;
  padding: 4px 12px;
  border-radius: 12px;
  background: var(--bg-2);
  border: 1px solid var(--border);
  color: var(--fg-1);
  white-space: nowrap;
}
.empty-state {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  color: var(--fg-2);
  padding: var(--space-6) 0;
}
.spinner {
  width: 16px; height: 16px;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.all-done { text-align: center; padding: var(--space-6) 0; }
.done-icon { font-size: 48px; color: var(--ok); margin-bottom: var(--space-3); }
.done-title { font-size: 20px; font-weight: 600; margin-bottom: var(--space-2); }

.section { margin-bottom: var(--space-5); }
.section-label {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--fg-2);
  margin-bottom: var(--space-2);
}
.section-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--fg-2); }
.section-dot.essential { background: var(--err); }
.section-dot.recommended { background: var(--warn); }
.section-count {
  font-size: 10px; padding: 1px 6px; border-radius: 8px;
  background: var(--bg-2); color: var(--fg-2); font-weight: 600;
}

.task-list { display: flex; flex-direction: column; gap: 2px; }
.task {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-3) var(--space-4);
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-left: 3px solid transparent;
  border-radius: var(--radius);
  transition: background 0.1s;
}
.task:hover { background: var(--bg-2); }
.task.essential { border-left-color: var(--err-dim); }
.task.recommended { border-left-color: var(--warn-dim); }

.task-content { flex: 1; min-width: 0; }
.task-title { font-weight: 500; font-size: 14px; margin-bottom: 2px; }
.task-detail { font-size: 12px; color: var(--fg-2); line-height: 1.5; }

.task-action {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--accent);
  white-space: nowrap;
  flex-shrink: 0;
  padding: 4px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  transition: background 0.1s;
}
.task-action:hover { background: var(--bg-2); text-decoration: none; }
.error-state { color: var(--warn); }
.error-icon { font-size: 18px; }
</style>
