<script setup>
import { computed, onMounted, onBeforeUnmount, ref, createApp, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import MapPopup from './map/MapPopup.vue'
import TopTabs from './TopTabs.vue'
import redRiskIconUrl from '../assets/icons/red-risk-icon.svg'
import yellowRiskIconUrl from '../assets/icons/yellow-risk-icon.svg'
import { suggestRoadSegments, fetchRoadSegmentsByName, createFavorite, getFavorites, deleteFavorite } from '@/service/api'
const mapEl = ref(null)
let map = null
const router = useRouter()

// ====== Flutter / GPS 互動 ======
let pollTimer = null
let flutterMsgHandler = null

// ====== UI 狀態 ======
const searchMode = ref('place')      // 'place' | 'road' | 'route'
const searchText = ref('')
const roadSearchText = ref('')
const routeStart = ref('')           // 起點輸入
const routeEnd = ref('')             // 終點輸入
const currentRouteGeoJSON = ref(null) // 當前路線的 GeoJSON 資料
const currentRouteMeta = ref(null)    // 路線收藏與資訊所需的中繼資料
// 行政區篩選已移除，改用資料集顯示切換
const selectedDistrict = ref('')   // 保留但不再顯示 UI（若未來需要可再啟用）
const enabledDatasets = ref(['construction', 'narrow_street']) // 已啟用的資料集 ID 陣列（景點僅供搜尋用）
const showNearby = ref(false)
const nearbyList = ref([])
const selectedNearbyItem = ref(null) // 當前選中的詳細資訊項目
const showDetailView = ref(false) // 是否顯示詳細資訊模式（單行顯示）
const lastSearchLonLat = ref(null)  // { lon, lat }：最近一次「搜尋中心」
const userLonLat = ref(null)        // { lon, lat }：最新「GPS 定位」
const originMode = ref('gps')       // 'gps' | 'search'
const showSettingsPanel = ref(false) // 設定齒輪彈窗開關

// （行政區清單已不再顯示）
const TPE_DISTRICTS = []
const districtOptions = ref([])

// ====== Mapbox 搜尋邊界限定「台北市」=====
const TPE_CENTER = [121.5654, 25.0330]
const TPE_BBOX = '121.457,24.955,121.654,25.201'

const API_BASE = import.meta.env.VITE_API_BASE || ''

// ====== 資料集（全部顯示） ======
const datasets = ref([
  { id: 'attraction', name: '景點', url: '/mapData/attraction_tpe.geojson', color: '#f59e0b', outline: '#92400e', visible: true, includeNearby: true },
  { id: 'construction', name: '施工地點', url: `${API_BASE}/api/construction/geojson`, color: '#ef4444', outline: '#7f1d1d', visible: true, includeNearby: true },
  { id: 'narrow_street', name: '巷弄線圖', url: '/mapData/fire_narrow_street.geojson', color: '#64748b', outline: '#475569', visible: true, includeNearby: false },
])

const ROAD_SEARCH_SOURCE_ID = 'road-search'
const ROAD_SEARCH_LAYER_ID = 'road-search-lines'
const ROUTE_SOURCE_ID = 'route-navigation'
const ROUTE_LAYER_ID = 'route-line'
const ROUTE_MARKERS_SOURCE_ID = 'route-markers'
const ROUTE_MARKERS_LAYER_ID = 'route-markers-symbols'

const mapImagePromises = new Map()

function ensureMapImage(imageId, url) {
  if (!map) return Promise.resolve(false)
  try {
    if (typeof map.hasImage === 'function' && map.hasImage(imageId)) {
      return Promise.resolve(true)
    }
  } catch (_) {
    // ignore hasImage errors and continue loading
  }

  if (mapImagePromises.has(imageId)) {
    return mapImagePromises.get(imageId)
  }

  const promise = new Promise((resolve) => {
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => {
      try {
        map.addImage(imageId, img)
        resolve(true)
      } catch (err) {
        console.warn(`Failed to register map image: ${imageId}`, err)
        resolve(false)
      }
    }
    img.onerror = () => resolve(false)
    img.src = url
  })

  mapImagePromises.set(imageId, promise)
  return promise
}

// 快取：每個資料集 => { sourceId, layerIds, geo, bounds }
const datasetCache = new Map()
const favorites = ref([])
const selectedPlace = ref(null)
const userId = ref(null) // 從 Flutter 獲取的用戶 ID
const NEARBY_RADIUS_M = 1000
const lastRoadFeatureCollection = ref(null)
const lastRouteFeatureCollection = ref(null)

function handleTabSelect(tab) {
  if (tab === 'recommend') {
    router.push('/')
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
  
  // tab === 'map' 時不需要做任何事，因為已經在地圖頁面
}

function computeBounds(geo) {
  const bounds = new mapboxgl.LngLatBounds()
  for (const f of geo.features || []) {
    const g = f.geometry
    if (!g) continue
    if (g.type === 'Point') bounds.extend(g.coordinates)
    else if (g.type === 'MultiPoint' || g.type === 'LineString') for (const c of g.coordinates) bounds.extend(c)
    else if (g.type === 'MultiLineString' || g.type === 'Polygon') for (const ring of g.coordinates) for (const c of ring) bounds.extend(c)
    else if (g.type === 'MultiPolygon') for (const poly of g.coordinates) for (const ring of poly) for (const c of ring) bounds.extend(c)
  }
  return bounds
}

// 創建並顯示 popup
function createMapPopup(properties, datasetId, lngLat) {
  if (!map) return null
  
  const container = document.createElement('div')
  const lon = Array.isArray(lngLat) ? lngLat[0] : lngLat.lng
  const lat = Array.isArray(lngLat) ? lngLat[1] : lngLat.lat
  
  const app = createApp(MapPopup, { 
    properties, 
    datasetId,
    lon,
    lat
  })
  
  // 監聽收藏更新事件，刷新收藏列表
  app.config.globalProperties.$onFavoriteUpdated = () => {
    refreshFavorites()
  }
  
  app.mount(container)
  
  const popup = new mapboxgl.Popup({
    offset: 8,
    className: 'inset-card-popup'
  })
    .setLngLat(lngLat)
    .setDOMContent(container)
    .addTo(map)
  
  popup.on('close', () => {
    app.unmount()
    // 觸發收藏更新事件，讓主組件刷新收藏列表
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('map-favorites-updated'))
    }
  })
  
  return popup
}

function attachPopupInteraction(layerId, datasetIdOverride = null) {
  map.on('mouseenter', layerId, () => { map.getCanvas().style.cursor = 'pointer' })
  map.on('mouseleave', layerId, () => { map.getCanvas().style.cursor = '' })
  map.on('click', layerId, (e) => {
    const feature = e?.features?.[0]
    if (!feature) return
    const props = feature.properties || {}
    const datasetId = datasetIdOverride || 'attraction'
    const lon = e.lngLat.lng
    const lat = e.lngLat.lat
    // 設置 selectedPlace，以便可以收藏
    if (datasetId === 'construction') {
      // 對於 construction 類型，使用 DIGADD 和 PURP 字段
      const name = props['DIGADD'] || props['位置'] || '未命名地點'
      const addr = props['PURP'] || props['用途'] || ''
      pickSelectedPlace({ lon, lat, place: name, addr, props })
    } else {
      // 對於其他類型，使用位置和地址字段
      const name = props['位置'] || props['name'] || props['title'] || '未命名地點'
      const addr = props['地址'] || props['address'] || props['addr'] || ''
      pickSelectedPlace({ lon, lat, place: name, addr, props })
    }
    createMapPopup(props, datasetId, e.lngLat)
  })
}

// 顯示附近列表項目的 popup
function showNearbyItemPopup(item) {
  if (!map || !item) return
  
  // 設置詳細資訊模式
  selectedNearbyItem.value = item
  showDetailView.value = true
  
  // 先關閉現有的 popup
  const existingPopups = document.querySelectorAll('.mapboxgl-popup')
  existingPopups.forEach(p => p.remove())
  
  // 飛到該位置（使用 padding 讓目標點不在正中心）
  flyToLngLat(item.lon, item.lat, 16, { bottom: 250 })
  // map.flyTo({ center: [item.lon, item.lat], zoom: 16 })
  
  // 設置 selectedPlace，以便可以收藏
  const props = item.props || {}
  const datasetId = item.dsid || 'attraction'
  // item 已經有正確的 name 和 addr（在 collectNearbyPoints 中已處理）
  pickSelectedPlace({ 
    lon: item.lon, 
    lat: item.lat, 
    place: item.name, 
    addr: item.addr,
    props 
  })
  
  // 創建並顯示 popup
  createMapPopup(props, datasetId, [item.lon, item.lat])
}

// 返回搜尋結果清單
function backToNearbyList() {
  showDetailView.value = false
  selectedNearbyItem.value = null
  // 關閉 popup
  const existingPopups = document.querySelectorAll('.mapboxgl-popup')
  existingPopups.forEach(p => p.remove())
}

// 關閉附近清單
function closeNearbyList() {
  showNearby.value = false
  showDetailView.value = false
  selectedNearbyItem.value = null
}

async function ensureDatasetLoaded(ds) {
  if (!map || datasetCache.has(ds.id)) return
  const geo = await fetch(ds.url).then(r => r.json())
  const sourceId = `geo-${ds.id}`
  const first = geo?.features?.[0]
  const geomType = first?.geometry?.type || ''

  map.addSource(sourceId, { type: 'geojson', data: geo })
  const layerIds = []

  if (geomType.includes('Point')) {
    const lid = `${ds.id}-points`
    let added = false

    if (ds.id === 'construction') {
      const iconReady = await ensureMapImage('construction-icon-red', redRiskIconUrl)
      if (iconReady) {
        map.addLayer({
          id: lid,
          type: 'symbol',
          source: sourceId,
          layout: {
            visibility: ds.visible ? 'visible' : 'none',
            'icon-image': 'construction-icon-yellow',
            'icon-size': 0.5,
            'icon-allow-overlap': true,
            'icon-ignore-placement': true
          }
        })
        added = true
      }
    }

    if (!added) {
      map.addLayer({
        id: lid,
        type: 'circle',
        source: sourceId,
        paint: {
          'circle-radius': 6,
          'circle-color': ds.color,
          'circle-stroke-width': 1,
          'circle-stroke-color': ds.outline
        },
        layout: { visibility: ds.visible ? 'visible' : 'none' }
      })
    }

    layerIds.push(lid)
    attachPopupInteraction(lid, ds.id)
  } else if (geomType.includes('Line')) {
    const lid = `${ds.id}-lines`
    const paint = ds.id === 'narrow_street'
      ? {
          'line-color': [
            'match',
            ['get', 'category'],
            '紅區', '#ef4444',
            '黃區', '#f59e0b',
            ds.color
          ],
          'line-width': 3,
          'line-opacity': 0.9
        }
      : { 'line-color': ds.color, 'line-width': 2 }
    map.addLayer({
      id: lid,
      type: 'line',
      source: sourceId,
      paint,
      layout: { visibility: ds.visible ? 'visible' : 'none' }
    })
    layerIds.push(lid)
    attachPopupInteraction(lid, ds.id)
  } else {
    const fillId = `${ds.id}-fill`
    const outlineId = `${ds.id}-outline`
    map.addLayer({
      id: fillId,
      type: 'fill',
      source: sourceId,
      paint: { 'fill-color': ds.color, 'fill-opacity': 0.2 },
      layout: { visibility: ds.visible ? 'visible' : 'none' }
    })
    map.addLayer({
      id: outlineId,
      type: 'line',
      source: sourceId,
      paint: { 'line-color': ds.outline, 'line-width': 1 },
      layout: { visibility: ds.visible ? 'visible' : 'none' }
    })
    layerIds.push(fillId, outlineId)
    attachPopupInteraction(fillId, ds.id)
  }

  datasetCache.set(ds.id, { sourceId, layerIds, geo, bounds: computeBounds(geo) })
}

function setDatasetVisibility(ds, visible) {
  const cache = datasetCache.get(ds.id)
  if (!cache) return
  for (const lid of cache.layerIds) if (map.getLayer(lid)) {
    map.setLayoutProperty(lid, 'visibility', visible ? 'visible' : 'none')
  }
}

