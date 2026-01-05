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
  {
    path: '/player/:sessionId',
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
