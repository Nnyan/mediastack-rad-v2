<template>
  <span class="badge" :class="`badge-${normalised}`">{{ status }}</span>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({ status: { type: String, default: "unknown" } });

const normalised = computed(() => {
  const s = props.status?.toLowerCase() ?? "";
  if (["running"].includes(s))    return "running";
  if (["exited", "dead"].includes(s)) return "exited";
  if (["paused"].includes(s))     return "paused";
  if (["restarting"].includes(s)) return "restarting";
  if (["created"].includes(s))    return "created";
  return "error";
});
</script>