function toggleDataset(ds) {
  ds.visible = !ds.visible
  setDatasetVisibility(ds, ds.visible)
  computeNearbyForCurrentCenter()
}

function ensureRoadSearchLayer() {
  if (!map) return
  if (!map.getSource(ROAD_SEARCH_SOURCE_ID)) {
    map.addSource(ROAD_SEARCH_SOURCE_ID, {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] }
    })
  }
  if (!map.getLayer(ROAD_SEARCH_LAYER_ID)) {
    map.addLayer({
      id: ROAD_SEARCH_LAYER_ID,
      type: 'line',
      source: ROAD_SEARCH_SOURCE_ID,
      paint: {
        'line-color': '#2563eb',
        'line-width': 5,
        'line-opacity': 0.9
      }
    })
    attachPopupInteraction(ROAD_SEARCH_LAYER_ID, 'road_search')
  }
}

function setRoadSearchData(featureCollection, presetBounds = null) {
  if (!map) return
  ensureRoadSearchLayer()
  const src = map.getSource(ROAD_SEARCH_SOURCE_ID)
  if (!src) return
  src.setData(featureCollection || { type: 'FeatureCollection', features: [] })

  const bounds = presetBounds || computeBounds(featureCollection || { features: [] })
  if (bounds && !bounds.isEmpty()) {
    map.fitBounds(bounds, { padding: 60, maxZoom: 17 })
  }
  return bounds
}

watch(showNearby, async () => {
  await nextTick()
  map?.resize()
})

watch(searchMode, (mode) => {
  if (mode === 'place') {
    roadSearchText.value = ''
    roadSuggestions.value = []
    showRoadSuggestions.value = false
    clearRoadSearchData()
    clearRouteFromMap()
  } else if (mode === 'road') {
    searchText.value = ''
    clearRouteFromMap()
  } else if (mode === 'route') {
    searchText.value = ''
    roadSearchText.value = ''
    roadSuggestions.value = []
    showRoadSuggestions.value = false
    clearRoadSearchData()
  }
})

function normalizeFavorite(raw) {
  if (!raw || typeof raw !== 'object') return null
  const type = raw.type === 'road' ? 'road' : raw.type === 'route' ? 'route' : 'place'
  const normalized = {
    ...raw,
    type,
    recommendations: Array.isArray(raw?.recommendations) ? raw.recommendations : [],
  }
  if (type === 'road') {
    normalized.roadDistanceThreshold = typeof raw.roadDistanceThreshold === 'number'
      ? raw.roadDistanceThreshold
      : ROAD_CONSTRUCTION_DISTANCE_THRESHOLD
    if (!normalized.address) {
      const roadName = raw.roadName || raw.name || '道路'
      normalized.address = `${roadName} 道路`
    }
  } else if (type === 'route') {
    normalized.routeDistanceThreshold = typeof raw.routeDistanceThreshold === 'number'
      ? raw.routeDistanceThreshold
      : ROUTE_CONSTRUCTION_DISTANCE_THRESHOLD
    normalized.routeStart = raw.routeStart || raw.startLabel || raw.startInput || ''
    normalized.routeEnd = raw.routeEnd || raw.endLabel || raw.endInput || ''
    if (!normalized.name) {
      const startName = normalized.routeStart || '起點'
      const endName = normalized.routeEnd || '終點'
      normalized.name = `${startName} → ${endName}`
    }
    if (!normalized.address) {
      normalized.address = normalized.name
    }
  }
  return normalized
}

const currentFavoriteContext = computed(() => {
  const routeMeta = currentRouteMeta.value
  if (routeMeta?.featureCollection?.features?.length) {
    const startName = routeMeta.startLabel || routeMeta.startInput || '起點'
    const endName = routeMeta.endLabel || routeMeta.endInput || '終點'
    let center = lastSearchLonLat.value
    if (!center && routeMeta.featureCollection.features[0]?.geometry?.coordinates?.length) {
      const coords = routeMeta.featureCollection.features[0].geometry.coordinates
      if (Array.isArray(coords) && coords.length) {
        const midIndex = Math.floor(coords.length / 2)
        const mid = coords[midIndex]
        if (Array.isArray(mid) && mid.length >= 2) {
          center = { lon: mid[0], lat: mid[1] }
        }
      }
    }
    return {
      type: 'route',
      id: routeMeta.id,
      name: `${startName} → ${endName}`,
      startInput: routeMeta.startInput,
      endInput: routeMeta.endInput,
      startLabel: startName,
      endLabel: endName,
      startCoords: routeMeta.startCoords,
      endCoords: routeMeta.endCoords,
      distance: routeMeta.distance,
      duration: routeMeta.duration,
      featureCollection: routeMeta.featureCollection,
      center,
    }
  }

  const roadCollection = lastRoadFeatureCollection.value
  if (roadCollection && Array.isArray(roadCollection.features) && roadCollection.features.length > 0) {
    const keyword = (roadSearchText.value || '').trim()
    const features = roadCollection.features
    const osmids = [...new Set(features.map((f) => f?.properties?.osmid).filter(Boolean))].sort()
    const nameCandidates = features
      .map((f) => f?.properties?.name)
      .filter((v) => typeof v === 'string' && v.trim().length > 0)
    const roadName = nameCandidates[0] || keyword || '未命名道路'
    let center = lastSearchLonLat.value
    if (!center) {
      const bounds = computeBounds(roadCollection)
      if (bounds && typeof bounds.getCenter === 'function' && !bounds.isEmpty?.()) {
        const c = bounds.getCenter()
        center = { lon: c.lng, lat: c.lat }
      }
    }
    return {
      type: 'road',
      id: osmids.length ? `road:${osmids.join(',')}` : `road:${roadName}`,
      name: roadName,
      keyword,
      osmids,
      center,
    }
  }

  if (selectedPlace.value?.id) {
    return {
      type: 'place',
      id: selectedPlace.value.id,
      place: selectedPlace.value,
    }
  }

  return null
})

const currentFavoriteSaved = computed(() => {
  const ctx = currentFavoriteContext.value
  if (!ctx) return false
  
  // 根據類型匹配收藏
  if (ctx.type === 'place' && ctx.place) {
    return favorites.value.some((fav) => {
      if (fav.type !== 'place') return false
      // 比較 place_data 中的 id
      if (ctx.place.id && fav.place_data?.id === ctx.place.id) return true
      // 或比較座標（用於沒有 id 的地點）
      if (fav.lon && fav.lat && ctx.place.lon && ctx.place.lat) {
        const dist = Math.abs(fav.lon - ctx.place.lon) + Math.abs(fav.lat - ctx.place.lat)
        return dist < 0.0001 // 約 10 公尺內的誤差
      }
      return false
    })
  }
  
  if (ctx.type === 'road' && ctx.name) {
    return favorites.value.some((fav) => {
      if (fav.type !== 'road') return false
      // 比較道路名稱和 osmids
      if (fav.road_name === ctx.name) {
        if (ctx.osmids && fav.road_osmids) {
          const ctxOsmids = Array.isArray(ctx.osmids) ? ctx.osmids.sort() : []
          const favOsmids = Array.isArray(fav.road_osmids) ? fav.road_osmids.sort() : []
          if (ctxOsmids.length === favOsmids.length && ctxOsmids.length > 0) {
            return ctxOsmids.every((id, i) => id === favOsmids[i])
          }
        }
        return true // 如果沒有 osmids，只比較名稱
      }
      return false
    })
  }
  
  if (ctx.type === 'route' && ctx.startLabel && ctx.endLabel) {
    return favorites.value.some((fav) => {
      if (fav.type !== 'route') return false
      // 比較路線起點和終點
      return fav.route_start === ctx.startLabel && fav.route_end === ctx.endLabel
    })
  }
  
  return false
})

// 測試用的預設 user_id（當沒有 Flutter 環境時使用）
const DEFAULT_TEST_USER_ID = '7f3562f4-bb3f-4ec7-89b9-da3b4b5ff250'

// 從 Flutter 獲取 user_id（與 Home.vue 相同）
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
    
    const handleUserIdMessage = (event) => {
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
    
    if (window.flutterObject?.addEventListener) {
      window.flutterObject.addEventListener('message', handleUserIdMessage)
    } else {
      window.addEventListener('message', handleUserIdMessage)
    }
    
    requestUserId()
    
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

async function refreshFavorites() {
  if (!userId.value) {
    console.warn('User ID not available, cannot load favorites')
    return
  }
  
  try {
    const favoritesList = await getFavorites(userId.value) // userId 現在是 UUID 字符串
    const list = favoritesList
      .map((item) => normalizeFavorite(item))
      .filter(Boolean)
    favorites.value = list
  } catch (error) {
    console.error('Failed to load favorites:', error)
    favorites.value = []
  }
}

async function removeFavoriteById(id) {
  if (!userId.value) {
    console.warn('User ID not available, cannot delete favorite')
    return
  }
  
  try {
    await deleteFavorite(id, userId.value) // userId 現在是 UUID 字符串
    const next = favorites.value.filter((f) => f.id !== id)
    favorites.value = next
    // 觸發事件通知其他組件
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('map-favorites-updated'))
    }
  } catch (error) {
    console.error('Failed to delete favorite:', error)
    alert('刪除收藏失敗，請稍後再試')
  }
}

