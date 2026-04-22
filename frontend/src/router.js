import { createRouter, createWebHistory } from 'vue-router'

// Import all views eagerly — they're small Vue components and the bundle
// size difference is negligible. Eager loading eliminates the "click and
// wait with no feedback" problem caused by lazy chunk loading.
import Containers from './views/Containers.vue'
import StackBuilder from './views/StackBuilder.vue'
import Traefik from './views/Traefik.vue'
import Health from './views/Health.vue'
import Settings from './views/Settings.vue'

const routes = [
  { path: '/', redirect: '/containers' },
  { path: '/containers',   name: 'containers',    component: Containers },
  { path: '/stack-builder',name: 'stack-builder', component: StackBuilder },
  { path: '/traefik',      name: 'traefik',        component: Traefik },
  { path: '/health',       name: 'health',         component: Health },
  { path: '/settings',     name: 'settings',       component: Settings },
]

export default createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})
