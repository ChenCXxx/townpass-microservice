<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import TopTabs from './TopTabs.vue'
import { getConstructionData } from '@/service/api'

const router = useRouter()
const currentTab = ref('watch')
const trackingEnabled = ref(false)
const statusText = ref('尚未啟動')
const statusDetail = ref('開啟後會在背景持續運作，並於接近施工點時語音提醒。')
const currentLocation = ref(null) // { lon, lat }
const lastUpdate = ref(null)
const nearbySites = ref([])
const loading = ref(false)
const error = ref('')
const constructionFeatures = ref([])

const ROAD_WATCH_KEY = 'roadWatchEnabled'
const LOCATION_POLL_MS = 3000
const NEARBY_RADIUS_M = 1500
const MAX_NEARBY_COUNT = 5

let pollTimer = null
let flutterMsgHandler = null

onMounted(async () => {
  await loadConstructionData()
  attachFlutterListener()
  if (getStoredWatchFlag()) {
    startTracking({ silentStatus: true })
  }
})

onBeforeUnmount(() => {
  stopPolling()
  detachFlutterListener()
})

function selectTab(tab) {
  if (tab === 'map') {
    router.push('/map')
  } else if (tab === 'announcement') {
    router.push('/announcement')
  } else if (tab === 'recommend') {
    router.push('/')
  } else if (tab === 'watch') {
    currentTab.value = 'watch'
  }
}

async function loadConstructionData() {
  try {
    loading.value = true
    error.value = ''
    const data = await getConstructionData()
    constructionFeatures.value = Array.isArray(data?.features) ? data.features : []
    if (currentLocation.value) {
      updateNearbySites()
    }
  } catch (e) {
    error.value = e?.message || '無法取得施工資料'
  } finally {
    loading.value = false
  }
}

function startTracking({ silentStatus = false } = {}) {
  if (!trackingEnabled.value) {
    trackingEnabled.value = true
    setStoredWatchFlag(true)
    statusText.value = '偵測中'
    statusDetail.value = '可切換至其他 App，背景仍會語音提醒施工點。'
  } else if (!silentStatus) {
    statusText.value = '偵測中'
  }

  sendFlutterCommand('watch')
  ensurePolling()
}

function stopTracking() {
  trackingEnabled.value = false
  setStoredWatchFlag(false)
  statusText.value = '已停止'
  statusDetail.value = '若要持續偵測，請重新點擊啟動。'
  stopPolling()

  if (!hasFavoriteNotificationEnabled()) {
    sendFlutterCommand('unwatch')
  }
}