async function toggleFavorite() {
  const ctx = currentFavoriteContext.value
  if (!ctx) {
    alert('請先搜尋並選擇要收藏的地點、道路或路線')
    return
  }

  if (currentFavoriteSaved.value) {
    // 找到對應的收藏並刪除
    let favoriteToRemove = null
    
    if (ctx.type === 'place' && ctx.place) {
      favoriteToRemove = favorites.value.find((fav) => {
        if (fav.type !== 'place') return false
        // 比較 place_data 中的 id
        if (ctx.place.id && fav.place_data?.id === ctx.place.id) return true
        // 或比較座標（用於沒有 id 的地點）
        if (fav.lon && fav.lat && ctx.place.lon && ctx.place.lat) {
          const dist = Math.abs(fav.lon - ctx.place.lon) + Math.abs(fav.lat - ctx.place.lat)
          return dist < 0.0001
        }
        return false
      })
    } else if (ctx.type === 'road' && ctx.name) {
      favoriteToRemove = favorites.value.find((fav) => {
        if (fav.type !== 'road') return false
        if (fav.road_name === ctx.name) {
          if (ctx.osmids && fav.road_osmids) {
            const ctxOsmids = Array.isArray(ctx.osmids) ? ctx.osmids.sort() : []
            const favOsmids = Array.isArray(fav.road_osmids) ? fav.road_osmids.sort() : []
            if (ctxOsmids.length === favOsmids.length && ctxOsmids.length > 0) {
              return ctxOsmids.every((id, i) => id === favOsmids[i])
            }
          }
          return true
        }
        return false
      })
    } else if (ctx.type === 'route' && ctx.startLabel && ctx.endLabel) {
      favoriteToRemove = favorites.value.find((fav) => {
        if (fav.type !== 'route') return false
        return fav.route_start === ctx.startLabel && fav.route_end === ctx.endLabel
      })
    }
    
    if (favoriteToRemove?.id) {
      removeFavoriteById(favoriteToRemove.id)
    }
    return
  }

  if (ctx.type === 'place') {
    const place = ctx.place
    if (!place) return

    for (const ds of datasets.value) {
      await ensureDatasetLoaded(ds)
    }

    const nearby = collectNearbyPoints(place.lon, place.lat, {
      respectVisibility: false,
      respectDistrict: false,
      limit: 50,
    })

    if (!userId.value) {
      alert('無法獲取用戶 ID，請稍後再試')
      return
    }

    // 檢查是否是 construction 類型，如果是則從 props 中提取 DIGADD 和 PURP
    const props = place.props || {}
    let name = place.name || place.addr || '未命名地點'
    let address = place.addr || place.name || ''
    
    // 如果 props 中有 DIGADD 和 PURP，說明是 construction 類型
    if (props.DIGADD || props.PURP) {
      name = props.DIGADD || props['位置'] || name
      address = props.PURP || props['用途'] || address
    }

    const payload = {
      type: 'place',
      name: name,
      address: address,
      lon: place.lon,
      lat: place.lat,
      place_data: place, // 保存完整地點信息（已包含 props）
      recommendations: nearby.map((r) => ({
        name: r.name,
        addr: r.addr,
        dist: r.dist,
        lon: r.lon,
        lat: r.lat,
        dsid: r.dsid,
        props: r.props || null,
      })),
      notification_enabled: false,
      distance_threshold: 100.0,
    }

    try {
      const saved = await createFavorite(payload, userId.value) // userId 現在是 UUID 字符串
      const normalized = normalizeFavorite(saved)
      if (normalized) {
        favorites.value = [...favorites.value, normalized]
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new CustomEvent('map-favorites-updated'))
        }
      }
    } catch (error) {
      console.error('Failed to create favorite:', error)
      alert('收藏失敗，請稍後再試')
    }
    return
  }

  if (ctx.type === 'road') {
    const constructionDs = datasets.value.find((ds) => ds.id === 'construction')
    if (constructionDs) {
      try { await ensureDatasetLoaded(constructionDs) } catch (_) {}
    }

    const matches = lastRoadFeatureCollection.value
      ? collectRoadConstructionMatches(lastRoadFeatureCollection.value)
      : []
    if (!userId.value) {
      alert('無法獲取用戶 ID，請稍後再試')
      return
    }

    const payload = {
      type: 'road',
      name: ctx.name,
      address: `${ctx.name} 道路`,
      lon: ctx.center?.lon ?? null,
      lat: ctx.center?.lat ?? null,
      road_name: ctx.name,
      road_search_name: ctx.keyword || ctx.name,
      road_osmids: ctx.osmids,
      road_distance_threshold: ROAD_CONSTRUCTION_DISTANCE_THRESHOLD,
      recommendations: matches.map((item) => ({
        name: item.name,
        addr: item.addr,
        dist: item.dist,
        lon: item.lon,
        lat: item.lat,
        dsid: item.dsid,
        props: item.props || null,
      })),
      notification_enabled: false,
      distance_threshold: 100.0,
    }

    try {
      const saved = await createFavorite(payload, userId.value) // userId 現在是 UUID 字符串
      const normalized = normalizeFavorite(saved)
      if (normalized) {
        favorites.value = [...favorites.value, normalized]
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new CustomEvent('map-favorites-updated'))
        }
      }
    } catch (error) {
      console.error('Failed to create favorite:', error)
      alert('收藏失敗，請稍後再試')
    }
    return
  }

  if (ctx.type === 'route') {
    const constructionDs = datasets.value.find((ds) => ds.id === 'construction')
    if (constructionDs) {
      try { await ensureDatasetLoaded(constructionDs) } catch (_) {}
    }

    const featureCollection = ctx.featureCollection || lastRouteFeatureCollection.value
    const matches = featureCollection
      ? collectRoadConstructionMatches(featureCollection, ROUTE_CONSTRUCTION_DISTANCE_THRESHOLD)
      : []

    if (!userId.value) {
      alert('無法獲取用戶 ID，請稍後再試')
      return
    }

    const payload = {
      type: 'route',
      name: ctx.name,
      address: ctx.name,
      route_start: ctx.startLabel || ctx.startInput,
      route_end: ctx.endLabel || ctx.endInput,
      route_start_coords: ctx.startCoords || null,
      route_end_coords: ctx.endCoords || null,
      route_distance: typeof ctx.distance === 'number' ? ctx.distance : null,
      route_duration: typeof ctx.duration === 'number' ? ctx.duration : null,
      route_distance_threshold: ROUTE_CONSTRUCTION_DISTANCE_THRESHOLD,
      route_feature_collection: featureCollection,
      recommendations: matches.map((item) => ({
        name: item.name,
        addr: item.addr,
        dist: item.dist,
        lon: item.lon,
        lat: item.lat,
        dsid: item.dsid,
        props: item.props || null,
      })),
      notification_enabled: false,
      distance_threshold: 100.0,
    }

    try {
      const saved = await createFavorite(payload, userId.value) // userId 現在是 UUID 字符串
      const normalized = normalizeFavorite(saved)
      if (normalized) {
        favorites.value = [...favorites.value, normalized]
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new CustomEvent('map-favorites-updated'))
        }
      }
    } catch (error) {
      console.error('Failed to create favorite:', error)
      alert('收藏失敗，請稍後再試')
    }
  }
}

function clearSearchText() {
  if (searchMode.value === 'road') {
    roadSearchText.value = ''
    roadSuggestions.value = []
    showRoadSuggestions.value = false
    clearRoadSearchData()
  } else {
    searchText.value = ''
  }
}

function clearRouteInputs() {
  routeStart.value = ''
  routeEnd.value = ''
  clearRouteFromMap()
}

function clearRouteStart() {
  if (!routeStart.value) return
  routeStart.value = ''
  clearRouteFromMap()
}

function clearRouteEnd() {
  if (!routeEnd.value) return
  routeEnd.value = ''
  clearRouteFromMap()
}

function swapRouteEndpoints() {
  if (!routeStart.value && !routeEnd.value) return
  const nextStart = routeEnd.value
  routeEnd.value = routeStart.value
  routeStart.value = nextStart
  clearRouteFromMap()
}

function clearRouteFromMap() {
  // 清除路線圖層
  if (map && map.getSource(ROUTE_SOURCE_ID)) {
    map.getSource(ROUTE_SOURCE_ID)?.setData({
      type: 'FeatureCollection',
      features: []
    })
  }
  if (map && map.getSource(ROUTE_MARKERS_SOURCE_ID)) {
    map.getSource(ROUTE_MARKERS_SOURCE_ID)?.setData({
      type: 'FeatureCollection',
      features: []
    })
  }
  currentRouteGeoJSON.value = null
  currentRouteMeta.value = null
  lastRouteFeatureCollection.value = null
  routeMatchList.value = []
  showRouteMatches.value = false
  showRouteMatchDetail.value = false
  selectedRouteMatch.value = null
  routeMatchNotice.value = ''
  routeMatchesReady.value = false
  updateRoadConstructionHighlights([], null)
}

async function performRouteSearch() {
  const start = routeStart.value.trim()
  const end = routeEnd.value.trim()
  
  if (!start || !end) {
    alert('請輸入起點和終點')
    return
  }

  try {
    console.log('開始路線規劃:', { start, end })
    
  // 1. 先將起點和終點轉換成座標（優先使用本地景點資料集，找不到再回落 Mapbox）
  const startCoords = await resolvePlaceCoordinates(start)
    console.log('起點座標:', startCoords)

  const endCoords = await resolvePlaceCoordinates(end)
    console.log('終點座標:', endCoords)

    if (!startCoords) {
      alert(`找不到起點：${start}\n請輸入更精確的地址或地點名稱`)
      return
    }
    if (!endCoords) {
      alert(`找不到終點：${end}\n請輸入更精確的地址或地點名稱`)
      return
    }

    // 2. 使用 Mapbox Directions API 取得路線
    const accessToken = import.meta.env.VITE_MAPBOXTOKEN || mapboxgl.accessToken
    if (!accessToken) {
      console.error('Mapbox token not found')
      alert('地圖服務設定錯誤，請聯絡系統管理員')
      return
    }

    const directionsUrl = `https://api.mapbox.com/directions/v5/mapbox/walking/${startCoords.lon},${startCoords.lat};${endCoords.lon},${endCoords.lat}`
    const params = new URLSearchParams({
      geometries: 'geojson',
      access_token: accessToken,
      language: 'zh-Hant',
    })

    console.log('呼叫 Directions API:', `${directionsUrl}?${params}`)
    
    const response = await fetch(`${directionsUrl}?${params}`)
    const data = await response.json()
    
    console.log('API 回應:', data)

    if (!response.ok) {
      console.error('API 錯誤:', response.status, data)
      alert(`路線規劃服務錯誤 (${response.status})\n${data.message || '請稍後再試'}`)
      return
    }

    if (!data.routes || data.routes.length === 0) {
      alert('找不到可行路線，請嘗試其他地點')
      return
    }

    const route = data.routes[0]
    console.log('找到路線:', {
      distance: route.distance,
      duration: route.duration,
      coordinates: route.geometry.coordinates.length
    })
    
    const routeGeoJSON = {
      type: 'Feature',
      geometry: route.geometry,
      properties: {
        distance: route.distance,
        duration: route.duration
      }
    }

    currentRouteGeoJSON.value = routeGeoJSON

    const routeFeatureCollection = {
      type: 'FeatureCollection',
      features: [{
        type: 'Feature',
        geometry: routeGeoJSON.geometry,
        properties: {
          dataset: 'route_search',
          distance: route.distance,
          duration: route.duration,
        },
      }],
    }

    const startLabel = startCoords.place || startCoords.addr || start
    const endLabel = endCoords.place || endCoords.addr || end
    const routeId = `route:${startCoords.lon.toFixed(6)},${startCoords.lat.toFixed(6)}->${endCoords.lon.toFixed(6)},${endCoords.lat.toFixed(6)}`
    currentRouteMeta.value = {
      id: routeId,
      startInput: start,
      endInput: end,
      startLabel,
      endLabel,
      startCoords,
      endCoords,
      distance: route.distance,
      duration: route.duration,
      featureCollection: routeFeatureCollection,
    }

    lastRouteFeatureCollection.value = routeFeatureCollection
    lastRoadFeatureCollection.value = null
    selectedPlace.value = null
    originMode.value = 'search'
    showNearby.value = false
    showDetailView.value = false
    selectedNearbyItem.value = null
    const existingPopups = document.querySelectorAll('.mapboxgl-popup')
    existingPopups.forEach((p) => p.remove())

    const constructionDs = datasets.value.find((ds) => ds.id === 'construction')
    if (constructionDs) {
      try { await ensureDatasetLoaded(constructionDs) } catch (_) {}
    }

    // 3. 在地圖上顯示路線
    displayRouteOnMap(routeGeoJSON, startCoords, endCoords)

    // 4. 調整視角以顯示完整路線
    const coordinates = route.geometry.coordinates
    const bounds = coordinates.reduce((bounds, coord) => {
      return bounds.extend(coord)
    }, new mapboxgl.LngLatBounds(coordinates[0], coordinates[0]))

    map.fitBounds(bounds, {
      padding: 80,
      maxZoom: 16
    })

    if (!bounds.isEmpty()) {
      const center = bounds.getCenter()
      lastSearchLonLat.value = { lon: center.lng, lat: center.lat }
    }

    refreshRouteMatches(true)

  } catch (error) {
    console.error('路線規劃錯誤:', error)
    alert(`路線規劃失敗：${error.message}\n請檢查網路連線或稍後再試`)
  }
}

function displayRouteOnMap(routeGeoJSON, startCoords, endCoords) {
  // 確保路線圖層存在
  if (!map.getSource(ROUTE_SOURCE_ID)) {
    map.addSource(ROUTE_SOURCE_ID, {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] }
    })
  }

  if (!map.getLayer(ROUTE_LAYER_ID)) {
    map.addLayer({
      id: ROUTE_LAYER_ID,
      type: 'line',
      source: ROUTE_SOURCE_ID,
      layout: {
        'line-join': 'round',
        'line-cap': 'round'
      },
      paint: {
        'line-color': '#3b82f6',
        'line-width': 5,
        'line-opacity': 0.8
      }
    })
  }

  // 設定路線資料
  map.getSource(ROUTE_SOURCE_ID).setData({
    type: 'FeatureCollection',
    features: [routeGeoJSON]
  })

  // 顯示起點和終點標記
  if (!map.getSource(ROUTE_MARKERS_SOURCE_ID)) {
    map.addSource(ROUTE_MARKERS_SOURCE_ID, {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] }
    })
  }

  if (!map.getLayer(ROUTE_MARKERS_LAYER_ID)) {
    map.addLayer({
      id: ROUTE_MARKERS_LAYER_ID,
      type: 'circle',
      source: ROUTE_MARKERS_SOURCE_ID,
      paint: {
        'circle-radius': 8,
        'circle-color': [
          'match',
          ['get', 'type'],
          'start', '#22c55e',
          'end', '#ef4444',
          '#94a3b8'
        ],
        'circle-stroke-width': 2,
        'circle-stroke-color': '#ffffff'
      }
    })
  }

  // 設定起點和終點標記
  map.getSource(ROUTE_MARKERS_SOURCE_ID).setData({
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        geometry: {
          type: 'Point',
          coordinates: [startCoords.lon, startCoords.lat]
        },
        properties: { type: 'start', name: '起點' }
      },
      {
        type: 'Feature',
        geometry: {
          type: 'Point',
          coordinates: [endCoords.lon, endCoords.lat]
        },
        properties: { type: 'end', name: '終點' }
      }
    ]
  })
}

