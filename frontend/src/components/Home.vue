<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import TopTabs from './TopTabs.vue'
import { getConstructionData, updateConstructionData, getConstructionNotices, getFavorites, updateFavorite, deleteFavorite } from '@/service/api'

const router = useRouter()
const currentTab = ref('recommend')
const savedPlaces = ref([])
const expandedFavoriteIds = ref([])
const notificationEnabled = ref({}) // { [placeId]: boolean }
// 類別選擇：'nearby' | 'upcoming'
const selectedCategory = ref({}) // { [placeId]: 'nearby' | 'upcoming' }
const NOTIFICATION_STORAGE_KEY = 'placeNotifications'
const constructionNotices = ref([]) // 施工公告資料
const loadingNotices = ref(false)
const loadingFavorites = ref(false)
const userId = ref(null) // 從 Flutter 獲取的用戶 ID
const ROAD_NOTICE_DISTANCE_M = 15
const ROUTE_NOTICE_DISTANCE_M = 50

const favoriteTypeBadges = {
  place: 'bg-emerald-100 text-emerald-700',
  road: 'bg-sky-100 text-sky-700',
  route: 'bg-violet-100 text-violet-700',
}

function normalizeFavorite(raw) {
  if (!raw || typeof raw !== 'object') return null
  const type = raw.type === 'road' ? 'road' : raw.type === 'route' ? 'route' : 'place'
  const normalized = {
    ...raw,
    type,
    recommendations: Array.isArray(raw?.recommendations) ? raw.recommendations : [],
  }
  if (type === 'road') {
    normalized.roadDistanceThreshold = typeof raw.road_distance_threshold === 'number'
      ? raw.road_distance_threshold
      : (typeof raw.roadDistanceThreshold === 'number' ? raw.roadDistanceThreshold : ROAD_NOTICE_DISTANCE_M)
    normalized.roadName = raw.road_name || raw.roadName
    normalized.roadSearchName = raw.road_search_name || raw.roadSearchName
    normalized.roadOsmids = raw.road_osmids || raw.roadOsmids
    if (!normalized.address) {
      const roadName = normalized.roadName || raw.name || '道路'
      normalized.address = `${roadName} 道路`
    }
  } else if (type === 'route') {
    normalized.routeDistanceThreshold = typeof raw.route_distance_threshold === 'number'
      ? raw.route_distance_threshold
      : (typeof raw.routeDistanceThreshold === 'number' ? raw.routeDistanceThreshold : ROUTE_NOTICE_DISTANCE_M)
    normalized.routeStart = raw.route_start || raw.routeStart || raw.startLabel || raw.startInput || ''
    normalized.routeEnd = raw.route_end || raw.routeEnd || raw.endLabel || raw.endInput || ''
    normalized.routeStartCoords = raw.route_start_coords || raw.routeStartCoords
    normalized.routeEndCoords = raw.route_end_coords || raw.routeEndCoords
    if (!normalized.name) {
      const startName = normalized.routeStart || '起點'
      const endName = normalized.routeEnd || '終點'
      normalized.name = `${startName} → ${endName}`
    }
    if (!normalized.address) {
      normalized.address = normalized.name
    }
  } else if (type === 'place') {
    // 從 place_data 恢復地點信息
    // 但保留數據庫的原始 id（數字），不要被 place_data.id（可能是坐標字符串）覆蓋
    const dbId = normalized.id // 保存數據庫的 id
    if (raw.place_data) {
      const { id: placeDataId, ...placeDataWithoutId } = raw.place_data
      Object.assign(normalized, placeDataWithoutId)
    }
    // 確保使用數據庫的 id
    if (dbId !== undefined) {
      normalized.id = dbId
    }
  }
  // 從後端字段映射到前端字段
  if (raw.added_at) normalized.addedAt = raw.added_at
  if (raw.notification_enabled !== undefined) normalized.notificationEnabled = raw.notification_enabled
  if (raw.distance_threshold !== undefined) normalized.distanceThreshold = raw.distance_threshold
  return normalized
}

// 測試用的預設 user_id（當沒有 Flutter 環境時使用）
const DEFAULT_TEST_USER_ID = '7f3562f4-bb3f-4ec7-89b9-da3b4b5ff250'