function ensurePolling() {
  requestLocationFromFlutter()
  if (pollTimer) return
  pollTimer = setInterval(requestLocationFromFlutter, LOCATION_POLL_MS)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function attachFlutterListener() {
  if (typeof window === 'undefined') return
  const handler = (event) => handleIncomingMessage(event?.data ?? event)
  if (window.flutterObject && typeof window.flutterObject.addEventListener === 'function') {
    flutterMsgHandler = handler
    try { window.flutterObject.addEventListener('message', flutterMsgHandler) } catch (_) {}
  } else {
    flutterMsgHandler = handler
    window.addEventListener('message', flutterMsgHandler)
  }
  window.receiveLocationFromFlutter = (msg) => handleIncomingMessage(msg)
}

function detachFlutterListener() {
  if (typeof window === 'undefined' || !flutterMsgHandler) return
  if (!flutterMsgHandler) return
  if (window.flutterObject && typeof window.flutterObject.removeEventListener === 'function') {
    try { window.flutterObject.removeEventListener('message', flutterMsgHandler) } catch (_) {}
  } else {
    window.removeEventListener('message', flutterMsgHandler)
  }
  flutterMsgHandler = null
  try { delete window.receiveLocationFromFlutter } catch (_) {}
}

function handleIncomingMessage(raw) {
  try {
    const msg = typeof raw === 'string' ? JSON.parse(raw) : raw
    const payload = msg?.data ?? msg
    const name = msg?.name ?? null
    if (name && name !== 'location') return
    const lat = payload?.latitude ?? payload?.lat ?? payload?.coords?.latitude
    const lon = payload?.longitude ?? payload?.lng ?? payload?.lon ?? payload?.coords?.longitude
    if (typeof lat === 'number' && typeof lon === 'number') {
      updateCurrentLocation(lon, lat)
    }
  } catch (err) {
    console.warn('Invalid location message', err)
  }
}

function updateCurrentLocation(lon, lat) {
  currentLocation.value = { lon, lat }
  lastUpdate.value = new Date()
  if (trackingEnabled.value) {
    statusText.value = '偵測中'
    statusDetail.value = '背景語音提醒已啟動'
  }
  updateNearbySites()
}

function updateNearbySites() {
  if (!currentLocation.value || !Array.isArray(constructionFeatures.value)) {
    nearbySites.value = []
    return
  }

  const { lon, lat } = currentLocation.value
  const points = []

  for (const feature of constructionFeatures.value) {
    const coords = feature?.geometry?.coordinates
    if (!Array.isArray(coords) || coords.length < 2) continue
    const conLon = Number(coords[0])
    const conLat = Number(coords[1])
    if (Number.isNaN(conLon) || Number.isNaN(conLat)) continue
    const distance = distM(lon, lat, conLon, conLat)
    if (distance > NEARBY_RADIUS_M) continue
    const props = feature?.properties ?? {}
    points.push({
      id: feature?.id ?? props?.AC_NO ?? `${conLat},${conLon}`,
      name: props?.DIGADD || props?.AP_ADDR || props?.['場地名稱'] || props?.PURP || '施工地點',
      company: props?.AP_NAME || props?.TC_NA || props?.ROAD || props?.ROAD_NAME || '',
      distance,
    })
  }

  points.sort((a, b) => a.distance - b.distance)
  nearbySites.value = points.slice(0, MAX_NEARBY_COUNT)
}

function requestLocationFromFlutter() {
  if (typeof window === 'undefined') return false
  try {
    if (window.flutterObject?.postMessage) {
      window.flutterObject.postMessage(JSON.stringify({ name: 'location' }))
      return true
    }
  } catch (_) {}
  return false
}

function sendFlutterCommand(name, data = null) {
  if (typeof window === 'undefined') return false
  try {
    if (!window.flutterObject?.postMessage) return false
    window.flutterObject.postMessage(JSON.stringify({ name, data }))
    return true
  } catch (err) {
    console.warn(`Failed to send ${name} message`, err)
    return false
  }
}

function hasFavoriteNotificationEnabled() {
  if (typeof window === 'undefined') return false
  try {
    const raw = localStorage.getItem('placeNotifications')
    if (!raw) return false
    const parsed = JSON.parse(raw)
    return Object.values(parsed || {}).some(Boolean)
  } catch (_) {
    return false
  }
}

function getStoredWatchFlag() {
  if (typeof window === 'undefined') return false
  try {
    return localStorage.getItem(ROAD_WATCH_KEY) === 'true'
  } catch (_) {
    return false
  }
}

function setStoredWatchFlag(enabled) {
  if (typeof window === 'undefined') return
  try {
    localStorage.setItem(ROAD_WATCH_KEY, enabled ? 'true' : 'false')
  } catch (_) {}
}

function handleToggle() {
  if (trackingEnabled.value) {
    stopTracking()
  } else {
    startTracking()
  }
}

function distM(lon1, lat1, lon2, lat2) {
  const toRad = (d) => d * Math.PI / 180
  const R = 6371000
  const dLat = toRad(lat2 - lat1)
  const dLon = toRad(lon2 - lon1)
  const a = Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) *
    Math.sin(dLon / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(a))
}

const locationText = computed(() => {
  if (!currentLocation.value) return '尚未取得定位'
  const { lon, lat } = currentLocation.value
  return `${lat.toFixed(5)}, ${lon.toFixed(5)}`
})