function centerOnUserLocation() {
  if (!userLonLat.value) {
    alert('尚未取得您的位置')
    return
  }
  const { lon, lat } = userLonLat.value
  map.flyTo({ center: [lon, lat], zoom: Math.max(map.getZoom() ?? 0, 15) })
  originMode.value = 'gps'
  computeNearby(lon, lat)
}

// ===== 使用者定位 =====
function ensureUserLayer() {
  if (!map.getSource('user-location')) {
    map.addSource('user-location', {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] }
    })
  }
  if (!map.getLayer('user-location-circle')) {
    map.addLayer({
      id: 'user-location-circle',
      type: 'circle',
      source: 'user-location',
      paint: {
        'circle-radius': 8,
        'circle-color': '#5AB4C5',
        'circle-stroke-width': 2,
        'circle-stroke-color': '#ffffff'
      }
    })
  }
}

function setUserSource(lon, lat) {
  const src = map.getSource('user-location')
  if (!src) return
  const geo = {
    type: 'FeatureCollection',
    features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: [lon, lat] } }]
  }
  src.setData(geo)
}

function updateUserLocation(lon, lat) {
  userLonLat.value = { lon, lat }
  setUserSource(lon, lat)
  // 若目前中心來源是 GPS（或尚未有搜尋），就更新附近清單並移動視角
  if (originMode.value === 'gps') {
    map.flyTo({ center: [lon, lat], zoom: Math.max(map.getZoom() ?? 0, 14) })
    computeNearbyForCurrentCenter()
  }
}

function handleIncomingMessage(raw) {
  try {
    const msg = typeof raw === 'string' ? JSON.parse(raw) : raw
    const payload = msg?.data ?? msg
    const name = msg?.name ?? null
    if (name === 'location' && payload) {
      const lat = payload.latitude ?? payload.lat ?? payload.coords?.latitude
      const lon = payload.longitude ?? payload.lng ?? payload.lon ?? payload.coords?.longitude
      if (typeof lat === 'number' && typeof lon === 'number') {
        updateUserLocation(lon, lat)
      }
    }
  } catch (err) {
    console.warn('Invalid location message', err)
  }
}

function requestLocationFromFlutter() {
  try {
    const payload = JSON.stringify({ name: 'location' })
    if (window.flutterObject?.postMessage) {
      window.flutterObject.postMessage(payload)
      return true
    }
  } catch (_) {}
  return false
}

function startPollingFlutter(intervalMs = 1000) {
  requestLocationFromFlutter()
  pollTimer = setInterval(requestLocationFromFlutter, intervalMs)
}

// ===== 搜尋標記（紅點）=====
function ensureSearchMarkerLayer() {
  if (!map.getSource('search-target')) {
    map.addSource('search-target', {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] }
    })
  }
  if (!map.getLayer('search-target-circle')) {
    map.addLayer({
      id: 'search-target-circle',
      type: 'circle',
      source: 'search-target',
      paint: {
        'circle-radius': 9,
        'circle-color': '#5AB4C5',
        'circle-stroke-width': 2,
        'circle-stroke-color': '#ffffff'
      }
    })
  }
}

function clearSearchMarker() {
  const src = map.getSource('search-target')
  if (!src) return
  const empty = { type: 'FeatureCollection', features: [] }
  src.setData(empty)
}

// ===== 行政區篩選 =====
// 資料集顯示切換（多選）
function applyDatasetFilter() {
  for (const ds of datasets.value) {
    ds.visible = enabledDatasets.value.includes(ds.id)
    setDatasetVisibility(ds, ds.visible)
  }
  computeNearbyForCurrentCenter()
  refreshRoadMatches()
  refreshRouteMatches()
}

function toggleDatasetCheckbox(datasetId) {
  const index = enabledDatasets.value.indexOf(datasetId)
  if (index > -1) {
    enabledDatasets.value.splice(index, 1)
  } else {
    enabledDatasets.value.push(datasetId)
  }
  applyDatasetFilter()
}

function selectAllDatasets() {
  enabledDatasets.value = datasets.value.map(ds => ds.id)
  applyDatasetFilter()
}

function deselectAllDatasets() {
  enabledDatasets.value = []
  applyDatasetFilter()
}

// ===== 距離計算（Haversine，公尺）=====
function distM(lon1, lat1, lon2, lat2) {
  const toRad = (d) => d * Math.PI / 180
  const R = 6371000
  const dLat = toRad(lat2 - lat1)
  const dLon = toRad(lon2 - lon1)
  const a = Math.sin(dLat/2)**2 + Math.cos(toRad(lat1))*Math.cos(toRad(lat2))*Math.sin(dLon/2)**2
  return 2 * R * Math.asin(Math.sqrt(a))
}

function collectNearbyPoints(lon, lat, options = {}) {
  const {
    maxDistance = 1000,
    limit = 50,
    respectVisibility = true,
    respectDistrict = true,
  } = options

  const results = []
  for (const ds of datasets.value) {
    if (respectVisibility && !ds.visible) continue
    // 這個資料集不參與「附近推薦」
    if (ds.includeNearby === false) continue
    const cache = datasetCache.get(ds.id)
    if (!cache) continue
    const feats = cache.geo?.features || []
    for (const f of feats) {
      if (respectDistrict && selectedDistrict.value && (f?.properties?.['行政區']?.trim() !== selectedDistrict.value)) continue
      const g = f.geometry
      if (!g || g.type !== 'Point') continue
      const [flon, flat] = g.coordinates
      const d = distM(lon, lat, flon, flat)
      if (d <= maxDistance) {
        // 名稱與內容格式：景點用 位置+地址，施工用 DIGADD + PURP
        let name = f?.properties?.['位置'] || f?.properties?.['位置'] || '(未命名)'
        let addr = f?.properties?.['地址'] || ''
        if (ds.id === 'construction') {
          const apName = f?.properties?.['DIGADD'] || f?.properties?.['位置'] || '(未命名)'
          const purp = f?.properties?.['PURP'] || f?.properties?.['地址'] || ''
          name = apName
          addr = purp
        }
        results.push({
          dsid: ds.id,
          name,
          addr,
          dist: Math.round(d),
          lon: flon,
          lat: flat,
          props: f.properties,
        })
      }
    }
  }
  results.sort((a, b) => a.dist - b.dist)
  return limit ? results.slice(0, limit) : results
}



function destPoint(lon, lat, bearingDeg, distanceMeters) {
  // returns [lon, lat]
  const R = 6371000
  const brng = bearingDeg * Math.PI / 180
  const d = distanceMeters / R
  const lat1 = lat * Math.PI / 180
  const lon1 = lon * Math.PI / 180

  const lat2 = Math.asin(Math.sin(lat1) * Math.cos(d) + Math.cos(lat1) * Math.sin(d) * Math.cos(brng))
  const lon2 = lon1 + Math.atan2(Math.sin(brng) * Math.sin(d) * Math.cos(lat1), Math.cos(d) - Math.sin(lat1) * Math.sin(lat2))
  return [ (lon2 * 180 / Math.PI), (lat2 * 180 / Math.PI) ]
}

function createCircleGeoJSON(lon, lat, radiusMeters, steps = 64) {
  const coords = []
  for (let i = 0; i < steps; i++) {
    const bearing = (i / steps) * 360
    coords.push(destPoint(lon, lat, bearing, radiusMeters))
  }
  coords.push(coords[0])
  return {
    type: 'FeatureCollection',
    features: [ { type: 'Feature', geometry: { type: 'Polygon', coordinates: [coords] }, properties: {} } ]
  }
}

