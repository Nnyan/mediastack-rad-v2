<template>
  <div class="app-shell">
    <!-- Progress bar — visible during any navigation or API loading -->
    <div class="nav-progress" :class="{ active: navigating }"></div>

    <header class="topbar">
      <div class="logo">MediaStack<span class="logo-rad">RAD</span></div>
      <nav class="nav">
        <router-link
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          :class="{ disabled: navigating }"
          @click.prevent="navigate(item.to)"
        >
          {{ item.label }}
          <span v-if="item.badge" class="badge" :style="item.badgeStyle">
            {{ item.badge }}
          </span>
        </router-link>
      </nav>
      <div class="topbar-info" v-if="info.docker_version">
        <span class="info-chip">
          <span class="dot ok"></span>{{ info.running }} running
        </span>
        <span class="info-chip muted" v-if="info.stopped > 0">
          {{ info.stopped }} stopped
        </span>
        <span class="info-chip muted">
          Docker {{ info.docker_version }}
        </span>
        <span class="info-chip muted">
          {{ info.cpus }}C · {{ gb(info.memory_bytes) }}GB
        </span>
      </div>
      <button class="theme-btn" @click="toggleTheme" :title="theme === 'dark' ? 'Light mode' : 'Dark mode'">
        {{ theme === 'dark' ? '☽' : '☀' }}
      </button>
    </header>

    <main class="main">
      <router-view v-slot="{ Component }">
        <transition name="page" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>

    <transition name="toast">
      <div v-if="toast" :class="['toast', toast.type]">{{ toast.message }}</div>
    </transition>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, provide } from 'vue'
import { useRouter, useRoute } from 'vue-router'

const router = useRouter()
const route  = useRoute()

const version   = ref('2.0.0')
const info      = ref({})
const health    = ref(null)
const checklist = ref([])
const toast     = ref(null)
const navigating = ref(false)
const theme     = ref(localStorage.getItem('rad-theme') || 'dark')

document.documentElement.dataset.theme = theme.value

// Navigation guard — prevents double-clicking and provides visual feedback
function navigate(to) {
  if (navigating.value || route.path === to) return
  navigating.value = true
  router.push(to).finally(() => {
    // Small delay so the bar is visible even on instant renders
    setTimeout(() => { navigating.value = false }, 150)
  })
}

// Also reset on browser back/forward
router.afterEach(() => {
  setTimeout(() => { navigating.value = false }, 150)
})

const errorCount  = computed(() => health.value?.summary?.error || 0)
const pendingCount = computed(
  () => checklist.value.filter(i => !i.done && i.category === 'essential').length
)

const navItems = computed(() => [
  { to: '/containers',    label: 'Containers' },
  { to: '/stack-builder', label: 'Stack Builder' },
  { to: '/traefik',       label: 'Traefik' },
  {
    to: '/health',
    label: 'Health',
    badge: errorCount.value || null,
    badgeStyle: 'background: var(--err); color: #fff',
  },
  {
    to: '/checklist',
    label: 'Checklist',
    badge: pendingCount.value || null,
    badgeStyle: 'background: var(--warn); color: #000',
  },
])

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
  return bytes ? (bytes / 1073741824).toFixed(1) : '0'
}

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
  } catch {}
}

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

<style scoped>
/* Progress bar */
.nav-progress {
  position: fixed;
  top: 0;
  left: 0;
  height: 2px;
  width: 0;
  background: var(--accent);
  z-index: 9999;
  transition: width 0s;
  border-radius: 0 2px 2px 0;
}
.nav-progress.active {
  width: 70%;
  transition: width 0.4s ease-out;
  box-shadow: 0 0 8px var(--accent);
}

.topbar {
  display: flex;
  align-items: center;
  padding: 0 var(--space-5);
  height: 48px;
  background: var(--bg-1);
  border-bottom: 1px solid var(--border);
  gap: var(--space-4);
  position: sticky;
  top: 0;
  z-index: 100;
}

.logo {
  font-family: var(--font-mono);
  font-weight: 700;
  font-size: 14px;
  letter-spacing: -0.02em;
  color: var(--fg-1);
  white-space: nowrap;
}
.logo-rad {
  color: var(--accent);
  margin-left: 3px;
}

.nav {
  display: flex;
  gap: 2px;
  flex: 1;
}
.nav a {
  position: relative;
  padding: 6px 14px;
  color: var(--fg-1);
  border-radius: var(--radius);
  font-size: 13px;
  font-weight: 500;
  text-decoration: none;
  transition: color 0.1s, background 0.1s;
  user-select: none;
}
.nav a:hover:not(.disabled) {
  color: var(--fg-0);
  background: var(--bg-2);
}
.nav a.router-link-active {
  color: var(--fg-0);
  background: var(--bg-2);
}
.nav a.router-link-active::after {
  content: '';
  position: absolute;
  bottom: -1px;
  left: 14px;
  right: 14px;
  height: 2px;
  background: var(--accent);
  border-radius: 2px 2px 0 0;
}
.nav a.disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.badge {
  margin-left: 5px;
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 8px;
  font-weight: 600;
  vertical-align: middle;
  line-height: 1.4;
  display: inline-block;
}

.topbar-info {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  margin-left: auto;
}
.info-chip {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--fg-1);
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  background: var(--bg-0);
  border: 1px solid var(--border);
  border-radius: 20px;
  white-space: nowrap;
}
.info-chip.muted { color: var(--fg-2); }

.theme-btn {
  padding: 4px 10px;
  font-size: 14px;
  flex-shrink: 0;
}

/* Page transition */
.page-enter-active,
.page-leave-active {
  transition: opacity 0.12s ease, transform 0.12s ease;
}
.page-enter-from {
  opacity: 0;
  transform: translateY(4px);
}
.page-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

/* Toast */
.toast {
  position: fixed;
  bottom: var(--space-5);
  right: var(--space-5);
  background: var(--bg-2);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius);
  padding: 10px 16px;
  box-shadow: var(--shadow-2);
  max-width: 360px;
  z-index: 1000;
  font-size: 13px;
}
.toast.ok  { border-left: 3px solid var(--ok); }
.toast.err { border-left: 3px solid var(--err); }
.toast.warn { border-left: 3px solid var(--warn); }

.toast-enter-active, .toast-leave-active { transition: all 0.2s ease; }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translateY(8px); }

.main {
  overflow-y: auto;
  padding: var(--space-5) var(--space-6);
  height: calc(100vh - 48px);
}
</style>
