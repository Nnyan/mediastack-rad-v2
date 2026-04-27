import { createRouter, createWebHistory } from 'vue-router'

// Import all views eagerly — they're small Vue components and the bundle
// size difference is negligible. Eager loading eliminates the "click and
// wait with no feedback" problem caused by lazy chunk loading.
import StackBuilder from './views/StackBuilder.vue'
import Todo from './views/Todo.vue'
import Traefik from './views/Traefik.vue'
import Vpn from './views/Vpn.vue'
import Settings from './views/Settings.vue'

const routes = [
  { path: '/', redirect: '/stack-builder' },
  { path: '/stack-builder',name: 'stack-builder', component: StackBuilder },
  { path: '/todo',         name: 'todo',           component: Todo },
  { path: '/traefik',      name: 'traefik',        component: Traefik },
  { path: '/vpn',          name: 'vpn',            component: Vpn },
  { path: '/settings',     name: 'settings',       component: Settings },
]

export default createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})
