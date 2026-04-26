<template>
  <div class="todo-view">
    <div class="todo-header">
      <div>
        <h1 class="page-title">To-Do</h1>
        <p class="subtitle">Setup tasks refresh automatically every 15 seconds.</p>
      </div>
      <div class="pill-count" v-if="total > 0">{{ total }} remaining</div>
    </div>

    <div v-if="checklistLoading" class="loading-state">
      <span class="spinner"></span> Checking system state…
    </div>

    <div v-else-if="checklistError" class="error-state">
      <span class="error-icon">⚠</span>
      Could not load checklist — is the backend running?
    </div>

    <div v-else-if="total === 0" class="all-done">
      <div class="done-icon">✓</div>
      <div class="done-title">All set up</div>
      <div class="done-sub muted">Nothing left to configure. Check the Health section in Settings for ongoing monitoring.</div>
    </div>

    <div v-else class="task-sections">
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
import { ref, computed, onMounted, onUnmounted } from 'vue'

const items = ref([])
const checklistLoading = ref(true)
const checklistError = ref(false)
const openTask = ref(null)
let pollTimer = null

const total = computed(() => items.value.length)
const itemsByCategory = computed(() => {
  const out = {}
  for (const it of items.value) (out[it.category] ||= []).push(it)
  return out
})
const categories = computed(() =>
  ['essential', 'recommended', 'optional'].filter(cat => itemsByCategory.value[cat]?.length > 0)
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
  refreshChecklist()
  pollTimer = setInterval(refreshChecklist, 15000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.todo-view { max-width: 820px; margin: 0 auto; padding-bottom: 64px; }
.todo-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}
.subtitle { margin: 0; color: var(--fg-2); font-size: 12px; }
.pill-count {
  font-family: var(--font-mono);
  font-size: 12px;
  padding: 4px 12px;
  border-radius: 12px;
  background: var(--bg-2);
  border: 1px solid var(--border);
  color: var(--fg-1);
}
.loading-state,
.error-state {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  color: var(--fg-2);
  padding: var(--space-5) 0;
  font-size: 13px;
}
.error-icon { color: var(--warn); font-size: 16px; }
.all-done { text-align: center; padding: var(--space-6) 0; }
.done-icon { font-size: 48px; color: var(--ok); margin-bottom: var(--space-3); }
.done-title { font-size: 20px; font-weight: 600; margin-bottom: var(--space-2); }

.task-sections { display: flex; flex-direction: column; gap: var(--space-3); }
.task-section { background: var(--bg-1); border: 1.5px solid var(--border); border-radius: var(--radius); padding: var(--space-3); }
.task-section-label {
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
.section-dot.essential   { background: var(--err); }
.section-dot.recommended { background: var(--warn); }
.section-count { font-size: 10px; padding: 1px 6px; border-radius: 8px; background: var(--bg-2); color: var(--fg-2); font-weight: 600; }

.task-list { display: flex; flex-direction: column; gap: 6px; }
.task {
  background: var(--bg-0);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  overflow: hidden;
  transition: background 0.1s, border-color 0.1s;
}
.task:hover { background: var(--bg-2); }
.task-open { border-color: var(--accent); }
.task.essential   { border-left: 3px solid var(--err-dim); }
.task.recommended { border-left: 3px solid var(--warn-dim); }
.task.optional    { border-left: 3px solid var(--border); }
.task-main {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
}
.task-title { font-weight: 500; font-size: 13px; flex: 1; }
.task-chevron { font-size: 14px; color: var(--fg-2); flex-shrink: 0; transition: transform 0.13s; display: inline-block; }
.task-chevron.open { transform: rotate(90deg); }
.task-detail {
  padding: 0 var(--space-3) var(--space-3);
  font-size: 12px;
  color: var(--fg-1);
  line-height: 1.5;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
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
  text-decoration: none;
}
.task-action:hover { background: var(--bg-2); }
.task-action-inline { align-self: flex-start; }

.spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 1.5px solid var(--border-strong);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.muted { color: var(--fg-2); }
.subtitle { font-size: 12.5px; color: var(--fg-2); }
</style>
