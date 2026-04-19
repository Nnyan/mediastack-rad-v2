<template>
  <div>
    <header class="topbar">
      <div class="container topbar-inner">
        <router-link to="/" class="topbar-logo">MediaStack-RAD</router-link>
        <span class="topbar-sub">v2 · live</span>

        <nav style="display:flex;gap:2px;margin-left:16px">
          <router-link to="/"        class="nav-link" active-class="nav-link-active" exact>Containers</router-link>
          <router-link to="/builder" class="nav-link" active-class="nav-link-active">Stack builder</router-link>
          <router-link to="/traefik" class="nav-link" active-class="nav-link-active">Traefik</router-link>
          <router-link to="/health"  class="nav-link" active-class="nav-link-active">Stack health</router-link>
        </nav>

        <div class="topbar-spacer" />

        <div v-if="dockerInfo" class="infobar">
          <div class="infobar-item">Docker <span>{{ dockerInfo.docker_version }}</span></div>
          <div class="infobar-item">Running <span>{{ dockerInfo.containers_running }}</span></div>
          <div class="infobar-item">Stopped <span>{{ dockerInfo.containers_stopped }}</span></div>
          <div class="infobar-item">{{ dockerInfo.cpus }} CPU · <span>{{ dockerInfo.memory_gb }} GB</span></div>
        </div>
        <div v-else-if="dockerError" style="font-size:11px;color:var(--danger)">Docker unavailable</div>

        <button class="btn btn-sm" @click="toggleTheme" style="margin-left:8px"
          :title="theme==='dark'?'Switch to light mode':'Switch to dark mode'">
          {{ theme === 'dark' ? '☀ Light' : '☾ Dark' }}
        </button>
      </div>
    </header>

    <main class="container">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { useTheme } from "@/composables/useTheme.js";

const { theme, toggle: toggleTheme } = useTheme();
const dockerInfo  = ref(null);
const dockerError = ref(false);

onMounted(async () => {
  try {
    const res = await fetch("/api/docker/info");
    if (!res.ok) throw new Error();
    dockerInfo.value = await res.json();
  } catch { dockerError.value = true; }
});
</script>
