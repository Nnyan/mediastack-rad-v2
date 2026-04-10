import { ref, onMounted } from "vue";
import { API } from "./useApi.js";

const assignments = ref({});
const enabled = ref(true);

export function useCategories() {
  async function load() {
    try {
      const data = await API.get("/categories");
      assignments.value = data.assignments || {};
      enabled.value = data.enabled !== false;
    } catch { /* use defaults */ }
  }

  async function save() {
    try {
      await API.post("/categories", { assignments: assignments.value, enabled: enabled.value });
    } catch (e) {
      console.error("Failed to save categories", e);
    }
  }

  function setCategory(containerName, category) {
    assignments.value = { ...assignments.value, [containerName]: category };
    save();
  }

  function getCategory(containerName, defaultCategory) {
    return assignments.value[containerName] || defaultCategory;
  }

  function toggleEnabled() {
    enabled.value = !enabled.value;
    save();
  }

  onMounted(load);

  return { assignments, enabled, setCategory, getCategory, toggleEnabled, reload: load };
}