function ensureNearbyCircleLayer() {
  if (!map) return
  if (!map.getSource('nearby-circle')) {
    map.addSource('nearby-circle', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
  }
  if (!map.getLayer('nearby-circle-fill')) {
    map.addLayer({
      id: 'nearby-circle-fill',
      type: 'fill',
      source: 'nearby-circle',
      paint: { 'fill-color': '#06b6d4', 'fill-opacity': 0.08 },
      layout: { visibility: 'visible' }
    })
  }
  if (!map.getLayer('nearby-circle-outline')) {
    map.addLayer({
      id: 'nearby-circle-outline',
      type: 'line',
      source: 'nearby-circle',
      paint: { 'line-color': '#06b6d4', 'line-width': 2 },
      layout: { visibility: 'visible' }
    })
  }

  // points (施工) highlight source/layer
  if (!map.getSource('nearby-points-highlight')) {
    map.addSource('nearby-points-highlight', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
  }
  // register risk icon and add symbol layer using the image
  if (!map.getLayer('nearby-points-highlight-symbol')) {
    const addHighlightLayer = () => {
      if (!map.getLayer('nearby-points-highlight-symbol')) {
        map.addLayer({
          id: 'nearby-points-highlight-symbol',
          type: 'symbol',
          source: 'nearby-points-highlight',
          layout: {
            'icon-image': 'construction-icon-red',
            'icon-size': 0.5,
            'icon-allow-overlap': true,
            'icon-ignore-placement': true
          }
        })
        attachPopupInteraction('nearby-points-highlight-symbol', 'construction')
      }
    }

    ensureMapImage('construction-icon-yellow', yellowRiskIconUrl)
      .then(() => { addHighlightLayer() })
      .catch(() => { addHighlightLayer() })
  }

  // lines (窄巷) highlight source/layer
  if (!map.getSource('nearby-lines-highlight')) {
    map.addSource('nearby-lines-highlight', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
  }
  if (!map.getLayer('nearby-lines-highlight')) {
    map.addLayer({
      id: 'nearby-lines-highlight',
      type: 'line',
      source: 'nearby-lines-highlight',
      paint: { 'line-color': '#7c3aed', 'line-width': 4, 'line-opacity': 0.9 }
    })
    attachPopupInteraction('nearby-lines-highlight', 'narrow_street')
  }

  // center marker (藍色圓心)
  if (!map.getSource('nearby-center')) {
    map.addSource('nearby-center', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
  }
  if (!map.getLayer('nearby-center-circle')) {
    map.addLayer({
      id: 'nearby-center-circle',
      type: 'circle',
      source: 'nearby-center',
      paint: {
        'circle-radius': 8,
        'circle-color': '#5AB4C5',
        'circle-stroke-width': 2,
        'circle-stroke-color': '#ffffff'
      }
    })
  }
}

function updateCircleAndHighlights(centerLon, centerLat) {
  if (!map) return
  ensureNearbyCircleLayer()
  const circle = createCircleGeoJSON(centerLon, centerLat, NEARBY_RADIUS_M, 96)
  map.getSource('nearby-circle')?.setData(circle)

  // 更新圓心位置
  const centerGeo = { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: [centerLon, centerLat] }, properties: {} }] }
  map.getSource('nearby-center')?.setData(centerGeo)

  // collect nearby features from datasetCache
  const pointFeatures = []
  const lineFeatures = []
  for (const [dsid, cache] of datasetCache.entries()) {
    if (!cache || !cache.geo) continue
    const ds = datasets.value.find((d) => d.id === dsid)
    if (!ds) continue
    if (!ds.visible) continue
    const allowPointHighlight = ds.includeNearby !== false
  // highlighter respects dataset visibility; points honor includeNearby flag
    for (const f of cache.geo.features || []) {
      if (!f || !f.geometry) continue
      const g = f.geometry
      if (g.type === 'Point') {
        if (!allowPointHighlight) continue
        const [flon, flat] = g.coordinates
        if (distM(centerLon, centerLat, flon, flat) <= NEARBY_RADIUS_M) {
          pointFeatures.push({ type: 'Feature', geometry: g, properties: { ...f.properties, _dsid: dsid } })
        }
      } else if (g.type === 'LineString' || g.type === 'MultiLineString') {
        // include line if any vertex within radius
        const coordsArray = g.type === 'LineString' ? [g.coordinates] : g.coordinates
        let included = false
        for (const ring of coordsArray) {
          for (const c of ring) {
            const [flon, flat] = c
            if (distM(centerLon, centerLat, flon, flat) <= NEARBY_RADIUS_M) { included = true; break }
          }
          if (included) break
        }
        if (included) lineFeatures.push({ type: 'Feature', geometry: g, properties: { ...f.properties, _dsid: dsid } })
      }
    }
  }
  map.getSource('nearby-points-highlight')?.setData({ type: 'FeatureCollection', features: pointFeatures })
  map.getSource('nearby-lines-highlight')?.setData({ type: 'FeatureCollection', features: lineFeatures })
}

// 1km 內據點（尊重「目前可見資料集」與行政區 filter）
function computeNearby(lon, lat) {
  nearbyList.value = collectNearbyPoints(lon, lat, { limit: 50 })
    try { updateCircleAndHighlights(lon, lat) } catch (_) {}
}

function getCurrentCenterLonLat() {
  if (originMode.value === 'search' && lastSearchLonLat.value) return lastSearchLonLat.value
  if (userLonLat.value) return userLonLat.value
  return { lon: TPE_CENTER[0], lat: TPE_CENTER[1] }
}

function computeNearbyForCurrentCenter() {
  if (lastRoadFeatureCollection.value || lastRouteFeatureCollection.value) return
  const c = getCurrentCenterLonLat()
  computeNearby(c.lon, c.lat)
}

// ===== 道路搜尋與施工配對 =====
const roadSuggestions = ref([])
const showRoadSuggestions = ref(false)
const isFetchingRoadSuggestions = ref(false)
const isSearchingRoad = ref(false)
const roadMatchList = ref([])
const showRoadMatches = ref(false)
const showRoadMatchDetail = ref(false)
const selectedRoadMatch = ref(null)
const roadMatchNotice = ref('')
const roadMatchesReady = ref(false)

const routeMatchList = ref([])
const showRouteMatches = ref(false)
const showRouteMatchDetail = ref(false)
const selectedRouteMatch = ref(null)
const routeMatchNotice = ref('')
const routeMatchesReady = ref(false)
const ROAD_CONSTRUCTION_DISTANCE_THRESHOLD = 15
const ROUTE_CONSTRUCTION_DISTANCE_THRESHOLD = 50
const isGlobalSearchButtonDisabled = computed(() => {
  if (searchMode.value === 'place') {
    return !(searchText.value || '').trim()
  }
  if (searchMode.value === 'road') {
    if (isSearchingRoad.value) return true
    return !(roadSearchText.value || '').trim()
  }
  return false
})
let latestRoadSuggestionToken = 0
let skipNextRoadSuggestionFetch = false

function clearRoadSearchData() {
  lastRoadFeatureCollection.value = null
  roadMatchList.value = []
  showRoadMatches.value = false
  showRoadMatchDetail.value = false
  selectedRoadMatch.value = null
  roadMatchNotice.value = ''
  roadMatchesReady.value = false
  if (!map) return
  const src = map.getSource(ROAD_SEARCH_SOURCE_ID)
  if (src) {
    src.setData({ type: 'FeatureCollection', features: [] })
  }
  updateRoadConstructionHighlights([], null)
}

watch(roadSearchText, async (value) => {
  if (searchMode.value !== 'road') return
  if (skipNextRoadSuggestionFetch) {
    skipNextRoadSuggestionFetch = false
    return
  }
  const keyword = value.trim()
  if (!keyword) {
    roadSuggestions.value = []
    showRoadSuggestions.value = false
    return
  }

  const token = ++latestRoadSuggestionToken
  isFetchingRoadSuggestions.value = true
  try {
    const items = await suggestRoadSegments(keyword)
    if (token === latestRoadSuggestionToken) {
      roadSuggestions.value = items
      showRoadSuggestions.value = items.length > 0
    }
  } catch (err) {
    if (token === latestRoadSuggestionToken) {
      console.warn('Failed to fetch road suggestions', err)
      roadSuggestions.value = []
      showRoadSuggestions.value = false
    }
  } finally {
    if (token === latestRoadSuggestionToken) {
      isFetchingRoadSuggestions.value = false
    }
  }
})

function selectRoadSuggestion(name) {
  skipNextRoadSuggestionFetch = true
  roadSearchText.value = name
  showRoadSuggestions.value = false
}

function openRoadSuggestionDropdown() {
  if (searchMode.value !== 'road') return
  if (roadSuggestions.value.length > 0) {
    showRoadSuggestions.value = true
  }
}

function closeRoadSuggestionDropdown() {
  setTimeout(() => {
    showRoadSuggestions.value = false
  }, 150)
}

function pointToSegmentDistanceMeters(plon, plat, a, b) {
  if (!Array.isArray(a) || !Array.isArray(b)) return Number.POSITIVE_INFINITY
  const cosLat = Math.cos(plat * Math.PI / 180)
  const mPerDegLon = 111320 * cosLat
  const mPerDegLat = 110574
  const ax = (a[0] - plon) * mPerDegLon
  const ay = (a[1] - plat) * mPerDegLat
  const bx = (b[0] - plon) * mPerDegLon
  const by = (b[1] - plat) * mPerDegLat
  const dx = bx - ax
  const dy = by - ay
  if (dx === 0 && dy === 0) return Math.hypot(ax, ay)
  const t = -(ax * dx + ay * dy) / (dx * dx + dy * dy)
  if (t <= 0) return Math.hypot(ax, ay)
  if (t >= 1) return Math.hypot(bx, by)
  const projX = ax + t * dx
  const projY = ay + t * dy
  return Math.hypot(projX, projY)
}

function pointToLineStringDistanceMeters(plon, plat, coordinates) {
  if (!Array.isArray(coordinates) || coordinates.length < 2) return Number.POSITIVE_INFINITY
  let min = Number.POSITIVE_INFINITY
  for (let i = 0; i < coordinates.length - 1; i++) {
    const d = pointToSegmentDistanceMeters(plon, plat, coordinates[i], coordinates[i + 1])
    if (d < min) min = d
  }
  return min
}

function collectRoadConstructionMatches(featureCollection, maxDistance = ROAD_CONSTRUCTION_DISTANCE_THRESHOLD) {
  if (!featureCollection || !Array.isArray(featureCollection?.features)) return []
  const constructionDs = datasets.value.find((ds) => ds.id === 'construction')
  if (!constructionDs || !constructionDs.visible) return []
  const cache = datasetCache.get('construction')
  const constructionFeatures = cache?.geo?.features || []
  if (!constructionFeatures.length) return []

  const roadSegments = []
  for (const f of featureCollection.features) {
    const geom = f?.geometry
    if (!geom) continue
    if (geom.type === 'LineString') {
      roadSegments.push(geom.coordinates)
    } else if (geom.type === 'MultiLineString') {
      for (const coords of geom.coordinates || []) roadSegments.push(coords)
    }
  }
  if (!roadSegments.length) return []

  const results = []
  for (const feature of constructionFeatures) {
    const geom = feature?.geometry
    if (!geom || geom.type !== 'Point') continue
    const [lon, lat] = geom.coordinates || []
    if (typeof lon !== 'number' || typeof lat !== 'number') continue

    let minDist = Number.POSITIVE_INFINITY
    for (const coords of roadSegments) {
      const d = pointToLineStringDistanceMeters(lon, lat, coords)
      if (d < minDist) minDist = d
      if (minDist <= maxDistance) break
    }
    if (minDist <= maxDistance) {
      const props = feature.properties || {}
      let name = props['DIGADD'] || props['位置'] || props['name'] || '(未命名)'
      let addr = props['PURP'] || props['地址'] || props['road'] || ''
      results.push({
        dsid: 'construction',
        name,
        addr,
        dist: Math.round(minDist),
        lon,
        lat,
        props,
      })
    }
  }

  results.sort((a, b) => a.dist - b.dist)
  return results
}

function updateRoadConstructionHighlights(matches, featureCollection) {
  if (!map) return
  ensureNearbyCircleLayer()
  const pointFeatures = matches.map((item) => ({
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [item.lon, item.lat] },
    properties: { ...(item.props || {}), dataset: 'construction' },
  }))

  const lineFeatures = []
  for (const f of featureCollection?.features || []) {
    const geom = f?.geometry
    if (!geom) continue
    if (geom.type === 'LineString' || geom.type === 'MultiLineString') {
      lineFeatures.push({
        type: 'Feature',
        geometry: geom,
        properties: { ...(f.properties || {}), dataset: 'road_search' },
      })
    }
  }

  map.getSource('nearby-points-highlight')?.setData({ type: 'FeatureCollection', features: pointFeatures })
  map.getSource('nearby-lines-highlight')?.setData({ type: 'FeatureCollection', features: lineFeatures })
  map.getSource('nearby-circle')?.setData({ type: 'FeatureCollection', features: [] })
  map.getSource('nearby-center')?.setData({ type: 'FeatureCollection', features: [] })
}

function refreshRoadMatches(autoOpen = false) {
  if (!lastRoadFeatureCollection.value) {
    roadMatchNotice.value = ''
    roadMatchesReady.value = false
    return
  }

  const constructionDs = datasets.value.find((ds) => ds.id === 'construction')
  if (!constructionDs || !constructionDs.visible) {
    roadMatchList.value = []
    roadMatchNotice.value = '請在設定中啟用「施工地點」資料集以查看道路施工據點'
    showRoadMatches.value = false
    showRoadMatchDetail.value = false
    selectedRoadMatch.value = null
    roadMatchesReady.value = false
    updateRoadConstructionHighlights([], lastRoadFeatureCollection.value)
    return
  }

  const matches = collectRoadConstructionMatches(lastRoadFeatureCollection.value)
  roadMatchList.value = matches
  roadMatchesReady.value = true

  if (matches.length === 0) {
    roadMatchNotice.value = ''
    showRoadMatches.value = false
    showRoadMatchDetail.value = false
    selectedRoadMatch.value = null
  } else {
    roadMatchNotice.value = ''
    if (autoOpen) {
      showRoadMatches.value = true
      showRoadMatchDetail.value = false
      selectedRoadMatch.value = null
    } else if (showRoadMatchDetail.value && selectedRoadMatch.value) {
      const current = matches.find((item) => item.lon === selectedRoadMatch.value.lon && item.lat === selectedRoadMatch.value.lat)
      if (!current) {
        showRoadMatchDetail.value = false
        selectedRoadMatch.value = null
      }
    }
  }

  updateRoadConstructionHighlights(matches, lastRoadFeatureCollection.value)
}

function refreshRouteMatches(autoOpen = false) {
  if (!lastRouteFeatureCollection.value) {
    routeMatchNotice.value = ''
    routeMatchesReady.value = false
    return
  }

  const constructionDs = datasets.value.find((ds) => ds.id === 'construction')
  if (!constructionDs || !constructionDs.visible) {
    routeMatchList.value = []
    routeMatchNotice.value = '請在設定中啟用「施工地點」資料集以查看路線沿線施工據點'
    showRouteMatches.value = false
    showRouteMatchDetail.value = false
    selectedRouteMatch.value = null
    routeMatchesReady.value = false
    updateRoadConstructionHighlights([], lastRouteFeatureCollection.value)
    return
  }

  const matches = collectRoadConstructionMatches(lastRouteFeatureCollection.value, ROUTE_CONSTRUCTION_DISTANCE_THRESHOLD)
  routeMatchList.value = matches
  routeMatchesReady.value = true

  if (matches.length === 0) {
    routeMatchNotice.value = ''
    showRouteMatches.value = false
    showRouteMatchDetail.value = false
    selectedRouteMatch.value = null
  } else {
    routeMatchNotice.value = ''
    if (autoOpen) {
      showRouteMatches.value = true
      showRouteMatchDetail.value = false
      selectedRouteMatch.value = null
    } else if (showRouteMatchDetail.value && selectedRouteMatch.value) {
      const current = matches.find((item) => item.lon === selectedRouteMatch.value.lon && item.lat === selectedRouteMatch.value.lat)
      if (!current) {
        showRouteMatchDetail.value = false
        selectedRouteMatch.value = null
      }
    }
  }

  updateRoadConstructionHighlights(matches, lastRouteFeatureCollection.value)
}

