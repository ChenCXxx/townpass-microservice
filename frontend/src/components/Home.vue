<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import TopTabs from './TopTabs.vue'
import { hello, echo, listUsers, createUser, listTestRecords, createTestRecord, getConstructionData, updateConstructionData } from '@/service/api'

const hi = ref(null)          // GET /api/hello 回傳
const echoMsg = ref('ping')   // POST /api/echo 輸入
const echoResp = ref(null)    // POST /api/echo 回傳

const users = ref([])         // GET /api/users 回傳
const newName = ref('Alice')  // POST /api/users 的 name

const tests = ref([])         // GET /api/test_records 回傳
const newTestTitle = ref('Sample title')
const newTestDescription = ref('A short description')

const constructionData = ref(null)  // GET /api/construction/geojson 回傳
const constructionUpdateStatus = ref(null)  // GET /api/construction/update 回傳
const constructionLoading = ref(false)

const loading = ref(false)
const error = ref('')
const router = useRouter()
const currentTab = ref('recommend')
const savedPlaces = ref([])
const expandedFavoriteIds = ref([])
const notificationEnabled = ref({}) // { [placeId]: boolean }
const selectedCategory = ref({}) // { [placeId]: 'attraction' | 'construction' }
const FAVORITES_STORAGE_KEY = 'mapFavorites'
const NOTIFICATION_STORAGE_KEY = 'placeNotifications'

onMounted(async () => {
  try {
    loading.value = true
    error.value = ''
    hi.value = await hello()
    users.value = await listUsers()
    tests.value = await listTestRecords()
    await loadConstructionData()
  } catch (e) {
    error.value = e?.message || String(e)
  } finally {
    loading.value = false
  }
  loadSavedPlaces()
  loadNotificationSettings()
  if (typeof window !== 'undefined') {
    window.addEventListener('map-favorites-updated', loadSavedPlaces)
  }
})

onBeforeUnmount(() => {
  if (typeof window !== 'undefined') {
    window.removeEventListener('map-favorites-updated', loadSavedPlaces)
  }
})

function selectTab(tab) {
  if (tab === 'recommend') {
    currentTab.value = 'recommend'
    if (router.currentRoute.value.path !== '/') {
      router.push('/')
    }
    return
  }

  currentTab.value = 'map'
  if (router.currentRoute.value.path !== '/map') {
    router.push('/map')
  }
}

