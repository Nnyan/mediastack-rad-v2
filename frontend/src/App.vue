<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="logo">MediaStack-RAD<span class="v">v{{ version }}</span></div>
      <nav class="nav">
        <router-link to="/containers">Containers</router-link>
        <router-link to="/stack-builder">Stack Builder</router-link>
        <router-link to="/traefik">Traefik</router-link>
        <router-link to="/health">
          Health
          <span v-if="errorCount > 0" class="badge">{{ errorCount }}</span>
        </router-link>
        <router-link to="/checklist">
          Checklist
          <span v-if="pendingCount > 0" class="badge" style="background: var(--warn); color: #000">
            {{ pendingCount }}
          </span>
        </router-link>
      </nav>
      <div class="info" v-if="info.docker_version">
        <span>Docker <strong>{{ info.docker_version }}</strong></span>
        <span>
          <span class="dot ok"></span>Running <strong>{{ info.running }}</strong>
        </span>
        <span v-if="info.stopped > 0" class="muted">
          Stopped <strong>{{ info.stopped }}</strong>
        </span>
        <span>{{ info.cpus }} CPU · {{ gb(info.memory_bytes) }} GB</span>
      </div>
      <button class="theme-toggle" @click="toggleTheme">
        {{ theme === 'dark' ? '☽' : '☀' }}
      </button>
    </header>
    <main class="main">
      <router-view />
    </main>

    <div v-if="toast" :class="['toast', toast.type]">
      {{ toast.message }}
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, provide } from 'vue'

const version = ref('2.0.0')
const info = ref({})
const health = ref(null)
const checklist = ref([])
const toast = ref(null)
const theme = ref(localStorage.getItem('rad-theme') || 'dark')

document.documentElement.dataset.theme = theme.value

const errorCount = computed(
  () => health.value?.summary?.error || 0
)
const pendingCount = computed(
  () => checklist.value.filter(i => !i.done && i.category === 'essential').length
)

// Toast helper — exposed via provide() so any view can trigger one.
function showToast(message, type = 'ok', ms = 3500) {
  toast.value = { message, type }
  setTimeout(() => { toast.value = null }, ms)
}
provide('showToast', showToast)

function toggleTheme() {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
  document.documentElement.dataset.theme = theme.value
  localStorage.setItem('rad-theme', theme.value)
}

function gb(bytes) {
  if (!bytes) return '0'
  return (bytes / 1024 / 1024 / 1024).toFixed(1)
}

// Poll global state every 15s so the topbar and nav badges stay fresh.
let pollTimer = null

async function refresh() {
  try {
    const [i, h, c] = await Promise.allSettled([
      fetch('/api/info').then(r => r.json()),
      fetch('/api/health').then(r => r.json()),
      fetch('/api/checklist').then(r => r.json()),
    ])
    if (i.status === 'fulfilled') info.value = i.value
    if (h.status === 'fulfilled') health.value = h.value
    if (c.status === 'fulfilled') checklist.value = c.value
  } catch (e) {
    console.error('Topbar refresh failed', e)
  }
}

// Get the app version so the header label is accurate.
async function loadVersion() {
  try {
    const r = await fetch('/api/version').then(r => r.json())
    version.value = r.version
  } catch {}
}

onMounted(() => {
  loadVersion()
  refresh()
  pollTimer = setInterval(refresh, 15000)
})
onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>