// 從 Flutter 獲取 user_id (UUID 字符串)
async function getUserIdFromFlutter() {
  return new Promise((resolve) => {
    if (typeof window === 'undefined') {
      resolve(DEFAULT_TEST_USER_ID) // 在非瀏覽器環境也返回預設值
      return
    }
    
    let resolved = false // 防止重複 resolve
    
    const doResolve = (value) => {
      if (!resolved) {
        resolved = true
        resolve(value)
      }
    }
    
    // 嘗試從 Flutter 獲取 user_id
    const requestUserId = () => {
      try {
        if (window.flutterObject?.postMessage) {
          console.log('📤 Requesting user_id from Flutter...')
          window.flutterObject.postMessage(JSON.stringify({ name: 'get_user_id' }))
        } else {
          console.warn('⚠️ window.flutterObject.postMessage is not available')
        }
      } catch (e) {
        console.warn('❌ Failed to request user_id from Flutter', e)
      }
    }
    
    // 監聽 Flutter 返回的 user_id
    const handleUserIdMessage = (event) => {
      console.log('🔔 Received message event:', event, typeof event)
      try {
        // 處理多種可能的消息格式
        let msg = null
        if (typeof event === 'string') {
          msg = JSON.parse(event)
        } else if (event?.data) {
          // 可能是 WebMessage 格式
          if (typeof event.data === 'string') {
            msg = JSON.parse(event.data)
          } else {
            msg = event.data
          }
        } else {
          msg = event
        }
        
        console.log('📦 Parsed message:', msg)
        
        // 檢查是否是 user_id 消息（即使 user_id 為空也要處理）
        if (msg?.name === 'user_id' && msg?.data !== undefined) {
          const userId = msg.data?.user_id ?? ''
          
          // 清理監聽器
          if (typeof window !== 'undefined') {
            window.removeEventListener('message', handleUserIdMessage)
            if (window.flutterObject?.removeEventListener) {
              window.flutterObject.removeEventListener('message', handleUserIdMessage)
            }
          }
          
          if (userId && userId.length > 0) {
            console.log('✅ Received user_id from Flutter:', userId)
            // 保存到 localStorage
            try {
              localStorage.setItem('userId', userId)
            } catch (e) {}
            doResolve(userId)
          } else {
            console.warn('⚠️ Received empty user_id from Flutter, will fallback to localStorage')
            // 即使收到空字符串，也清理監聽器並讓 fallback 邏輯處理
            // 不立即 resolve，讓 setTimeout 的 fallback 邏輯處理
          }
        } else {
          // 記錄收到的其他消息（用於調試）
          if (msg?.name) {
            console.log('📨 Received message from Flutter (not user_id):', msg.name, msg)
          }
        }
      } catch (e) {
        console.warn('Error parsing user_id message:', e, event)
      }
    }
    
    // 嘗試使用 Promise 方式（如果支持）
    const tryPromiseMethod = async () => {
      try {
        if (window.flutterObject?.postMessage && typeof window.flutterObject.postMessage === 'function') {
          // 檢查是否支持 Promise（某些實現可能支持）
          const result = await new Promise((resolve, reject) => {
            const timeout = setTimeout(() => {
              reject(new Error('Timeout waiting for Flutter response'))
            }, 1000)
            
            const handler = (event) => {
              clearTimeout(timeout)
              resolve(event)
            }
            
            if (window.flutterObject?.addEventListener) {
              window.flutterObject.addEventListener('message', handler)
            } else {
              window.addEventListener('message', handler)
            }
            
            window.flutterObject.postMessage(JSON.stringify({ name: 'get_user_id' }))
          })
          
          handleUserIdMessage(result)
          return true
        }
      } catch (e) {
        console.log('Promise method not supported, using event listener:', e)
      }
      return false
    }
    
    // 等待 flutterObject 可用
    const setupListener = () => {
      if (!window.flutterObject) {
        console.log('⏳ Waiting for flutterObject to be available...')
        setTimeout(setupListener, 100)
        return
      }
      
      console.log('🔍 flutterObject available:', {
        postMessage: typeof window.flutterObject.postMessage,
        addEventListener: typeof window.flutterObject.addEventListener,
        removeEventListener: typeof window.flutterObject.removeEventListener,
        onmessage: typeof window.flutterObject.onmessage,
        keys: Object.keys(window.flutterObject)
      })
      
      // 設置監聽器（多種方式）
      if (window.flutterObject?.addEventListener) {
        console.log('📡 Setting up flutterObject message listener')
        window.flutterObject.addEventListener('message', handleUserIdMessage)
      } else {
        console.log('📡 Setting up window message listener')
        window.addEventListener('message', handleUserIdMessage)
      }
      
      // 也嘗試監聽 flutterObject 的其他可能事件
      if (window.flutterObject.onmessage !== undefined) {
        console.log('📡 Using flutterObject.onmessage')
        const originalOnMessage = window.flutterObject.onmessage
        window.flutterObject.onmessage = (event) => {
          console.log('📨 flutterObject.onmessage called:', event)
          handleUserIdMessage(event)
          if (originalOnMessage) originalOnMessage(event)
        }
      }
      
      // 請求 user_id（延遲一點確保監聽器已設置）
      setTimeout(() => {
        requestUserId()
      }, 100)
    }
    
    // 立即嘗試設置，如果不行則等待
    if (window.flutterObject) {
      setupListener()
    } else {
      // 等待 DOM 和 flutterObject 準備好
      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', setupListener)
      } else {
        setupListener()
      }
    }
    
    // 如果 1.5 秒後還沒收到，嘗試從 localStorage 讀取（作為 fallback）
    setTimeout(() => {
      if (resolved) return // 已經 resolve 了，不需要 fallback
      
      try {
        const stored = localStorage.getItem('userId')
        // 檢查是否是有效的 UUID 格式（不是舊的數字格式）
        if (stored && stored.length > 10 && stored !== '1') {
          console.log('📦 Using stored userId from localStorage:', stored)
          doResolve(stored)
          return
        } else if (stored === '1') {
          // 清理舊的無效值
          localStorage.removeItem('userId')
          console.warn('⚠️ Removed invalid userId from localStorage')
        }
      } catch (e) {}
      
      // 如果還是沒有，使用測試用的預設值（開發/測試環境）
      console.warn('⚠️ 無法從 Flutter 獲取 user_id，使用測試用的預設值')
      try {
        localStorage.setItem('userId', DEFAULT_TEST_USER_ID)
      } catch (e) {}
      doResolve(DEFAULT_TEST_USER_ID)
    }, 1500)
  })
}