function openRoadMatchList() {
  if (!roadMatchList.value.length) return
  showRoadMatches.value = true
  showRoadMatchDetail.value = false
  selectedRoadMatch.value = null
}

function closeRoadMatchList() {
  showRoadMatches.value = false
  showRoadMatchDetail.value = false
  selectedRoadMatch.value = null
  const existingPopups = document.querySelectorAll('.mapboxgl-popup')
  existingPopups.forEach((p) => p.remove())
}

function showRoadMatchPopup(item) {
  if (!item || !map) return
  selectedRoadMatch.value = item
  showRoadMatchDetail.value = true
  showRoadMatches.value = true
  const existingPopups = document.querySelectorAll('.mapboxgl-popup')
  existingPopups.forEach((p) => p.remove())
  flyToLngLat(item.lon, item.lat, 16, { bottom: 250 })
  createMapPopup(item.props || {}, 'construction', [item.lon, item.lat])
}

function backToRoadMatchList() {
  showRoadMatchDetail.value = false
  selectedRoadMatch.value = null
  const existingPopups = document.querySelectorAll('.mapboxgl-popup')
  existingPopups.forEach((p) => p.remove())
}

function openRouteMatchList() {
  if (!routeMatchList.value.length) return
  showRouteMatches.value = true
  showRouteMatchDetail.value = false
  selectedRouteMatch.value = null
}

function closeRouteMatchList() {
  showRouteMatches.value = false
  showRouteMatchDetail.value = false
  selectedRouteMatch.value = null
  const existingPopups = document.querySelectorAll('.mapboxgl-popup')
  existingPopups.forEach((p) => p.remove())
}

function showRouteMatchPopup(item) {
  if (!item || !map) return
  selectedRouteMatch.value = item
  showRouteMatchDetail.value = true
  showRouteMatches.value = true
  const existingPopups = document.querySelectorAll('.mapboxgl-popup')
  existingPopups.forEach((p) => p.remove())
  flyToLngLat(item.lon, item.lat, 16, { bottom: 250 })
  createMapPopup(item.props || {}, 'construction', [item.lon, item.lat])
}

function backToRouteMatchList() {
  showRouteMatchDetail.value = false
  selectedRouteMatch.value = null
  const existingPopups = document.querySelectorAll('.mapboxgl-popup')
  existingPopups.forEach((p) => p.remove())
}

async function performRoadSearch() {
  const kw = (roadSearchText.value || '').trim()
  if (!kw) return

  isSearchingRoad.value = true
  try {
    const result = await fetchRoadSegmentsByName(kw)
    showRoadSuggestions.value = false
    const features = Array.isArray(result?.features) ? result.features.filter((f) => f?.geometry) : []
    if (features.length === 0) {
      clearRoadSearchData()
      alert('找不到符合的道路，請確認名稱是否正確')
      return
    }

    const collection = {
      type: 'FeatureCollection',
      features: features.map((f) => ({
        type: 'Feature',
        properties: { ...(f.properties || {}), dataset: 'road_search' },
        geometry: f.geometry,
      })),
    }

    const bounds = computeBounds(collection)
    const fittedBounds = setRoadSearchData(collection, bounds)
    clearSearchMarker()
    selectedPlace.value = null
    originMode.value = 'search'
    showNearby.value = false
    showDetailView.value = false
    selectedNearbyItem.value = null
    const existingPopups = document.querySelectorAll('.mapboxgl-popup')
    existingPopups.forEach((p) => p.remove())
    const constructionDs = datasets.value.find((ds) => ds.id === 'construction')
    if (constructionDs) {
      try { await ensureDatasetLoaded(constructionDs) } catch (_) {}
    }
  lastRoadFeatureCollection.value = collection
    refreshRoadMatches(true)
    if (fittedBounds && !fittedBounds.isEmpty()) {
      const center = fittedBounds.getCenter()
      lastSearchLonLat.value = { lon: center.lng, lat: center.lat }
    }
  } catch (err) {
    console.warn('Failed to search road segments', err)
    alert('搜尋道路資料時發生錯誤，請稍後再試')
  } finally {
    isSearchingRoad.value = false
  }
}

// ===== 地名搜尋（限定台北市邊界）=====
let attractionSearchFeatures = null

function normalizeForMatch(value) {
  return String(value || '')
    .trim()
    .replace(/\s+/g, '')
    .replace(/台/g, '臺')
    .toLowerCase()
}

function buildPlaceResultFromFeature(feature) {
  if (!feature || feature.geometry?.type !== 'Point') return null
  const coords = Array.isArray(feature.geometry?.coordinates) ? feature.geometry.coordinates : null
  if (!coords || coords.length < 2) return null

  const [lonRaw, latRaw] = coords
  const lon = typeof lonRaw === 'number' ? lonRaw : Number(lonRaw)
  const lat = typeof latRaw === 'number' ? latRaw : Number(latRaw)
  if (!Number.isFinite(lon) || !Number.isFinite(lat)) return null

  const props = feature.properties || {}
  const preferredName = props['地點名稱'] || props['位置'] || props['name'] || props['名稱'] || props['NAME'] || ''
  const address = props['地址'] || props['address'] || ''
  const placeLabel = preferredName || address || ''

  return {
    lon,
    lat,
    place: placeLabel,
    addr: address || placeLabel,
    props
  }
}

async function getAttractionFeaturesForSearch() {
  const cache = datasetCache.get('attraction')
  if (cache?.geo?.features) return cache.geo.features
  if (Array.isArray(attractionSearchFeatures)) return attractionSearchFeatures

  const ds = datasets.value.find((item) => item.id === 'attraction')
  if (!ds) return []

  try {
    const geo = await fetch(ds.url).then((r) => r.json())
    const features = Array.isArray(geo?.features) ? geo.features : []
    attractionSearchFeatures = features
    return features
  } catch (err) {
    console.warn('Failed to load attraction dataset for search', err)
    attractionSearchFeatures = []
    return []
  }
}

async function searchInAttractionDataset(kw) {
  const keyword = (kw || '').trim()
  if (!keyword) return null

  const features = await getAttractionFeaturesForSearch()
  if (!features.length) return null

  const normalizedKw = normalizeForMatch(keyword)
  let partialMatch = null

  for (const feature of features) {
    const baseResult = buildPlaceResultFromFeature(feature)
    if (!baseResult) continue
    const props = baseResult.props || {}
    const candidateSet = new Set([
      props['地點名稱'],
      props['位置'],
      props['name'],
      props['名稱'],
      props['NAME'],
      props['地址'],
      props['address'],
      baseResult.place,
      baseResult.addr
    ])
    candidateSet.delete('')

    for (const rawName of candidateSet) {
      if (!rawName) continue
      const normalizedName = normalizeForMatch(rawName)
      if (!normalizedName) continue

      const candidate = { ...baseResult }
      if (!candidate.place) candidate.place = rawName
      if (!candidate.addr) candidate.addr = rawName

      if (normalizedName === normalizedKw) {
        return candidate
      }

      if (!partialMatch && (normalizedName.includes(normalizedKw) || normalizedKw.includes(normalizedName))) {
        partialMatch = candidate
      }
    }
  }

  return partialMatch
}

function flyToLngLat(lon, lat, zoom = 15, padding = {}) {
  // 使用 padding 讓目標點不在正中心，稍微偏上一點，為底部列表留出空間
  // padding 參數只需要傳入想要改變的部分，會與默認值合併
  const defaultPadding = { top: 0, right: 0, bottom: 0, left: 0 }
  const finalPadding = { ...defaultPadding, ...padding }
  
  map?.flyTo({ 
    center: [lon, lat], 
    zoom,
    padding: finalPadding
  })
}

function isInsideTPEBBox(lon, lat) {
  const [w, s, e, n] = TPE_BBOX.split(',').map(Number)
  return lon >= w && lon <= e && lat >= s && lat <= n
}

async function geocodePlaceInTaipei(q) {
  const token = mapboxgl.accessToken
  if (!token) return null

  const url =
    `https://api.mapbox.com/geocoding/v5/mapbox.places/${encodeURIComponent(q)}.json` +
    `?language=zh-Hant&country=tw&types=poi,address,place,locality,neighborhood` +
    `&limit=5&proximity=${TPE_CENTER.join(',')}&bbox=${TPE_BBOX}&fuzzyMatch=true&access_token=${token}`

  try {
    const r = await fetch(url)
    if (!r.ok) return null
    const j = await r.json()
    const feats = j?.features || []
    if (!feats.length) return null

    const kw = q.trim()
    const list = feats.slice().sort((a,b) => {
      const an = (a.text || a.place_name || '')
      const bn = (b.text || b.place_name || '')
      const aHit = an.includes(kw) ? 1 : 0
      const bHit = bn.includes(kw) ? 1 : 0
      if (aHit !== bHit) return bHit - aHit
      return (b.relevance || 0) - (a.relevance || 0)
    })

    for (const f of list) {
      if (f?.center?.length >= 2) {
        const [lon, lat] = f.center
        if (isInsideTPEBBox(lon, lat)) {
          return { lon, lat, place: f.place_name, addr: f.place_name }
        }
      }
    }
    return null
  } catch (_) { return null }
}

async function resolvePlaceCoordinates(kw) {
  const keyword = (kw || '').trim()
  if (!keyword) return null

  const datasetHit = await searchInAttractionDataset(keyword)
  if (datasetHit) {
    return { ...datasetHit, source: 'dataset' }
  }

  const geocodeHit = await geocodePlaceInTaipei(keyword)
  if (geocodeHit) {
    return { ...geocodeHit, source: 'geocode' }
  }

  return null
}

// ===== 搜尋與清除 =====
async function goSearch() {
  if (searchMode.value === 'road') {
    await performRoadSearch()
    return
  }

  if (searchMode.value === 'route') {
    await performRouteSearch()
    return
  }

  // 行政區篩選已移除；改為資料集顯示選單（不需於搜尋時套用）

  const kw = (searchText.value || '').trim()
  if (!kw) return

  const hit = await resolvePlaceCoordinates(kw)
  if (hit) {
    lastSearchLonLat.value = { lon: hit.lon, lat: hit.lat }
    originMode.value = 'search'
    ensureSearchMarkerLayer()
    map.getSource('search-target')?.setData({
      type: 'FeatureCollection',
      features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: [hit.lon, hit.lat] } }]
    })
    flyToLngLat(hit.lon, hit.lat, 16)
    computeNearby(hit.lon, hit.lat)
    pickSelectedPlace(hit)
  } else {
    alert('找不到此地點（或不在台北市範圍內），請輸入更精確的名稱或地址')
    selectedPlace.value = null
  }
}

function pickSelectedPlace({ lon, lat, place, addr, props }) {
  if (typeof lon !== 'number' || typeof lat !== 'number') {
    selectedPlace.value = null
    return
  }
  const name = place || addr || '未命名地點'
  const address = addr || place || ''
  selectedPlace.value = {
    id: `${lon.toFixed(6)},${lat.toFixed(6)}`,
    name,
    address,
    lon,
    lat,
    props: props || {} // 保存完整的 properties，以便收藏時使用
  }
}

