<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import TopTabs from './TopTabs.vue'
import { getConstructionData, updateConstructionData } from '@/service/api'

const router = useRouter()
const currentTab = ref('recommend')
const savedPlaces = ref([])
const expandedFavoriteIds = ref([])
const notificationEnabled = ref({}) // { [placeId]: boolean }
// 類別選擇：'nearby' | 'upcoming'
const selectedCategory = ref({}) // { [placeId]: 'nearby' | 'upcoming' }
const FAVORITES_STORAGE_KEY = 'mapFavorites'
const NOTIFICATION_STORAGE_KEY = 'placeNotifications'
const ROAD_WATCH_KEY = 'roadWatchEnabled'

onMounted(async () => {
  loadSavedPlaces()
  loadNotificationSettings()
  if (typeof window !== 'undefined') {
    window.addEventListener('map-favorites-updated', loadSavedPlaces)
  }
  // 前端輪詢已移除，通知改由 Android 背景任務處理
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

  if (tab === 'announcement') {
    router.push('/announcement')
    return
  }

  if (tab === 'watch') {
    router.push('/watch')
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
    // 預設選擇『附近施工資訊』
    if (!selectedCategory.value[id]) {
      selectedCategory.value[id] = 'nearby'
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
  const wasEnabled = notificationEnabled.value[placeId] || false
  notificationEnabled.value[placeId] = !wasEnabled
  saveNotificationSettings()
  
  const nowEnabled = notificationEnabled.value[placeId]
  
  // 檢查是否有任何收藏啟用通知
  const anyEnabled = Object.values(notificationEnabled.value).some(v => v === true)
  const detectionEnabled = isRoadWatchEnabled()
  
  try {
    if (anyEnabled || detectionEnabled) {
      // 有至少一個收藏啟用通知 -> 啟動背景任務
      const watchPayload = { name: 'watch', data: null }
      if (typeof window !== 'undefined' && window.flutterObject?.postMessage) {
        window.flutterObject.postMessage(JSON.stringify(watchPayload))
        console.log('[Home] Sent watch message to start background task')
      }
    } else {
      // 所有收藏都關閉通知 -> 停止背景任務
      const unwatchPayload = { name: 'unwatch', data: null }
      if (typeof window !== 'undefined' && window.flutterObject?.postMessage) {
        window.flutterObject.postMessage(JSON.stringify(unwatchPayload))
        console.log('[Home] Sent unwatch message to stop background task')
      }
    }
  } catch (e) {
    console.warn('Failed to send watch/unwatch message', e)
  }
  
  // 如果剛開啟，立即檢查一次（前端即時通知）
  if (nowEnabled) {
    checkAndNotifyPlace(placeId, { immediate: true })
  }
}

function isRoadWatchEnabled() {
  if (typeof window === 'undefined') return false
  try {
    return localStorage.getItem(ROAD_WATCH_KEY) === 'true'
  } catch (_) {
    return false
  }
}

function checkAndNotifyPlace(placeId, { immediate = false } = {}) {
  const place = savedPlaces.value.find(p => p.id === placeId)
  if (!place) return
  const recs = Array.isArray(place.recommendations) ? place.recommendations : []
  const constructionCount = recs.filter(r => r?.dsid === 'construction' || (r?.props && (r.props.AP_NAME || r.props.PURP))).length
  if (constructionCount <= 0) return

  // 立即通知（前端層，不需時間間隔判斷）
  try {
    const payload = {
      name: 'notify',
      data: {
        title: `${place.name || '收藏地點'} 附近施工資訊`,
        content: `此收藏 1 公里內有 ${constructionCount} 個施工地點`,
      },
    }
    if (typeof window !== 'undefined' && window.flutterObject?.postMessage) {
      window.flutterObject.postMessage(JSON.stringify(payload))
    }
  } catch (e) {
    console.warn('Failed to send notify message', e)
  }
}

function selectCategoryForPlace(placeId, category) {
  selectedCategory.value[placeId] = category
}

function parsePossibleDate(raw) {
  if (!raw || typeof raw !== 'string') return null
  const cleaned = raw.replace(/\//g, '-').trim()
  const d = new Date(cleaned)
  return isNaN(d.getTime()) ? null : d
}

function getFilteredRecommendations(place) {
  const recs = Array.isArray(place.recommendations) ? place.recommendations : []
  const constructions = recs.filter(r => r?.dsid === 'construction' || (r?.props && (r.props.AP_NAME || r.props.PURP)))
  const category = selectedCategory.value[place.id]
  if (category === 'upcoming') {
    const now = new Date()
    const future = constructions.filter(r => {
      const props = r?.props || {}
      const dateCandidate = parsePossibleDate(props.SDATE || props.START_DATE || props.startDate || props.BEG_DATE)
      if (!dateCandidate) return false
      return dateCandidate.getTime() > now.getTime()
    })
    // 若沒有任何可判斷為未來的施工，回傳空陣列表示『目前沒有未來公告』
    return future
  }
  // nearby
  return constructions
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
                  class="mt-1 inline-block text-sm text-blue-900 transition-transform shrink-0"
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
            <!-- 類別選擇圓形按鈕（雙藍色樣式） -->
            <div class="mb-4 flex items-center gap-3">
              <span class="text-xs font-medium text-gray-600">顯示類型：</span>
              <div class="flex gap-2">
                <button
                  type="button"
                  @click="selectCategoryForPlace(place.id, 'nearby')"
                  :class="[
                    'flex h-10 items-center justify-center rounded-full border-2 px-4 text-xs font-medium transition-all',
                    selectedCategory[place.id] === 'nearby'
                      ? 'border-blue-900 bg-blue-900 text-white shadow-md'
                      : 'border-gray-300 bg-white text-gray-600 hover:border-blue-400'
                  ]"
                >
                  附近施工資訊
                </button>
                <button
                  type="button"
                  @click="selectCategoryForPlace(place.id, 'upcoming')"
                  :class="[
                    'flex h-10 items-center justify-center rounded-full border-2 px-4 text-xs font-medium transition-all',
                    selectedCategory[place.id] === 'upcoming'
                      ? 'border-blue-900 bg-blue-900 text-white shadow-md'
                      : 'border-gray-300 bg-white text-gray-600 hover:border-blue-400'
                  ]"
                >
                  未來施工公告
                </button>
              </div>
            </div>

            <!-- 清單標題 -->
            <div class="mb-2">
              <h3 class="text-sm font-semibold text-gray-800">
                {{ selectedCategory[place.id] === 'upcoming' ? '未來施工公告' : '附近施工資訊' }}
              </h3>
            </div>

            <!-- 施工資訊列表 -->
            <div class="space-y-2">
              <template v-if="getFilteredRecommendations(place).length">
                <div
                  v-for="rec in getFilteredRecommendations(place)"
                  :key="rec.id || rec.name"
                  class="rounded-lg border border-slate-200 bg-white px-3 py-2.5"
                >
                  <div class="text-sm text-gray-800">
                    <div class="font-medium">{{ rec.props?.AP_NAME || rec.name }}</div>
                    <div class="text-xs text-gray-600 mt-0.5">{{ rec.props?.PURP || rec.addr }}</div>
                  </div>
                  <div v-if="typeof rec.dist === 'number' && selectedCategory[place.id] === 'nearby'" class="text-xs text-gray-400 mt-1">
                    距離約 {{ formatDistance(rec.dist) }}
                  </div>
                </div>
              </template>
              <p v-else class="py-3 text-center text-xs text-gray-500">
                {{ selectedCategory[place.id] === 'upcoming' ? '目前沒有未來施工公告' : '1 公里內沒有施工資訊' }}
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
