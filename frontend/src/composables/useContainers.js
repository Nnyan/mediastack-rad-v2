import { ref, onMounted, onUnmounted } from "vue";
import { API, connectStatsWs } from "./useApi.js";

export function useContainers() {
  const containers = ref([]);
  const liveStats  = ref({});   // { [shortId]: { cpu_percent, memory_mb, ... } }
  const loading    = ref(true);
  const error      = ref(null);

  let pollTimer   = null;
  let wsCleanup   = null;

  async function fetchContainers() {
    try {
      containers.value = await API.containers.list();
      error.value = null;
    } catch (e) {
      error.value = e.message;
    } finally {
      loading.value = false;
    }
  }

  function startStatsWs() {
    wsCleanup = connectStatsWs((data) => {
      liveStats.value = data;
    });
  }

  onMounted(() => {
    fetchContainers();
    pollTimer = setInterval(fetchContainers, 5000);
    startStatsWs();
  });

  onUnmounted(() => {
    clearInterval(pollTimer);
    wsCleanup?.();
  });

  async function start(id) {
    await API.containers.start(id);
    await fetchContainers();
  }

  async function stop(id) {
    await API.containers.stop(id);
    await fetchContainers();
  }

  async function restart(id) {
    await API.containers.restart(id);
    await fetchContainers();
  }

  return { containers, liveStats, loading, error, refresh: fetchContainers, start, stop, restart };
}
