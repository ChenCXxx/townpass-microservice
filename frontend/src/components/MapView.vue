<script setup>
import { computed, onMounted, onBeforeUnmount, ref, createApp, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import MapPopup from './map/MapPopup.vue'
import TopTabs from './TopTabs.vue'
import riskIconUrl from '../assets/icons/risk-icon.svg'
import { suggestRoadSegments, fetchRoadSegmentsByName } from '@/service/api'
const mapEl = ref(null)
let map = null
const router = useRouter()

// ====== Flutter / GPS 互動 ======
let pollTimer = null
let flutterMsgHandler = null
let latestRoadSuggestionToken = 0
let skipNextRoadSuggestionFetch = false

// ====== UI 狀態 ======
const searchMode = ref('place')      // 'place' | 'road' | 'route'
const searchText = ref('')
const roadSearchText = ref('')
const routeStart = ref('')           // 起點輸入
const routeEnd = ref('')             // 終點輸入
const currentRouteGeoJSON = ref(null) // 當前路線的 GeoJSON 資料
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
const roadSuggestions = ref([])
const showRoadSuggestions = ref(false)
const isFetchingRoadSuggestions = ref(false)
const isSearchingRoad = ref(false)

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

// 快取：每個資料集 => { sourceId, layerIds, geo, bounds }
const datasetCache = new Map()
const FAVORITES_STORAGE_KEY = 'mapFavorites'
const favorites = ref([])
const selectedPlace = ref(null)
const NEARBY_RADIUS_M = 1000

function handleTabSelect(tab) {
  if (tab === 'recommend') {
    router.push('/')
    return
  }
  
  if (tab === 'announcement') {
    router.push('/announcement')
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
  const app = createApp(MapPopup, { properties, datasetId })
  app.mount(container)
  
  const popup = new mapboxgl.Popup({
    offset: 8,
    className: 'inset-card-popup'
  })
    .setLngLat(lngLat)
    .setDOMContent(container)
    .addTo(map)
  
  popup.on('close', () => app.unmount())
  
  return popup
}

function attachPopupInteraction(layerId, datasetId) {
  map.on('mouseenter', layerId, () => { map.getCanvas().style.cursor = 'pointer' })
  map.on('mouseleave', layerId, () => { map.getCanvas().style.cursor = '' })
  map.on('click', layerId, (e) => {
    const feature = e?.features?.[0]
    if (!feature) return
    const props = feature.properties || {}
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
  // 創建並顯示 popup
  const props = item.props || {}
  const datasetId = item.dsid || 'attraction' // 從 item 中取得資料集 ID
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

function clearRoadSearchData() {
  if (!map) return
  const src = map.getSource(ROAD_SEARCH_SOURCE_ID)
  if (src) {
    src.setData({ type: 'FeatureCollection', features: [] })
  }
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

const selectedPlaceSaved = computed(() => {
  if (!selectedPlace.value?.id) return false
  return favorites.value.some((f) => f.id === selectedPlace.value.id)
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

function readFavoritesFromStorage() {
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

function refreshFavorites() {
  const list = readFavoritesFromStorage().map((item) => ({
    ...item,
    recommendations: Array.isArray(item?.recommendations) ? item.recommendations : [],
  }))
  list.sort((a, b) => {
    const da = a?.addedAt ? Date.parse(a.addedAt) : 0
    const db = b?.addedAt ? Date.parse(b.addedAt) : 0
    return db - da
  })
  favorites.value = list
}

function saveFavorites(list) {
  if (typeof window === 'undefined') return
  localStorage.setItem(FAVORITES_STORAGE_KEY, JSON.stringify(list))
  window.dispatchEvent(new CustomEvent('map-favorites-updated'))
}

function removeFavoriteById(id) {
  const next = favorites.value.filter((f) => f.id !== id)
  favorites.value = next
  saveFavorites(next)
}

async function toggleSelectedPlaceFavorite() {
  if (!selectedPlace.value) {
    alert('請先搜尋地點')
    return
  }

  if (selectedPlaceSaved.value) {
    removeFavoriteById(selectedPlace.value.id)
    return
  }

  // 確保所有資料集都已載入
  for (const ds of datasets.value) {
    await ensureDatasetLoaded(ds)
  }

  const nearby = collectNearbyPoints(selectedPlace.value.lon, selectedPlace.value.lat, {
    respectVisibility: false,
    respectDistrict: false,
    limit: 50,
  })

  const next = [
    ...favorites.value,
    {
      ...selectedPlace.value,
      // 保留資料集與屬性，供推薦頁分類與顯示使用
      recommendations: nearby.map((r) => ({
        name: r.name,
        addr: r.addr,
        dist: r.dist,
        lon: r.lon,
        lat: r.lat,
        dsid: r.dsid,
        props: r.props || null,
      })),
      addedAt: new Date().toISOString(),
    },
  ]
  favorites.value = next
  saveFavorites(next)
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
    
    // 1. 先將起點和終點轉換成座標
    const startCoords = await geocodePlaceInTaipei(start)
    console.log('起點座標:', startCoords)
    
    const endCoords = await geocodePlaceInTaipei(end)
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
        'circle-color': '#2563eb',
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
        'circle-color': '#ef4444',
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
        // 名稱與內容格式：景點用 館所名稱+地址，施工用 AP_NAME + PURP
        let name = f?.properties?.['館所名稱'] || f?.properties?.['場地名稱'] || '(未命名)'
        let addr = f?.properties?.['地址'] || ''
        if (ds.id === 'construction') {
          const apName = f?.properties?.['AP_NAME'] || f?.properties?.['場地名稱'] || '(未命名)'
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
    const addRiskLayer = () => {
      if (!map.getLayer('nearby-points-highlight-symbol')) {
        map.addLayer({
          id: 'nearby-points-highlight-symbol',
          type: 'symbol',
          source: 'nearby-points-highlight',
          layout: {
            'icon-image': 'risk-icon',
            'icon-size': 0.13,
            'icon-allow-overlap': true,
            'icon-ignore-placement': true
          }
        })
        attachPopupInteraction('nearby-points-highlight-symbol', 'construction')
      }
    }

    try {
      if (!map.hasImage || !map.hasImage('risk-icon')) {
        const img = new Image()
        img.crossOrigin = 'anonymous'
        img.onload = () => {
          try { map.addImage('risk-icon', img) } catch (_) {}
          addRiskLayer()
        }
        img.src = riskIconUrl
      } else {
        addRiskLayer()
      }
    } catch (_) {
      // fallback: still try to add the layer (may render empty until image available)
      addRiskLayer()
    }
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
        'circle-color': '#2563eb',
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
    // only include construction (points) and narrow_street (lines) — but support both types
    for (const f of cache.geo.features || []) {
      if (!f || !f.geometry) continue
      const g = f.geometry
      if (g.type === 'Point') {
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
  const c = getCurrentCenterLonLat()
  computeNearby(c.lon, c.lat)
}

// ===== 地名搜尋（限定台北市邊界）=====
function searchInAttractionDataset(kw) {
  const cache = datasetCache.get('attraction')
  if (!cache) return null
  const feats = cache.geo?.features || []
  const k = kw.trim()
  const f = feats.find(f => {
    const name = String(f?.properties?.['館所名稱'] || '')
    const addr = String(f?.properties?.['地址'] || '')
    return name.includes(k) || addr.includes(k)
  })
  if (f?.geometry?.type === 'Point') {
    const [lon, lat] = f.geometry.coordinates
    return {
      lon,
      lat,
      place: f?.properties?.['館所名稱'] || '',
      addr: f?.properties?.['地址'] || '',
      props: f?.properties || {}
    }
  }
  return null
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

// ===== 搜尋與清除 =====
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
    if (fittedBounds && !fittedBounds.isEmpty()) {
      const center = fittedBounds.getCenter()
      lastSearchLonLat.value = { lon: center.lng, lat: center.lat }
      computeNearby(center.lng, center.lat)
    }
  } catch (err) {
    console.warn('Failed to search road segments', err)
    alert('搜尋道路資料時發生錯誤，請稍後再試')
  } finally {
    isSearchingRoad.value = false
  }
}

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

  // 1) 先查 attraction 的 館所名稱/地址
  const dsHit = searchInAttractionDataset(kw)
  if (dsHit) {
    lastSearchLonLat.value = { lon: dsHit.lon, lat: dsHit.lat }
    originMode.value = 'search'
    ensureSearchMarkerLayer()
    const { lon, lat } = lastSearchLonLat.value
    map.getSource('search-target')?.setData({
      type: 'FeatureCollection',
      features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: [lon, lat] } }]
    })
    flyToLngLat(lon, lat, 16)
    computeNearby(lon, lat)
    pickSelectedPlace({ lon: dsHit.lon, lat: dsHit.lat, place: dsHit.place, addr: dsHit.addr })
    return
  }

  // 2) 找不到才用限定台北市的 geocoding
  const hit = await geocodePlaceInTaipei(kw)
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

function pickSelectedPlace({ lon, lat, place, addr }) {
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
    lat
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
  refreshFavorites()
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
              class="h-11 w-28 rounded-full border border-gray-300 bg-white px-3 text-sm font-medium text-gray-700 shadow-sm focus:border-sky-400 focus:outline-none focus:ring-1 focus:ring-sky-400"
            >
              <option value="place">地點</option>
              <option value="road">道路</option>
              <option value="route">起訖點</option>
            </select>

            <div class="relative flex-1">
              <input
                v-if="searchMode === 'place'"
                v-model="searchText"
                @keyup.enter="goSearch"
                type="text"
                placeholder="輸入地點或地址"
                class="w-full rounded-full border border-gray-300 bg-white pl-4 pr-20 py-2.5 text-sm shadow-sm focus:border-sky-400 focus:outline-none focus:ring-1 focus:ring-sky-400"
              />
              <input
                v-else-if="searchMode === 'road'"
                v-model="roadSearchText"
                @keyup.enter="goSearch"
                @focus="openRoadSuggestionDropdown"
                @blur="closeRoadSuggestionDropdown"
                type="text"
                placeholder="輸入道路名稱"
                class="w-full rounded-full border border-gray-300 bg-white pl-4 pr-20 py-2.5 text-sm shadow-sm focus:border-sky-400 focus:outline-none focus:ring-1 focus:ring-sky-400"
              />
              <!-- 起訖點模式：兩個輸入框 -->
              <div v-else-if="searchMode === 'route'" class="flex flex-col gap-2">
                <input
                  v-model="routeStart"
                  @keyup.enter="goSearch"
                  type="text"
                  placeholder="起點地址"
                  class="w-full rounded-full border border-gray-300 bg-white pl-4 pr-20 py-2.5 text-sm shadow-sm focus:border-sky-400 focus:outline-none focus:ring-1 focus:ring-sky-400"
                />
                <input
                  v-model="routeEnd"
                  @keyup.enter="goSearch"
                  type="text"
                  placeholder="終點地址"
                  class="w-full rounded-full border border-gray-300 bg-white pl-4 pr-20 py-2.5 text-sm shadow-sm focus:border-sky-400 focus:outline-none focus:ring-1 focus:ring-sky-400"
                />
              </div>

              <div v-if="searchMode !== 'route'" class="absolute right-2 top-1/2 flex -translate-y-1/2 items-center gap-1">
                <button
                  v-if="(searchMode === 'road' ? roadSearchText : searchText)"
                  @click="clearSearchText"
                  type="button"
                  class="flex h-7 w-7 items-center justify-center rounded-full text-gray-400 hover:bg-gray-100 hover:text-gray-600"
                  title="清除輸入"
                >
                  <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                  </svg>
                </button>
                <button
                  @click="goSearch"
                  type="button"
                  class="flex h-7 w-7 items-center justify-center rounded-full bg-sky-500 text-white hover:bg-sky-600"
                  :disabled="searchMode === 'road' && isSearchingRoad"
                  :class="{ 'opacity-60 cursor-not-allowed': searchMode === 'road' && isSearchingRoad }"
                  title="搜尋"
                >
                  <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path>
                  </svg>
                </button>
              </div>
              
              <!-- 起訖點模式的搜尋按鈕（獨立顯示） -->
              <div v-else class="mt-2 flex justify-end gap-2">
                <button
                  v-if="routeStart || routeEnd"
                  @click="clearRouteInputs"
                  type="button"
                  class="rounded-full border border-gray-300 bg-white px-4 py-2 text-sm text-gray-600 hover:bg-gray-50"
                >
                  清除
                </button>
                <button
                  @click="goSearch"
                  type="button"
                  class="rounded-full bg-sky-500 px-6 py-2 text-sm text-white hover:bg-sky-600"
                  :disabled="!routeStart || !routeEnd"
                  :class="{ 'opacity-60 cursor-not-allowed': !routeStart || !routeEnd }"
                >
                  規劃路線
                </button>
              </div>

              <div
                v-if="searchMode === 'road' && (showRoadSuggestions || isFetchingRoadSuggestions)"
                class="absolute left-0 right-0 top-full mt-2 max-h-56 overflow-y-auto rounded-xl border border-gray-200 bg-white shadow-lg"
              >
                <div v-if="isFetchingRoadSuggestions" class="px-4 py-3 text-sm text-gray-500">載入中...</div>
                <template v-else>
                  <button
                    v-for="name in roadSuggestions"
                    :key="name"
                    type="button"
                    class="w-full px-4 py-2 text-left text-sm text-gray-700 hover:bg-sky-50"
                    @mousedown.prevent="selectRoadSuggestion(name)"
                  >
                    {{ name }}
                  </button>
                  <div v-if="roadSuggestions.length === 0" class="px-4 py-3 text-sm text-gray-500">沒有符合的道路</div>
                </template>
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
                class="flex h-11 w-11 items-center justify-center rounded-full border border-gray-300 bg-white text-sky-500 shadow-md hover:bg-sky-50 transition-colors"
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
                @click="toggleSelectedPlaceFavorite"
                type="button"
                :class="[
                  'flex h-11 w-11 items-center justify-center rounded-full border shadow-md transition-colors',
                  selectedPlaceSaved 
                    ? 'border-red-400 bg-red-50 text-red-500' 
                    : 'border-gray-300 bg-white text-gray-400 hover:bg-gray-50'
                ]"
                title="收藏地點"
              >
                <svg v-if="selectedPlaceSaved" class="h-5 w-5" viewBox="0 0 24 24" fill="currentColor">
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
                    'flex h-11 w-11 items-center justify-center rounded-full border shadow-md transition-colors',
                    showSettingsPanel 
                      ? 'border-sky-400 bg-sky-50 text-sky-600' 
                      : 'border-gray-300 bg-white text-gray-500 hover:bg-gray-50'
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
                          class="text-xs text-sky-600 hover:text-sky-800"
                        >
                          全選
                        </button>
                        <span class="text-xs text-gray-400">|</span>
                        <button
                          @click="deselectAllDatasets"
                          type="button"
                          class="text-xs text-sky-600 hover:text-sky-800"
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
                          class="h-4 w-4 rounded border-gray-300 text-sky-600 focus:ring-sky-500"
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
                    class="flex items-center justify-between py-2"
                  >
                    <div class="min-w-0">
                      <div class="font-medium truncate">{{ it.name }}</div>
                      <div class="truncate text-xs text-gray-600">{{ it.addr }}</div>
                    </div>
                    <div class="flex items-center gap-3">
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
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
</style>
