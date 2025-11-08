import { createRouter, createWebHistory } from 'vue-router'

// 懶載入頁面
const Home = () => import('@/components/Home.vue')
const About = () => import('@/components/About.vue')
const MapView = () => import('@/components/MapView.vue')
const AnnouncementView = () => import('@/views/AnnouncementView.vue')
const RoadWatch = () => import('@/components/RoadWatch.vue')

const router = createRouter({
  history: createWebHistory(),   // 若無法設定伺服器 rewrite，改用 createWebHashHistory()
  routes: [
    { path: '/', component: Home },
    { path: '/about', component: About },
    { path: '/map', component: MapView },
    { path: '/announcement', component: AnnouncementView },
    { path: '/watch', component: RoadWatch },
    // 404
    { path: '/:pathMatch(.*)*', component: { template: '<h2>Not Found</h2>' } }
  ],
  scrollBehavior() { return { top: 0 } }
})

export default router