onMounted(async () => {
  // 先獲取 user_id (UUID 字符串)
  userId.value = await getUserIdFromFlutter()
  if (userId.value && typeof window !== 'undefined') {
    // 保存到 localStorage 作為備份
    try {
      localStorage.setItem('userId', userId.value) // 直接保存字符串
    } catch (e) {}
  }
  
  // 載入收藏和通知設置
  await loadSavedPlaces()
  loadNotificationSettings()
  await loadConstructionNotices()
  
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

async function loadSavedPlaces() {
  if (!userId.value) {
    console.warn('User ID not available, cannot load favorites')
    return
  }
  
  try {
    loadingFavorites.value = true
    const favorites = await getFavorites(userId.value) // userId 現在是 UUID 字符串
    const list = favorites
      .map((item) => normalizeFavorite(item))
      .filter(Boolean)
    // 後端已經按 added_at 倒序排列
    savedPlaces.value = list
    expandedFavoriteIds.value = expandedFavoriteIds.value.filter((id) => list.some((place) => place.id === id))
    
    // 同步通知設置
    const notificationMap = {}
    list.forEach(place => {
      if (place.id && place.notificationEnabled !== undefined) {
        notificationMap[place.id] = place.notificationEnabled
      }
    })
    notificationEnabled.value = notificationMap
  } catch (error) {
    console.error('Failed to load favorites:', error)
    savedPlaces.value = []
  } finally {
    loadingFavorites.value = false
  }
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

async function removeFavorite(id) {
  if (!userId.value) {
    console.warn('User ID not available, cannot delete favorite')
    return
  }
  
  try {
    await deleteFavorite(id, userId.value) // userId 現在是 UUID 字符串
    const next = savedPlaces.value.filter((place) => place.id !== id)
    savedPlaces.value = next
    expandedFavoriteIds.value = expandedFavoriteIds.value.filter((item) => item !== id)
    delete notificationEnabled.value[id]
    delete selectedCategory.value[id]
    saveNotificationSettings()
    // 觸發事件通知其他組件
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('map-favorites-updated'))
    }
  } catch (error) {
    console.error('Failed to delete favorite:', error)
    alert('刪除收藏失敗，請稍後再試')
  }
}

async function toggleNotification(placeId) {
  if (!userId.value) {
    console.warn('User ID not available, cannot update notification')
    return
  }
  
  const wasEnabled = notificationEnabled.value[placeId] || false
  const nowEnabled = !wasEnabled
  notificationEnabled.value[placeId] = nowEnabled
  
  try {
    await updateFavorite(placeId, userId.value, { // userId 現在是 UUID 字符串
      notification_enabled: nowEnabled
    })
    saveNotificationSettings()

    // 如果剛開啟，立即檢查一次（前端即時通知）
    if (nowEnabled) {
      checkAndNotifyPlace(placeId, { immediate: true })
    }
  } catch (error) {
    console.error('Failed to update notification setting:', error)
    // 回滾
    notificationEnabled.value[placeId] = wasEnabled
    alert('更新通知設置失敗，請稍後再試')
  }
}

function checkAndNotifyPlace(placeId, { immediate = false } = {}) {
  const place = savedPlaces.value.find(p => p.id === placeId)
  if (!place) return
  const recs = Array.isArray(place.recommendations) ? place.recommendations : []
  const constructionCount = recs.filter(r => r?.dsid === 'construction' || (r?.props && (r.props.DIGADD || r.props.PURP))).length
  if (constructionCount <= 0) return

  // 立即通知（前端層，不需時間間隔判斷）
  try {
    const isRoad = place.type === 'road'
    const isRoute = place.type === 'route'
    const radiusText = isRoad
      ? `${place.roadDistanceThreshold || ROAD_NOTICE_DISTANCE_M} 公尺內`
      : isRoute
        ? `${place.routeDistanceThreshold || ROUTE_NOTICE_DISTANCE_M} 公尺內`
        : '1 公里內'
    const subject = place.name || (isRoad ? '收藏道路' : isRoute ? '收藏路線' : '收藏地點')
    const actor = isRoad ? '此道路' : isRoute ? '此路線' : '此收藏'
    const payload = {
      name: 'notify',
      data: {
        title: `${subject} 附近施工資訊`,
        content: `${actor} ${radiusText}有 ${constructionCount} 個施工地點`,
      },
    }
    if (typeof window !== 'undefined' && window.flutterObject?.postMessage) {
      window.flutterObject.postMessage(JSON.stringify(payload))
    }
  } catch (e) {
    console.warn('Failed to send notify message', e)
  }
}

function getEmptyRecommendationMessage(place, category) {
  if (category === 'upcoming') return '目前沒有未來施工公告'
  const threshold = place?.roadDistanceThreshold || ROAD_NOTICE_DISTANCE_M
  if (place?.type === 'road') {
    return `此道路沒有施工資訊`
  }
  if (place?.type === 'route') {
    const routeThreshold = place?.routeDistanceThreshold || ROUTE_NOTICE_DISTANCE_M
    return `此路線沒有施工資訊`
  }
  return '附近 1 公里內沒有施工資訊'
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
  const category = selectedCategory.value[place.id]
  
  if (category === 'upcoming') {
    // 從施工公告 API 獲取未來施工公告
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    
    // 篩選未來施工公告
    const upcomingNotices = constructionNotices.value.filter(notice => {
      if (!notice.start_date) return false
      const startDate = new Date(notice.start_date)
      startDate.setHours(0, 0, 0, 0)
      return startDate > today
    })
    
    // 計算每個公告與收藏地點的距離
    const placeLon = place.lon
    const placeLat = place.lat
    
    if (!placeLon || !placeLat) {
      return []
    }
    
    let noticesWithDistance = upcomingNotices.map(notice => {
      let distance = null
      
      // 從 geometry 中提取座標
      if (notice.geometry) {
        const center = getGeometryCenter(notice.geometry)
        if (center) {
          distance = calculateDistance(placeLon, placeLat, center.lon, center.lat)
        }
      }
      
      return {
        id: notice.id,
        name: notice.name,
        addr: notice.road || notice.name,
        dist: distance,
        props: {
          DIGADD: notice.name,
          PURP: notice.road || notice.type || '',
          SDATE: notice.start_date,
          EDATE: notice.end_date,
          TYPE: notice.type,
          UNIT: notice.unit
        },
        notice: notice // 保存完整公告資料
      }
    })

    const keywordCandidates = [
      place.name,
      place.address,
      place.addr,
      place.roadName,
      place.routeStart,
      place.routeEnd
    ]
      .map((value) => typeof value === 'string' ? value.trim().toLowerCase() : '')
      .filter(Boolean)

    if (keywordCandidates.length > 0) {
      // 只保留公告內容中提到收藏名稱或相關標籤的項目
      noticesWithDistance = noticesWithDistance.filter((item) => {
        const searchableTexts = [
          item.name,
          item.addr,
          item.props?.DIGADD,
          item.props?.PURP,
          item.notice?.name,
          item.notice?.road,
          item.notice?.type
        ].filter((text) => typeof text === 'string')

        if (searchableTexts.length === 0) return false

        return keywordCandidates.some((keyword) =>
          searchableTexts.some((text) => text.toLowerCase().includes(keyword))
        )
      })
    }
    
    // 按距離排序（有距離的在前，然後按距離升序）
    noticesWithDistance.sort((a, b) => {
      if (a.dist === null && b.dist === null) return 0
      if (a.dist === null) return 1
      if (b.dist === null) return -1
      return a.dist - b.dist
    })
    
    return noticesWithDistance
  }
  
  // nearby - 使用原有的邏輯
  const recs = Array.isArray(place.recommendations) ? place.recommendations : []
  const constructions = recs.filter(r => r?.dsid === 'construction' || (r?.props && (r.props.DIGADD || r.props.PURP)))
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

function formatDate(dateStr) {
  if (!dateStr) return ''
  try {
    const date = new Date(dateStr)
    return date.toLocaleDateString('zh-TW')
  } catch {
    return dateStr
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

// 計算兩點之間的距離（Haversine 公式，單位：公尺）
function calculateDistance(lon1, lat1, lon2, lat2) {
  const toRad = (d) => d * Math.PI / 180
  const R = 6371000 // 地球半徑（公尺）
  const dLat = toRad(lat2 - lat1)
  const dLon = toRad(lon2 - lon1)
  const a = Math.sin(dLat/2)**2 + Math.cos(toRad(lat1))*Math.cos(toRad(lat2))*Math.sin(dLon/2)**2
  return 2 * R * Math.asin(Math.sqrt(a))
}

// 從 GeoJSON geometry 中提取中心點座標
function getGeometryCenter(geometry) {
  if (!geometry) return null
  
  if (geometry.type === 'Point') {
    return { lon: geometry.coordinates[0], lat: geometry.coordinates[1] }
  } else if (geometry.type === 'Polygon' && geometry.coordinates && geometry.coordinates[0]) {
    // 計算多邊形的中心點（簡單平均）
    const coords = geometry.coordinates[0]
    let sumLon = 0
    let sumLat = 0
    let count = 0
    for (const coord of coords) {
      sumLon += coord[0]
      sumLat += coord[1]
      count++
    }
    if (count > 0) {
      return { lon: sumLon / count, lat: sumLat / count }
    }
  }
  return null
}

async function loadConstructionNotices() {
  try {
    loadingNotices.value = true
    const notices = await getConstructionNotices(0, 500)
    constructionNotices.value = notices || []
  } catch (e) {
    console.error('Failed to load construction notices:', e)
    constructionNotices.value = []
  } finally {
    loadingNotices.value = false
  }
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
              class="flex-1 text-left w-full max-w-full overflow-hidden"
              @click="toggleFavoriteDetails(place.id)"
            >
              <div class="flex items-start gap-2">
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2">
                    <span class="truncate text-sm font-semibold text-gray-800 basis-[60%] max-w-[60%]">{{ place.name }}</span>
                      <span
                        v-if="favoriteTypeBadges[place.type]"
                        class="rounded-full px-2 py-0.5 text-[11px] font-medium shrink-0"
                        :class="favoriteTypeBadges[place.type]"
                      >
                        {{ place.type === 'road' ? '道路' : place.type === 'route' ? '路線' : '地點' }}
                      </span>
                  </div>
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
              class="text-xs text-gray-500 hover:underline"
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
                    <div class="font-medium">{{ rec.props?.DIGADD || rec.name }}</div>
                    <div class="text-xs text-gray-600 mt-0.5">{{ rec.props?.PURP || rec.addr }}</div>
                    <div v-if="rec.props?.SDATE || rec.props?.EDATE" class="text-xs text-amber-600 mt-1">
                      <span v-if="rec.props?.SDATE">{{ formatDate(rec.props.SDATE) }}</span>
                      <span v-if="rec.props?.SDATE && rec.props?.EDATE"> 至 </span>
                      <span v-if="rec.props?.EDATE">{{ formatDate(rec.props.EDATE) }}</span>
                    </div>
                  </div>
                  <div v-if="typeof rec.dist === 'number'" class="text-xs text-gray-400 mt-1">
                    距離約 {{ formatDistance(rec.dist) }}
                  </div>
                </div>
              </template>
              <p v-else class="py-3 text-center text-xs text-gray-500">
                {{ getEmptyRecommendationMessage(place, selectedCategory[place.id]) }}
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