function clearSearch() {
  if (searchMode.value === 'road') {
    roadSearchText.value = ''
    roadSuggestions.value = []
    showRoadSuggestions.value = false
    clearRoadSearchData()
    lastSearchLonLat.value = null
    originMode.value = 'gps'
    selectedPlace.value = null
    const c = userLonLat.value || { lon: TPE_CENTER[0], lat: TPE_CENTER[1] }
    if (map) {
      map.flyTo({ center: [c.lon, c.lat], zoom: Math.max(map.getZoom() ?? 0, 14) })
    }
    computeNearby(c.lon, c.lat)
  } else if (searchMode.value === 'route') {
    clearRouteInputs()
    lastSearchLonLat.value = null
    originMode.value = 'gps'
    const c = userLonLat.value || { lon: TPE_CENTER[0], lat: TPE_CENTER[1] }
    if (map) {
      map.flyTo({ center: [c.lon, c.lat], zoom: Math.max(map.getZoom() ?? 0, 14) })
    }
    computeNearby(c.lon, c.lat)
  } else {
    searchText.value = ''
    lastSearchLonLat.value = null
    originMode.value = 'gps'
    clearSearchMarker()
    selectedPlace.value = null
    // 回到 GPS 並以 GPS 為中心重新計算
    const c = userLonLat.value || { lon: TPE_CENTER[0], lat: TPE_CENTER[1] }
    map.flyTo({ center: [c.lon, c.lat], zoom: Math.max(map.getZoom() ?? 0, 14) })
    computeNearby(c.lon, c.lat)
  }
}

// ===== Map 初始化 =====
onMounted(async () => {
  await nextTick()
  // 先獲取 user_id (UUID 字符串)
  userId.value = await getUserIdFromFlutter()
  if (userId.value && typeof window !== 'undefined') {
    try {
      localStorage.setItem('userId', userId.value) // 直接保存字符串
    } catch (e) {}
  }
  // 載入收藏
  await refreshFavorites()
  if (typeof window !== 'undefined') {
    window.addEventListener('map-favorites-updated', refreshFavorites)
  }
  const token = import.meta.env.VITE_MAPBOXTOKEN
  const styleUrl = 'mapbox://styles/mapbox/streets-v12'
  if (!token) {
    console.warn('VITE_MAPBOXTOKEN is missing')
    return
  }
  mapboxgl.accessToken = token

  map = new mapboxgl.Map({
    container: mapEl.value,
    style: styleUrl,
    center: TPE_CENTER,
    zoom: 11
  })

  map.addControl(new mapboxgl.NavigationControl())

  map.on('load', async () => {
    try {
      ensureRoadSearchLayer()
      for (const ds of datasets.value) await ensureDatasetLoaded(ds)
      // 應用初始資料集篩選設定
      applyDatasetFilter()
      ensureUserLayer()
      ensureSearchMarkerLayer()

      // Flutter 訊息接收
      window.receiveLocationFromFlutter = (msg) => handleIncomingMessage(msg)
      if (window.flutterObject && typeof window.flutterObject.addEventListener === 'function') {
        flutterMsgHandler = (e) => handleIncomingMessage(e?.data ?? e)
        try { window.flutterObject.addEventListener('message', flutterMsgHandler) } catch (_) {}
      } else {
        flutterMsgHandler = (e) => handleIncomingMessage(e?.data ?? e)
        window.addEventListener('message', flutterMsgHandler)
      }

      startPollingFlutter(1000)
      
      // 初始化時計算一次附近清單
      computeNearbyForCurrentCenter()
      
      map.resize()
    } catch (err) {
      console.warn('Failed to load datasets:', err)
    }
  })
})

onBeforeUnmount(() => {
  if (typeof window !== 'undefined') {
    window.removeEventListener('map-favorites-updated', refreshFavorites)
  }
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
  if (flutterMsgHandler) {
    if (window.flutterObject && typeof window.flutterObject.removeEventListener === 'function') {
      try { window.flutterObject.removeEventListener('message', flutterMsgHandler) } catch (_) {}
    } else {
      window.removeEventListener('message', flutterMsgHandler)
    }
  }
  try { delete window.receiveLocationFromFlutter } catch (_) {}
  if (map) { map.remove(); map = null }
})
</script>