const lastUpdateText = computed(() => {
  if (!lastUpdate.value) return '—'
  try {
    return lastUpdate.value.toLocaleTimeString('zh-TW', { hour12: false })
  } catch {
    return lastUpdate.value.toISOString()
  }
})

function formatDistance(meters) {
  if (meters >= 1000) {
    return `${(meters / 1000).toFixed(1)} 公里`
  }
  return `${Math.round(meters)} 公尺`
}
</script>

<template>
  <div class="bg-white min-h-screen">
    <section class="mx-auto flex h-dvh w-full max-w-[720px] flex-col px-4 pt-3 pb-5">
      <TopTabs :active="currentTab" @select="selectTab" />

      <div class="mt-4 flex flex-col gap-4">
        <div class="rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p class="text-sm text-slate-500">路上偵測狀態</p>
              <p class="text-xl font-semibold text-slate-900">{{ statusText }}</p>
              <p class="text-xs text-slate-500">{{ statusDetail }}</p>
            </div>
            <button
              class="w-full rounded-full px-4 py-2 text-sm font-semibold text-white sm:w-auto"
              :class="trackingEnabled ? 'bg-rose-500 hover:bg-rose-600' : 'bg-blue-900 hover:bg-blue-800'"
              @click="handleToggle"
            >
              {{ trackingEnabled ? '停止偵測' : '開始偵測' }}
            </button>
          </div>
          <p class="mt-3 text-xs text-slate-500">
            開啟後即可切換至 Google 導航等其他 App，本服務會留在背景語音提醒。
          </p>
        </div>

        <div class="rounded-2xl border border-slate-200 bg-white p-4">
          <div class="flex items-center justify-between">
            <div>
              <p class="text-sm text-slate-500">目前座標</p>
              <p class="text-base font-medium text-slate-900">{{ locationText }}</p>
            </div>
            <div class="text-right">
              <p class="text-xs text-slate-400">最後更新</p>
              <p class="text-sm text-slate-600">{{ lastUpdateText }}</p>
            </div>
          </div>

          <div class="mt-4 flex flex-col gap-2 text-sm text-slate-500 sm:flex-row sm:items-center sm:justify-between">
            <span class="truncate">資料來源：台北市道路挖掘管理系統</span>
            <button
              class="text-blue-900 underline decoration-dashed underline-offset-4"
              @click="loadConstructionData"
            >
              重新整理
            </button>
          </div>
        </div>

        <div class="rounded-2xl border border-slate-200 bg-white p-4">
          <div class="flex items-center justify-between">
            <h3 class="text-base font-semibold text-slate-900">附近施工地點</h3>
            <span class="text-sm text-slate-500">{{ nearbySites.length }} 個</span>
          </div>

          <div v-if="loading" class="py-8 text-center text-sm text-slate-500">
            資料載入中...
          </div>
          <div v-else-if="error" class="py-8 text-center text-sm text-rose-500">
            {{ error }}
          </div>
          <div v-else-if="!currentLocation" class="py-8 text-center text-sm text-slate-500">
            等待取得定位...
          </div>
          <div v-else-if="nearbySites.length === 0" class="py-8 text-center text-sm text-slate-500">
            目前 1.5 公里內沒有施工點
          </div>
          <ul v-else class="mt-3 divide-y divide-slate-100">
            <li
              v-for="site in nearbySites"
              :key="site.id"
              class="py-3"
            >
              <div class="flex items-center justify-between gap-2 text-sm">
                <span class="min-w-0 flex-1 truncate font-semibold text-slate-900">{{ site.name }}</span>
                <span class="shrink-0 text-rose-500 font-semibold">{{ formatDistance(site.distance) }}</span>
              </div>
              <p v-if="site.company" class="mt-1 text-xs text-slate-500 line-clamp-2">{{ site.company }}</p>
            </li>
          </ul>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
</style>
