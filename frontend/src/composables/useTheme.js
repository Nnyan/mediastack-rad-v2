import { ref, watch } from "vue";

const STORAGE_KEY = "msr-theme";
const theme = ref(localStorage.getItem(STORAGE_KEY) || "dark");

watch(theme, (t) => {
  localStorage.setItem(STORAGE_KEY, t);
  document.documentElement.setAttribute("data-theme", t);
});

document.documentElement.setAttribute("data-theme", theme.value);

export function useTheme() {
  function toggle() {
    theme.value = theme.value === "dark" ? "light" : "dark";
  }
  return { theme, toggle };
}
