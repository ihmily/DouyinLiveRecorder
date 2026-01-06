import { createRouter, createWebHistory } from 'vue-router'
import Home from '@/views/Home.vue'
import Player from '@/views/Player.vue'

const routes = [
  {
    path: '/',
    name: 'Home',
    component: Home,
    meta: { title: '录像库' }
  },
  // T044: Legacy route - redirect to new format (handled in Player.vue)
  {
    path: '/player/:sessionId',
    name: 'PlayerLegacy',
    component: Player,
    props: true,
    meta: { title: '播放' }
  },
  // T035: Human-readable URL format
  // T039: Vue Router handles URL encoding/decoding automatically
  {
    path: '/:anchorName/:sessionTimestamp',
    name: 'Player',
    component: Player,
    props: true,
    meta: { title: '播放' }
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// Update document title on navigation
router.beforeEach((to, _from, next) => {
  document.title = `${to.meta.title || 'VOD Player'} - 直播录像回放`
  next()
})

export default router
