<template>
  <div class="container-card" @click="$emit('select')">
    <div class="container-card-header">
      <div class="container-card-name">{{ container.name }}</div>
      <StatusBadge :status="container.status" />
      <div style="position:relative" @click.stop>
        <button class="btn btn-sm" style="padding:2px 6px;font-size:10px" @click="showMenu=!showMenu" title="Change category">⋮</button>
        <div v-if="showMenu" style="position:absolute;right:0;top:100%;z-index:50;background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:4px 0;min-width:140px;margin-top:2px">
          <div style="font-size:10px;color:var(--muted);padding:4px 10px;text-transform:uppercase;letter-spacing:0.06em">Move to category</div>
          <button
            v-for="cat in categories" :key="cat"
            style="display:block;width:100%;text-align:left;padding:5px 10px;font-size:11px;background:transparent;border:none;color:var(--text);cursor:pointer"
            @mouseover="e=>e.target.style.background='var(--surface2)'"
            @mouseout="e=>e.target.style.background='transparent'"
            @click="choose(cat)"
          >{{ cat }}</button>
        </div>
      </div>
    </div>

    <div class="container-card-image">{{ container.image }}</div>

    <template v-if="container.status === 'running' && stats">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:6px">
        <div>
          <div class="stat-mini">CPU <span>{{ stats.cpu_percent }}%</span></div>
          <div class="progress-wrap mt-1"><div class="progress-bar progress-cpu" :style="`width:${Math.min(stats.cpu_percent,100)}%`" /></div>
        </div>
        <div>
          <div class="stat-mini">MEM <span>{{ stats.memory_mb }} MB</span></div>
          <div class="progress-wrap mt-1"><div class="progress-bar progress-mem" :style="`width:${memPct}%`" /></div>
        </div>
      </div>
    </template>

    <div class="container-card-footer">
      <span v-for="(hosts,cp) in Object.fromEntries(Object.entries(container.ports).slice(0,3))" :key="cp" class="port-pill">:{{ hosts[0] }}</span>
      <span class="card-id" style="margin-left:auto;color:var(--muted);font-size:10px;font-family:var(--mono)">{{ container.id }}</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from "vue";
import StatusBadge from "./StatusBadge.vue";

const props = defineProps({
  container: Object,
  stats: Object,
  categories: Array,
});
const emit = defineEmits(["select", "recategorize"]);

const showMenu = ref(false);

const memPct = computed(() => {
  if (!props.stats?.memory_limit_mb) return 0;
  return Math.min((props.stats.memory_mb / props.stats.memory_limit_mb) * 100, 100).toFixed(1);
});

function choose(cat) {
  showMenu.value = false;
  emit("recategorize", cat);
}
</script>
