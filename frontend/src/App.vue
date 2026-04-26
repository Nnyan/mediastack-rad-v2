<template>
  <div class="app-shell">
    <div class="nav-bar" :class="{ loading: navigating }"></div>

    <header class="topbar">
      <div class="logo">
        <span class="logo-media">Media</span><span class="logo-stack">Stack</span><span class="logo-rad">RAD</span>
      </div>

      <nav class="nav">
        <a
          v-for="item in navItems"
          :key="item.to"
          :class="['nav-link', { active: route.path === item.to, disabled: navigating }]"
          @click.prevent="navigate(item.to)"
          href="#"
        >
          <span class="nav-icon">{{ item.icon }}</span>
          {{ item.label }}
          <span v-if="item.badge" class="nav-badge" :style="{ background: item.badgeColor }">
            {{ item.badge }}
          </span>
        </a>
      </nav>

      <div class="topbar-right">
        <div class="status-chips" v-if="info.docker_version">
          <div class="chip chip-green">
            <span class="chip-dot"></span>
            {{ info.running }} running
          </div>
          <div class="chip chip-orange" v-if="info.stopped > 0">
            {{ info.stopped }} stopped
          </div>
          <div class="chip chip-muted">
            {{ info.cpus }}C · {{ gb(info.memory_bytes) }}GB
          </div>
        </div>

        <button class="theme-btn" @click="toggleTheme" :title="isDark ? 'Switch to light' : 'Switch to dark'">
          <span v-if="isDark">☀</span>
          <span v-else>☽</span>
        </button>
      </div>
    </header>

    <main class="main-content">
      <router-view v-slot="{ Component }">
        <transition name="fade-up" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>

    <transition name="toast-slide">
      <div v-if="toast" :class="['toast', toast.type]">
        <span class="toast-icon">{{ toast.type === 'ok' ? '✓' : toast.type === 'err' ? '✗' : '!' }}</span>
        {{ toast.message }}
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, provide } from 'vue'
import { useRouter, useRoute } from 'vue-router'

const router = useRouter()
const route  = useRoute()

const info       = ref({})
const health     = ref(null)
const checklist  = ref([])
const toast      = ref(null)
const navigating = ref(false)
const isDark     = ref(localStorage.getItem('rad-theme') === 'dark')

if (isDark.value) document.documentElement.dataset.theme = 'dark'

function navigate(to) {
  if (navigating.value || route.path === to) return
  navigating.value = true
  router.push(to).finally(() => setTimeout(() => { navigating.value = false }, 200))
}

// Store the unsubscribe function so we can clean it up on unmount.
// Without this, each mount adds another afterEach handler that never fires.
const unsubAfterEach = router.afterEach(() => {
  setTimeout(() => { navigating.value = false }, 200)
})

const errorCount   = computed(() => health.value?.summary?.error || 0)
const pendingCount = computed(() =>
  checklist.value.filter(i => !i.done && i.category === 'essential').length
)

const navItems = computed(() => [
  { to: '/stack-builder', label: 'Stack Builder', icon: '⊞' },
  { to: '/traefik',       label: 'Traefik',       icon: '⇄' },
  { to: '/settings',      label: 'Settings',      icon: '⚙',
    badge: errorCount.value || null, badgeColor: 'var(--err)' },
  { to: '/todo',          label: 'To-Do',         icon: '☑',
    badge: pendingCount.value || null, badgeColor: 'var(--orange)' },
])

function showToast(message, type = 'ok', ms = 3500) {
  toast.value = { message, type }
  setTimeout(() => { toast.value = null }, ms)
}
provide('showToast', showToast)

function toggleTheme() {
  isDark.value = !isDark.value
  if (isDark.value) {
    document.documentElement.dataset.theme = 'dark'
    localStorage.setItem('rad-theme', 'dark')
  } else {
    delete document.documentElement.dataset.theme
    localStorage.removeItem('rad-theme')
  }
}

function gb(bytes) { return bytes ? (bytes / 1073741824).toFixed(1) : '0' }

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
    // Non-fatal — topbar data is supplementary; don't show a toast for this
    console.warn('App.vue refresh failed:', e)
  }
}

onMounted(() => { refresh(); pollTimer = setInterval(refresh, 15000) })
onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  unsubAfterEach()  // remove the afterEach navigation guard
})
</script>

<style scoped>
.nav-bar {
  height: 3px;
  background: linear-gradient(90deg, var(--pink), var(--purple), var(--blue));
  background-size: 200% 100%;
  width: 100%;
  opacity: 0;
  transition: opacity 0.15s;
}
.nav-bar.loading {
  opacity: 1;
  animation: shimmer 1.2s linear infinite;
}
@keyframes shimmer {
  0%   { background-position: 100% 0; }
  100% { background-position: -100% 0; }
}

