import { createRouter, createWebHistory } from 'vue-router'

// Lazy-load views so the initial bundle is small. Each view becomes
// its own chunk that loads only when the user navigates to it.
const routes = [
  { path: '/', redirect: '/containers' },
  {
    path: '/containers',
    name: 'containers',
    component: () => import('./views/Containers.vue'),
  },
  {
    path: '/stack-builder',
    name: 'stack-builder',
    component: () => import('./views/StackBuilder.vue'),
  },
  {
    path: '/traefik',
    name: 'traefik',
    component: () => import('./views/Traefik.vue'),
  },
  {
    path: '/health',
    name: 'health',
    component: () => import('./views/Health.vue'),
  },
  {
    path: '/checklist',
    name: 'checklist',
    component: () => import('./views/Checklist.vue'),
  },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
