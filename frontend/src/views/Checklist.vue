<template>
  <div>
    <h1 class="page-title">
      Setup Checklist
      <span class="sub">
        {{ done }} / {{ total }} complete
      </span>
    </h1>

    <div class="card muted small mb-4">
      This is a running to-do list for getting your stack fully
      configured. Items check themselves off as RAD detects the
      corresponding state — for example, Plex running satisfies
      "Bring the stack up" but we can't detect whether you've
      actually claimed your server, so some items never auto-complete.
    </div>

    <div v-for="cat in categories" :key="cat">
      <h3 class="section-title">{{ cat }}</h3>
      <div class="items">
        <div
          v-for="item in itemsByCategory[cat]"
          :key="item.id"
          class="item"
          :class="{ done: item.done }"
        >
          <span class="check" :class="{ done: item.done }">
            {{ item.done ? '✓' : '○' }}
          </span>
          <div class="item-body">
            <div class="item-title">{{ item.title }}</div>
            <div class="item-detail">{{ item.detail }}</div>
            <a
              v-if="item.action_url"
              :href="item.action_url"
              :target="item.action_url.startsWith('http') ? '_blank' : '_self'"
              class="item-action"
            >
              {{ item.action_url.startsWith('http') ? 'Open ↗' : 'Go →' }}
            </a>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

const items = ref([])
let pollTimer = null

const done = computed(() => items.value.filter(i => i.done).length)
const total = computed(() => items.value.length)

const itemsByCategory = computed(() => {
  const out = {}
  for (const it of items.value) (out[it.category] ||= []).push(it)
  return out
})
const categories = computed(() => {
  // Fixed order even if backend returns them differently.
  const order = ['essential', 'recommended', 'optional']
  return order.filter(c => itemsByCategory.value[c])
})

async function refresh() {
  items.value = await fetch('/api/checklist').then(r => r.json())
}

onMounted(() => {
  refresh()
  pollTimer = setInterval(refresh, 15000)
})
onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.section-title {
  margin: var(--space-5) 0 var(--space-2);
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--fg-2);
  font-weight: 600;
}
.section-title:first-of-type { margin-top: 0; }

.items { display: flex; flex-direction: column; gap: var(--space-2); }
.item {
  display: flex;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}
.item.done { opacity: 0.6; }

.check {
  font-size: 18px;
  line-height: 1;
  color: var(--fg-2);
  flex-shrink: 0;
  margin-top: 2px;
}
.check.done { color: var(--ok); }

.item-body { flex: 1; }
.item-title { font-weight: 500; font-size: 14px; margin-bottom: 2px; }
.item.done .item-title { text-decoration: line-through; }
.item-detail { font-size: 13px; color: var(--fg-1); line-height: 1.5; }
.item-action {
  display: inline-block;
  margin-top: 6px;
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--accent);
}
</style>