.topbar {
  display: flex;
  align-items: center;
  height: 54px;
  padding: 0 var(--space-5);
  gap: var(--space-4);
  background: var(--bg-1);
  border-bottom: 1.5px solid var(--border);
  box-shadow: var(--shadow-1);
  position: sticky;
  top: 0;
  z-index: 100;
  flex-shrink: 0;
}

.logo {
  font-family: 'Outfit', sans-serif;
  font-weight: 800;
  font-size: 16px;
  letter-spacing: -0.03em;
  white-space: nowrap;
  flex-shrink: 0;
}
.logo-media { color: var(--fg-1); }
.logo-stack { color: var(--fg-0); }
.logo-rad {
  margin-left: 2px;
  background: linear-gradient(135deg, var(--purple), var(--pink));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.nav { display: flex; gap: 2px; flex: 1; }
.nav-link {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: var(--radius-sm);
  font-size: 13.5px;
  font-weight: 500;
  color: var(--fg-1);
  cursor: pointer;
  transition: color 0.15s, background 0.15s;
  text-decoration: none;
  user-select: none;
}
.nav-link:hover:not(.disabled) { color: var(--fg-0); background: var(--bg-2); text-decoration: none; }
.nav-link.active               { color: var(--accent); background: var(--accent-dim); font-weight: 600; }
.nav-link.disabled             { opacity: 0.5; cursor: not-allowed; }
.nav-icon  { font-size: 12px; opacity: 0.7; }
.nav-badge {
  font-size: 10px; font-weight: 700;
  padding: 1px 6px; border-radius: 20px;
  color: #fff; min-width: 18px; text-align: center;
}

.topbar-right { display: flex; align-items: center; gap: var(--space-2); margin-left: auto; flex-shrink: 0; }

.status-chips { display: flex; gap: var(--space-2); align-items: center; }
.chip {
  display: flex; align-items: center; gap: 5px;
  font-size: 12px; font-weight: 500;
  padding: 4px 10px; border-radius: 20px; white-space: nowrap;
}
.chip-green  { background: var(--ok-bg);   color: var(--ok);   border: 1px solid rgba(22,163,74,0.2); }
.chip-orange { background: var(--warn-bg); color: var(--warn); border: 1px solid rgba(217,119,6,0.2); }
.chip-muted  { background: var(--bg-2);    color: var(--fg-2); border: 1px solid var(--border); font-family: 'JetBrains Mono', monospace; }
.chip-dot    { width: 6px; height: 6px; border-radius: 50%; background: var(--ok); box-shadow: 0 0 4px var(--ok); flex-shrink: 0; }

.theme-btn {
  width: 34px; height: 34px; padding: 0;
  border-radius: 50%; font-size: 16px;
  display: flex; align-items: center; justify-content: center;
  background: var(--bg-2); border-color: var(--border);
}

.main-content {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-5) var(--space-6);
  /* Reserve scrollbar gutter at all times so the scrollbar appearing/disappearing
     never shifts the page content horizontally (was causing ~15px tile reflow
     when config sections opened and page height crossed the viewport threshold) */
  scrollbar-gutter: stable;
}

.fade-up-enter-active, .fade-up-leave-active { transition: opacity 0.15s ease, transform 0.15s ease; }
.fade-up-enter-from { opacity: 0; transform: translateY(6px); }
.fade-up-leave-to   { opacity: 0; transform: translateY(-4px); }

.toast {
  position: fixed; bottom: var(--space-5); right: var(--space-5);
  background: var(--bg-1); border: 1.5px solid var(--border);
  border-radius: var(--radius); padding: 12px 16px;
  box-shadow: var(--shadow-2); max-width: 360px;
  z-index: 1000; font-size: 13.5px; font-weight: 500;
  display: flex; align-items: center; gap: var(--space-2);
}
.toast-icon { font-size: 15px; font-weight: 700; flex-shrink: 0; }
.toast.ok   { border-left: 3px solid var(--ok);  }  .toast.ok  .toast-icon { color: var(--ok);  }
.toast.err  { border-left: 3px solid var(--err); }  .toast.err .toast-icon { color: var(--err); }
.toast.warn { border-left: 3px solid var(--warn);}  .toast.warn .toast-icon{ color: var(--warn);}

.toast-slide-enter-active, .toast-slide-leave-active { transition: all 0.2s ease; }
.toast-slide-enter-from, .toast-slide-leave-to { opacity: 0; transform: translateX(16px); }
</style>
