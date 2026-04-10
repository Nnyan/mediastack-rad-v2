<template>
  <div>
    <header class="topbar">
      <div class="container topbar-inner">
        <router-link to="/" class="topbar-logo">MediaStack-RAD</router-link>
        <span class="topbar-sub">v2 · live</span>
        <div class="topbar-spacer" />
        <div v-if="dockerInfo" class="infobar">
          <div class="infobar-item">Docker <span>{{ dockerInfo.docker_version }}</span></div>
          <div class="infobar-item">Running <span>{{ dockerInfo.containers_running }}</span></div>
          <div class="infobar-item">Stopped <span>{{ dockerInfo.containers_stopped }}</span></div>
          <div class="infobar-item">Images <span>{{ dockerInfo.images }}</span></div>
          <div class="infobar-item">{{ dockerInfo.cpus }} CPU · <span>{{ dockerInfo.memory_gb }} GB</span></div>
        </div>
        <div v-else-if="dockerError" class="alert alert-error" style="padding:0.3rem 0.75rem;font-size:0.75rem;">
          Docker unavailable
        </div>
      </div>
    </header>

    <main class="container">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";

const dockerInfo = ref(null);
const dockerError = ref(false);

onMounted(async () => {
  try {
    const res = await fetch("/api/docker/info");
    if (!res.ok) throw new Error();
    dockerInfo.value = await res.json();
  } catch {
    dockerError.value = true;
  }
});
</script>