function readSavedPlaces() {
  if (typeof window === 'undefined') return []
  try {
    const raw = localStorage.getItem(FAVORITES_STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch (_) {
    return []
  }
}

function loadSavedPlaces() {
  const list = readSavedPlaces().map((item) => ({
    ...item,
    recommendations: Array.isArray(item?.recommendations) ? item.recommendations : [],
  }))
  list.sort((a, b) => {
    const da = a?.addedAt ? Date.parse(a.addedAt) : 0
    const db = b?.addedAt ? Date.parse(b.addedAt) : 0
    return db - da
  })
  savedPlaces.value = list
  expandedFavoriteIds.value = expandedFavoriteIds.value.filter((id) => list.some((place) => place.id === id))
}

function saveFavorites(list) {
  if (typeof window === 'undefined') return
  localStorage.setItem(FAVORITES_STORAGE_KEY, JSON.stringify(list))
  window.dispatchEvent(new CustomEvent('map-favorites-updated'))
}

function loadNotificationSettings() {
  if (typeof window === 'undefined') return
  try {
    const raw = localStorage.getItem(NOTIFICATION_STORAGE_KEY)
    if (raw) {
      notificationEnabled.value = JSON.parse(raw)
    }
  } catch (_) {}
}

function saveNotificationSettings() {
  if (typeof window === 'undefined') return
  localStorage.setItem(NOTIFICATION_STORAGE_KEY, JSON.stringify(notificationEnabled.value))
}

function isFavoriteExpanded(id) {
  return expandedFavoriteIds.value.includes(id)
}

function toggleFavoriteDetails(id) {
  if (isFavoriteExpanded(id)) {
    expandedFavoriteIds.value = expandedFavoriteIds.value.filter((item) => item !== id)
  } else {
    expandedFavoriteIds.value = [...expandedFavoriteIds.value, id]
    // 預設選擇景點
    if (!selectedCategory.value[id]) {
      selectedCategory.value[id] = 'attraction'
    }
  }
}

function removeFavorite(id) {
  const next = savedPlaces.value.filter((place) => place.id !== id)
  savedPlaces.value = next
  expandedFavoriteIds.value = expandedFavoriteIds.value.filter((item) => item !== id)
  delete notificationEnabled.value[id]
  delete selectedCategory.value[id]
  saveFavorites(next)
  saveNotificationSettings()
}

function toggleNotification(placeId) {
  notificationEnabled.value[placeId] = !notificationEnabled.value[placeId]
  saveNotificationSettings()
  const place = savedPlaces.value.find(p => p.id === placeId)
  const enabled = notificationEnabled.value[placeId]
  // 發送 watch/unwatch 訊息給 Flutter，啟用或停止監控附近施工地點
  try {
    const payload = enabled ? {
      name: 'watch',
      data: {
        id: placeId,
        name: place?.name || '未命名地點',
        lon: place?.lon,
        lat: place?.lat,
      },
    } : {
      name: 'unwatch',
      data: {
        id: placeId,
      },
    }
    if (typeof window !== 'undefined' && window.flutterObject?.postMessage) {
      window.flutterObject.postMessage(JSON.stringify(payload))
    }
  } catch (_) {}
}

function selectCategoryForPlace(placeId, category) {
  selectedCategory.value[placeId] = category
}

function getFilteredRecommendations(place) {
  const recs = Array.isArray(place.recommendations) ? place.recommendations : []
  const category = selectedCategory.value[place.id] || 'attraction'
  if (category === 'construction') {
    // 施工資訊：依 dsid 或 props 判斷
    return recs.filter(r => r?.dsid === 'construction' || (r?.props && (r.props.AP_NAME || r.props.PURP)))
  }
  // 景點：僅 attraction
  return recs.filter(r => r?.dsid === 'attraction' || (!r?.dsid && !r?.props))
}

function formatFavoriteDate(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  try {
    return date.toLocaleString('zh-TW', { hour12: false })
  } catch (_) {
    return date.toLocaleString()
  }
}

function formatDistance(meters) {
  if (typeof meters !== 'number' || Number.isNaN(meters)) return ''
  if (meters >= 1000) {
    const km = meters / 1000
    return `${km >= 10 ? km.toFixed(0) : km.toFixed(1)} 公里`
  }
  return `${Math.round(meters)} 公尺`
}

async function loadConstructionData() {
  try {
    constructionLoading.value = true
    error.value = ''
    constructionData.value = await getConstructionData()
  } catch (e) {
    error.value = e?.message || String(e)
    constructionData.value = null
  } finally {
    constructionLoading.value = false
  }
}

async function triggerConstructionUpdate() {
  try {
    constructionLoading.value = true
    error.value = ''
    constructionUpdateStatus.value = await updateConstructionData()
    // 更新後重新載入數據
    await loadConstructionData()
  } catch (e) {
    error.value = e?.message || String(e)
    constructionUpdateStatus.value = null
  } finally {
    constructionLoading.value = false
  }
}
</script>

<template>
  <section class="mx-auto max-w-[720px] px-4 pt-3 pb-5">
    <TopTabs :active="currentTab" @select="selectTab" />

    <div v-if="currentTab === 'recommend'" class="mt-3">
      <!-- 收藏地點列表 - 直接就是整個介面 -->
      <div class="mb-3 flex items-center justify-between">
        <h2 class="text-lg font-semibold text-gray-800">我的收藏</h2>
        <span class="text-sm text-gray-500">共 {{ savedPlaces.length }} 個地點</span>
      </div>

      <p v-if="savedPlaces.length === 0" class="text-center py-12 text-gray-500">
        目前尚未收藏地點<br />
        <span class="text-sm">前往地圖搜尋地點並加入收藏</span>
      </p>

      <ul v-else class="space-y-3">
        <li
          v-for="place in savedPlaces"
          :key="place.id"
          class="rounded-lg border border-slate-200 bg-white shadow-sm overflow-hidden"
        >
          <!-- 地點標題列 -->
          <div class="flex items-start gap-3 px-4 py-3">
            <button
              type="button"
              class="flex-1 text-left"
              @click="toggleFavoriteDetails(place.id)"
            >
              <div class="flex items-start justify-between gap-2">
                <div class="flex-1">
                  <div class="text-sm font-semibold text-gray-800">{{ place.name }}</div>
                  <div v-if="place.address" class="mt-0.5 text-xs text-gray-500">{{ place.address }}</div>
                  <div v-else-if="place.addr" class="mt-0.5 text-xs text-gray-500">{{ place.addr }}</div>
                </div>
                <span
                  class="mt-1 inline-block text-sm text-blue-500 transition-transform shrink-0"
                  :class="isFavoriteExpanded(place.id) ? 'rotate-180' : 'rotate-0'"
                >▼</span>
              </div>
            </button>

            <!-- 鈴鐺通知按鈕 -->
            <button
              type="button"
              @click.stop="toggleNotification(place.id)"
              :class="[
                'flex h-9 w-9 items-center justify-center rounded-full border transition-colors shrink-0',
                notificationEnabled[place.id]
                  ? 'border-amber-400 bg-amber-50 text-amber-600'
                  : 'border-gray-300 bg-gray-50 text-gray-400 hover:bg-gray-100'
              ]"
              :title="notificationEnabled[place.id] ? '關閉通知' : '開啟通知'"
            >
              <svg class="h-5 w-5" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 2C11.172 2 10.5 2.672 10.5 3.5V4.1C8.53 4.56 7 6.28 7 8.5V14L5.71 15.29C5.08 15.92 5.52 17 6.41 17H17.59C18.48 17 18.92 15.92 18.29 15.29L17 14V8.5C17 6.28 15.47 4.56 13.5 4.1V3.5C13.5 2.672 12.828 2 12 2ZM10 19C10 20.1 10.9 21 12 21C13.1 21 14 20.1 14 19H10Z"></path>
              </svg>
            </button>
          </div>

          <!-- 底部操作列 -->
          <div class="flex items-center justify-between border-t border-slate-100 px-4 py-2 bg-slate-50/50">
            <span class="text-xs text-gray-500">
              收藏於 {{ formatFavoriteDate(place.addedAt) }}
            </span>
            <button
              type="button"
              class="text-xs text-red-500 hover:underline"
              @click.stop="removeFavorite(place.id)"
            >
              取消收藏
            </button>
          </div>

          <!-- 展開的詳細內容 -->
          <div
            v-if="isFavoriteExpanded(place.id)"
            class="border-t border-slate-200 bg-slate-50 px-4 py-4"
          >
            <!-- 類別選擇圓形按鈕 -->
            <div class="mb-4 flex items-center gap-3">
              <span class="text-xs font-medium text-gray-600">附近資訊：</span>
              <div class="flex gap-2">
                <button
                  type="button"
                  @click="selectCategoryForPlace(place.id, 'attraction')"
                  :class="[
                    'flex h-10 items-center justify-center rounded-full border-2 px-4 text-xs font-medium transition-all',
                    selectedCategory[place.id] === 'attraction'
                      ? 'border-sky-500 bg-sky-500 text-white shadow-md'
                      : 'border-gray-300 bg-white text-gray-600 hover:border-sky-300'
                  ]"
                >
                  景點
                </button>
                <button
                  type="button"
                  @click="selectCategoryForPlace(place.id, 'construction')"
                  :class="[
                    'flex h-10 items-center justify-center rounded-full border-2 px-4 text-xs font-medium transition-all',
                    selectedCategory[place.id] === 'construction'
                      ? 'border-orange-500 bg-orange-500 text-white shadow-md'
                      : 'border-gray-300 bg-white text-gray-600 hover:border-orange-300'
                  ]"
                >
                  施工資訊
                </button>
              </div>
            </div>

            <!-- 附近推薦列表 -->
            <div class="space-y-2">
              <template v-if="getFilteredRecommendations(place).length">
                <div
                  v-for="rec in getFilteredRecommendations(place)"
                  :key="rec.id || rec.name"
                  class="rounded-lg border border-slate-200 bg-white px-3 py-2.5"
                >
                  <div v-if="selectedCategory[place.id] === 'construction'" class="text-sm text-gray-800">
                    <div class="font-medium">{{ rec.props?.AP_NAME || rec.name }}</div>
                    <div class="text-xs text-gray-600 mt-0.5">{{ rec.props?.PURP || rec.addr }}</div>
                  </div>
                  <div v-else class="font-medium text-sm text-gray-800">{{ rec.name }}</div>
                  <div v-if="selectedCategory[place.id] !== 'construction' && rec.addr" class="text-xs text-gray-500 mt-1">{{ rec.addr }}</div>
                  <div v-if="typeof rec.dist === 'number'" class="text-xs text-gray-400 mt-1">
                    距離約 {{ formatDistance(rec.dist) }}
                  </div>
                </div>
              </template>
              <p v-else class="text-sm text-gray-500 text-center py-4">
                附近暫無{{ selectedCategory[place.id] === 'construction' ? '施工' : '景點' }}資訊
              </p>
            </div>
          </div>
        </li>
      </ul>
    </div>
  </section>
</template>

<style scoped>
</style>
