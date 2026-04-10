import { createApp } from "vue";
import { createRouter, createWebHistory } from "vue-router";
import App from "./App.vue";
import Dashboard from "./components/Dashboard.vue";
import ContainerDetail from "./components/ContainerDetail.vue";
import StackHealth from "./components/StackHealth.vue";
import TraefikManager from "./components/TraefikManager.vue";
import "./style.css";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/",              component: Dashboard },
    { path: "/container/:id", component: ContainerDetail },
    { path: "/health",        component: StackHealth },
    { path: "/traefik",       component: TraefikManager },
  ],
});

createApp(App).use(router).mount("#app");