<template>
  <div class="bg-white min-h-screen">
    <section class="mx-auto flex h-dvh w-full max-w-[720px] flex-col px-3 pb-5 pt-2 overflow-hidden">
      <TopTabs active="map" @select="handleTabSelect" />

      <div class="mt-3 flex flex-1 flex-col overflow-hidden">
        <!-- 搜尋列 -->
        <div class="relative z-10 mb-3 flex w-full items-center">
          <div class="flex flex-1 items-center gap-2">
            <select
              v-model="searchMode"
              class="tp-focus-outline h-11 w-20 rounded-full border border-gray-300 bg-white px-3 text-sm font-medium text-gray-700 shadow-sm"
            >
              <option value="place">地點</option>
              <option value="road">道路</option>
              <option value="route">路線</option>
            </select>

            <div class="flex-1">
              <div v-if="searchMode === 'place'" class="flex items-center gap-2">
                <div class="relative flex-1">
                  <input
                    v-model="searchText"
                    @keyup.enter="goSearch"
                    type="text"
                    placeholder="輸入地點或地址"
                    class="tp-focus-outline w-full rounded-full border border-gray-300 bg-white pl-4 pr-12 py-2.5 text-sm shadow-sm"
                  />
                  <button
                    v-if="searchText"
                    @click="clearSearchText"
                    type="button"
                    class="absolute right-3 top-1/2 flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-full text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
                    title="清除輸入"
                  >
                    <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                    </svg>
                  </button>
                </div>
                <button
                  @click="goSearch"
                  type="button"
                  class="tp-search-btn flex h-10 w-10 items-center justify-center rounded-full border shadow-sm transition-colors"
                  :disabled="isGlobalSearchButtonDisabled"
                  title="搜尋"
                >
                  <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path>
                  </svg>
                </button>
              </div>

              <div v-else-if="searchMode === 'road'" class="flex items-start gap-2">
                <div class="relative flex-1">
                  <input
                    v-model="roadSearchText"
                    @keyup.enter="goSearch"
                    @focus="openRoadSuggestionDropdown"
                    @blur="closeRoadSuggestionDropdown"
                    type="text"
                    placeholder="輸入道路名稱"
                    class="tp-focus-outline w-full rounded-full border border-gray-300 bg-white pl-4 pr-12 py-2.5 text-sm shadow-sm"
                  />
                  <button
                    v-if="roadSearchText"
                    @click="clearSearchText"
                    type="button"
                    class="absolute right-3 top-1/2 flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-full text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
                    title="清除輸入"
                  >
                    <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                    </svg>
                  </button>

                  <div
                    v-if="showRoadSuggestions || isFetchingRoadSuggestions"
                    class="absolute left-0 right-0 top-full mt-2 max-h-56 overflow-y-auto rounded-xl border border-gray-200 bg-white shadow-lg"
                  >
                    <div v-if="isFetchingRoadSuggestions" class="px-4 py-3 text-sm text-gray-500">載入中...</div>
                    <template v-else>
                      <button
                        v-for="name in roadSuggestions"
                        :key="name"
                        type="button"
                        class="tp-suggestion w-full px-4 py-2 text-left text-sm text-gray-700 transition-colors"
                        @mousedown.prevent="selectRoadSuggestion(name)"
                      >
                        {{ name }}
                      </button>
                      <div v-if="roadSuggestions.length === 0" class="px-4 py-3 text-sm text-gray-500">沒有符合的道路</div>
                    </template>
                  </div>
                </div>
                <button
                  @click="goSearch"
                  type="button"
                  class="tp-search-btn flex h-10 w-10 items-center justify-center rounded-full border shadow-sm transition-colors"
                  :disabled="isGlobalSearchButtonDisabled"
                  title="搜尋"
                >
                  <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path>
                  </svg>
                </button>
              </div>

              <!-- 起訖點模式：兩個輸入框 -->
              <div v-else class="grid grid-cols-[1fr_auto] gap-x-2 gap-y-2 items-center">
                <div class="relative">
                  <input
                    v-model="routeStart"
                    @keyup.enter="goSearch"
                    type="text"
                    placeholder="起點地址"
                    class="tp-focus-outline w-full rounded-full border border-gray-300 bg-white pl-4 pr-12 py-2.5 text-sm shadow-sm"
                  />
                  <button
                    v-if="routeStart"
                    @click="clearRouteStart"
                    type="button"
                    class="absolute right-3 top-1/2 flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-full text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
                    title="清除起點"
                  >
                    <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                    </svg>
                  </button>
                </div>
                <button
                  @click="swapRouteEndpoints"
                  type="button"
                  :disabled="!routeStart && !routeEnd"
                  class="tp-swap-btn flex h-10 w-10 items-center justify-center rounded-full border bg-white shadow-sm transition-colors"
                  title="交換起訖點"
                >
                  <svg class="h-5 w-5" viewBox="0 0 24 24" fill="currentColor" stroke="none">
                    <path d="M9 4l-3.5 3.5H8v9h2V7.5h2.5L9 4z"></path>
                    <path d="M15 20l3.5-3.5H16V7h-2v9.5h-2.5L15 20z"></path>
                  </svg>
                </button>
                <div class="relative">
                  <input
                    v-model="routeEnd"
                    @keyup.enter="goSearch"
                    type="text"
                    placeholder="終點地址"
                    class="tp-focus-outline w-full rounded-full border border-gray-300 bg-white pl-4 pr-12 py-2.5 text-sm shadow-sm"
                  />
                  <button
                    v-if="routeEnd"
                    @click="clearRouteEnd"
                    type="button"
                    class="absolute right-3 top-1/2 flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-full text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
                    title="清除終點"
                  >
                    <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                    </svg>
                  </button>
                </div>
                <button
                  @click="goSearch"
                  type="button"
                  class="tp-search-btn flex h-10 w-10 items-center justify-center rounded-full border shadow-sm transition-colors"
                  title="規劃路線"
                  :disabled="!routeStart || !routeEnd"
                >
                  <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path>
                  </svg>
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- 地圖容器 -->
        <div class="relative flex-1 overflow-hidden">
          <div ref="mapEl" class="h-full w-full rounded-2xl border border-gray-200" />

          <!-- 圓形按鈕群組 - 覆蓋在地圖右上角 -->
          <div class="pointer-events-none absolute top-0 right-0 bottom-0 left-0 p-3" style="z-index: 10;">
            <div class="pointer-events-auto flex flex-col gap-2 ml-auto w-fit" style="margin-top: 120px;">
              <!-- 定位按鈕 -->
              <button
                @click="centerOnUserLocation"
                type="button"
                class="tp-icon-btn flex h-11 w-11 items-center justify-center rounded-full shadow-md transition-colors"
                :class="{ 'tp-icon-btn--active': originMode === 'gps' && userLonLat }"
                title="回到我的位置"
              >
                <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="12" cy="12" r="10"></circle>
                  <circle cx="12" cy="12" r="3"></circle>
                  <line x1="12" y1="2" x2="12" y2="4"></line>
                  <line x1="12" y1="20" x2="12" y2="22"></line>
                  <line x1="2" y1="12" x2="4" y2="12"></line>
                  <line x1="20" y1="12" x2="22" y2="12"></line>
                </svg>
              </button>

              <!-- 收藏按鈕 -->
              <button
                @click="toggleFavorite"
                type="button"
                :class="[
                  'flex h-11 w-11 items-center justify-center rounded-full border shadow-md transition-colors',
                  currentFavoriteSaved 
                    ? 'border-red-400 bg-red-50 text-red-500' 
                    : currentFavoriteContext 
                      ? 'border-gray-300 bg-white text-gray-400 hover:bg-gray-50'
                      : 'border-gray-200 bg-gray-50 text-gray-300 cursor-not-allowed'
                ]"
                :disabled="!currentFavoriteContext"
                :title="currentFavoriteContext?.type === 'road' ? '收藏道路' : currentFavoriteContext?.type === 'route' ? '收藏路線' : '收藏地點'"
              >
                <svg v-if="currentFavoriteSaved" class="h-5 w-5" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path>
                </svg>
                <svg v-else class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path>
                </svg>
              </button>

              <!-- 設定按鈕帶下拉選單 -->
              <div class="relative">
                <button
                  @click="showSettingsPanel = !showSettingsPanel"
                  type="button"
                  :class="[
                    'tp-icon-btn flex h-11 w-11 items-center justify-center rounded-full shadow-md transition-colors',
                    showSettingsPanel ? 'tp-icon-btn--active' : ''
                  ]"
                  title="設定"
                >
                  <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"></path>
                    <circle cx="12" cy="12" r="3"></circle>
                  </svg>
                </button>

                <!-- 設定選單：資料集顯示切換 -->
                <div
                  v-if="showSettingsPanel"
                  class="absolute right-0 top-full mt-2 w-56 rounded-lg border border-gray-200 bg-white shadow-lg"
                >
                  <div class="p-3">
                    <div class="mb-2 flex items-center justify-between">
                      <label class="block text-xs font-medium text-gray-600">顯示資料集</label>
                      <div class="flex gap-1">
                        <button
                          @click="selectAllDatasets"
                          type="button"
                          class="tp-link text-xs"
                        >
                          全選
                        </button>
                        <span class="text-xs text-gray-400">|</span>
                        <button
                          @click="deselectAllDatasets"
                          type="button"
                          class="tp-link text-xs"
                        >
                          全不選
                        </button>
                      </div>
                    </div>
                    <div class="space-y-2">
                      <label
                        v-for="ds in datasets"
                        :key="ds.id"
                        class="flex items-center gap-2 cursor-pointer hover:bg-gray-50 rounded px-2 py-1.5"
                      >
                        <input
                          type="checkbox"
                          :checked="enabledDatasets.includes(ds.id)"
                          @change="toggleDatasetCheckbox(ds.id)"
                          class="tp-checkbox h-4 w-4 rounded border border-gray-300"
                        />
                        <span class="text-sm text-gray-700">{{ ds.name }}</span>
                      </label>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 附近列表 -->
          <div class="pointer-events-none absolute inset-x-0 bottom-0 px-2 pb-2">
            <template v-if="routeMatchesReady">
              <div v-if="routeMatchList.length">
                <div v-if="showRouteMatches && showRouteMatchDetail && selectedRouteMatch" class="pointer-events-auto w-full rounded-2xl border border-gray-200 bg-white/95 shadow-sm">
                  <div class="flex items-center justify-between px-4 py-3">
                    <div class="min-w-0 flex-1">
                      <div class="font-medium truncate">{{ selectedRouteMatch.name }}</div>
                      <div class="truncate text-xs text-gray-600">{{ selectedRouteMatch.addr }}</div>
                    </div>
                    <div class="flex items-center gap-3 ml-3">
                      <div class="whitespace-nowrap text-sm font-semibold">距路線 {{ selectedRouteMatch.dist }} 公尺</div>
                    </div>
                  </div>
                  <div class="px-4 pb-3">
                    <button
                      class="w-full rounded border px-3 py-2 text-sm hover:bg-gray-100 transition-colors text-gray-700"
                      @click="backToRouteMatchList"
                    >
                      ← 返回路線施工列表
                    </button>
                  </div>
                </div>
                <div v-else-if="showRouteMatches" class="pointer-events-auto w-full rounded-2xl border border-gray-200 bg-white/95 shadow-sm">
                  <button
                    class="flex w-full items-center justify-between rounded-t-2xl px-4 py-3 text-left font-medium"
                    @click="closeRouteMatchList"
                  >
                    <span>路線沿線施工據點（{{ routeMatchList.length }}）</span>
                    <span class="text-sm text-gray-500">收合</span>
                  </button>
                  <div class="max-h-48 overflow-y-auto px-4 pb-4">
                    <ul class="divide-y">
                      <li
                        v-for="(it, idx) in routeMatchList"
                        :key="idx"
                        class="flex items-center py-2"
                      >
                        <!-- 左側內容: 固定 65%，超出使用 ellipsis -->
                        <div class="min-w-0 w-[65%]">
                          <div class="font-medium truncate">{{ it.name }}</div>
                          <div class="truncate text-xs text-gray-600">{{ it.addr }}</div>
                        </div>
                        <!-- 右側行為區: 固定 35%，靠右對齊 -->
                        <div class="w-[35%] flex items-center justify-end gap-3">
                          <div class="whitespace-nowrap text-sm font-semibold">{{ it.dist }} 公尺</div>
                          <button
                            class="rounded border px-2 py-1 text-xs hover:bg-gray-100 transition-colors"
                            @click="showRouteMatchPopup(it)"
                          >
                            詳細資訊
                          </button>
                        </div>
                      </li>
                    </ul>
                  </div>
                </div>

                <button
                  v-else
                  class="pointer-events-auto mx-auto flex items-center gap-2 rounded-full bg-white/95 px-4 py-2 text-sm font-medium shadow"
                  @click="openRouteMatchList"
                >
                  查看路線施工據點（{{ routeMatchList.length }}）
                </button>
              </div>
              <div v-else class="pointer-events-auto flex w-fit mx-auto flex-col items-center gap-1 rounded-full bg-white/95 px-4 py-2 text-sm font-medium shadow text-center">
                <span class="whitespace-nowrap">路線沿線施工據點（0）</span>
                <span class="text-xs font-normal text-gray-600">{{ ROUTE_CONSTRUCTION_DISTANCE_THRESHOLD }} 公尺內沒有符合條件的據點</span>
              </div>
            </template>
            <template v-else-if="routeMatchNotice">
              <div class="pointer-events-auto mx-auto flex items-center gap-2 rounded-full bg-white/95 px-4 py-2 text-sm font-medium shadow">
                {{ routeMatchNotice }}
              </div>
            </template>
            <template v-else-if="roadMatchesReady">
              <div v-if="roadMatchList.length">
                <div v-if="showRoadMatches && showRoadMatchDetail && selectedRoadMatch" class="pointer-events-auto w-full rounded-2xl border border-gray-200 bg-white/95 shadow-sm">
                  <div class="flex items-center justify-between px-4 py-3">
                    <div class="min-w-0 flex-1">
                      <div class="font-medium truncate">{{ selectedRoadMatch.name }}</div>
                      <div class="truncate text-xs text-gray-600">{{ selectedRoadMatch.addr }}</div>
                    </div>
                    <div class="flex items-center gap-3 ml-3">
                      <div class="whitespace-nowrap text-sm font-semibold">距道路 {{ selectedRoadMatch.dist }} 公尺</div>
                    </div>
                  </div>
                  <div class="px-4 pb-3">
                    <button
                      class="w-full rounded border px-3 py-2 text-sm hover:bg-gray-100 transition-colors text-gray-700"
                      @click="backToRoadMatchList"
                    >
                      ← 返回道路施工列表
                    </button>
                  </div>
                </div>
                <div v-else-if="showRoadMatches" class="pointer-events-auto w-full rounded-2xl border border-gray-200 bg-white/95 shadow-sm">
                  <button
                    class="flex w-full items-center justify-between rounded-t-2xl px-4 py-3 text-left font-medium"
                    @click="closeRoadMatchList"
                  >
                    <span>道路沿線施工據點（{{ roadMatchList.length }}）</span>
                    <span class="text-sm text-gray-500">收合</span>
                  </button>
                  <div class="max-h-48 overflow-y-auto px-4 pb-4">
                    <ul class="divide-y">
                      <li
                        v-for="(it, idx) in roadMatchList"
                        :key="idx"
                        class="flex items-center py-2"
                      >
                        <!-- 左側內容: 固定 65%，超出使用 ellipsis -->
                        <div class="min-w-0 w-[65%]">
                          <div class="font-medium truncate">{{ it.name }}</div>
                          <div class="truncate text-xs text-gray-600">{{ it.addr }}</div>
                        </div>
                        <!-- 右側行為區: 固定 35%，靠右對齊 -->
                        <div class="w-[35%] flex items-center justify-end gap-3">
                          <div class="whitespace-nowrap text-sm font-semibold">{{ it.dist }} 公尺</div>
                          <button
                            class="rounded border px-2 py-1 text-xs hover:bg-gray-100 transition-colors"
                            @click="showRoadMatchPopup(it)"
                          >
                            詳細資訊
                          </button>
                        </div>
                      </li>
                    </ul>
                  </div>
                </div>
                
                <button
                  v-else
                  class="pointer-events-auto mx-auto flex items-center gap-2 rounded-full bg-white/95 px-4 py-2 text-sm font-medium shadow"
                  @click="openRoadMatchList"
                >
                  查看道路施工據點（{{ roadMatchList.length }}）
                </button>
              </div>
              <div v-else class="pointer-events-auto flex w-fit mx-auto flex-col items-center gap-1 rounded-full bg-white/95 px-4 py-2 text-sm font-medium shadow text-center">
                <span class="whitespace-nowrap">道路沿線施工據點（0）</span>
                <span class="text-xs font-normal text-gray-600">{{ ROAD_CONSTRUCTION_DISTANCE_THRESHOLD }} 公尺內沒有符合條件的據點</span>
              </div>
            </template>
            <template v-else-if="roadMatchNotice">
              <div class="pointer-events-auto mx-auto flex items-center gap-2 rounded-full bg-white/95 px-4 py-2 text-sm font-medium shadow">
                {{ roadMatchNotice }}
              </div>
            </template>
            <template v-else>
              <!-- 詳細資訊模式：只顯示一行該筆資料 -->
              <div v-if="showNearby && showDetailView && selectedNearbyItem" class="pointer-events-auto w-full rounded-2xl border border-gray-200 bg-white/95 shadow-sm">
                <div class="flex items-center justify-between px-4 py-3">
                  <div class="min-w-0 flex-1">
                    <div class="font-medium truncate">{{ selectedNearbyItem.name }}</div>
                    <div class="truncate text-xs text-gray-600">{{ selectedNearbyItem.addr }}</div>
                  </div>
                  <div class="flex items-center gap-3 ml-3">
                    <div class="whitespace-nowrap text-sm font-semibold">{{ selectedNearbyItem.dist }} 公尺</div>
                  </div>
                </div>
                <div class="px-4 pb-3">
                  <button
                    class="w-full rounded border px-3 py-2 text-sm hover:bg-gray-100 transition-colors text-gray-700"
                    @click="backToNearbyList"
                  >
                    ← 返回搜尋結果
                  </button>
                </div>
              </div>
              <!-- 正常清單模式 -->
              <div v-else-if="showNearby" class="pointer-events-auto w-full rounded-2xl border border-gray-200 bg-white/95 shadow-sm">
                <button
                  class="flex w-full items-center justify-between rounded-t-2xl px-4 py-3 text-left font-medium"
                  @click="closeNearbyList"
                >
                  <span>距中心點 1 公里內的據點（{{ nearbyList.length }}）</span>
                  <span class="text-sm text-gray-500">收合</span>
                </button>
                <div class="max-h-48 overflow-y-auto px-4 pb-4">
                  <p v-if="!userLonLat && !lastSearchLonLat" class="text-sm text-gray-500">等待 GPS 定位中，或先進行一次搜尋。</p>
                  <ul v-else class="divide-y">
                    <li
                      v-for="(it, idx) in nearbyList"
                      :key="idx"
                      class="flex items-center py-2"
                    >
                      <!-- 左側內容: 固定 65%，超出使用 ellipsis -->
                      <div class="min-w-0 w-[65%]">
                        <div class="font-medium truncate">{{ it.name }}</div>
                        <div class="truncate text-xs text-gray-600">{{ it.addr }}</div>
                      </div>
                      <!-- 右側行為區: 固定 35%，靠右對齊 -->
                      <div class="w-[35%] flex items-center justify-end gap-3">
                        <div class="whitespace-nowrap text-sm font-semibold">{{ it.dist }} 公尺</div>
                        <button
                          class="rounded border px-2 py-1 text-xs hover:bg-gray-100 transition-colors"
                          @click="showNearbyItemPopup(it)"
                        >
                          詳細資訊
                        </button>
                      </div>
                    </li>
                    <li v-if="nearbyList.length === 0" class="py-3 text-sm text-gray-500">
                      1 公里內沒有符合條件的據點
                    </li>
                  </ul>
                </div>
              </div>
              <button
                v-else
                class="pointer-events-auto mx-auto flex items-center gap-2 rounded-full bg-white/95 px-4 py-2 text-sm font-medium shadow"
                @click="showNearby = true"
              >
                查看附近 1 公里內據點（{{ nearbyList.length }}）
              </button>
            </template>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
</style>
