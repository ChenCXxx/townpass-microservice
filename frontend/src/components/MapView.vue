<script setup>
import { onMounted, onBeforeUnmount, ref, createApp } from 'vue'
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import MapPopup from './map/MapPopup.vue'

const mapEl = ref(null)
let map = null

// ====== Flutter / GPS 互動 ======
let pollTimer = null
let flutterMsgHandler = null

// ====== UI 狀態 ======
const searchText = ref('')
const selectedDistrict = ref('')    // "" = 全部（台北市）
const showNearby = ref(true)
const nearbyList = ref([])
const lastSearchLonLat = ref(null)  // { lon, lat }：最近一次「搜尋中心」
const userLonLat = ref(null)        // { lon, lat }：最新「GPS 定位」
const originMode = ref('gps')       // 'gps' | 'search'

// ====== 台北市行政區（固定清單）=====
const TPE_DISTRICTS = [
  '中正區','大同區','中山區','松山區','大安區','萬華區',
  '信義區','士林區','北投區','內湖區','南港區','文山區'
]
const districtOptions = ref([...TPE_DISTRICTS])

// ====== Mapbox 搜尋邊界限定「台北市」=====
const TPE_CENTER = [121.5654, 25.0330]
/** 台北市大致 bbox（西, 南, 東, 北） */
const TPE_BBOX = '121.457,24.955,121.654,25.201'

// ====== 資料集（點選可顯示/隱藏） ======
const datasets = ref([
  { id: 'accessibility', name: '無障礙據點', url: '/mapData/accessibility_new_tpe.geojson', color: '#10b981', outline: '#064e3b', visible: true },
  { id: 'attraction',    name: '景點',       url: '/mapData/attraction_tpe.geojson',     color: '#f59e0b', outline: '#92400e', visible: false },
])

// 快取：每個資料集 => { sourceId, layerIds, geo, bounds }
const datasetCache = new Map()

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

function attachPopupInteraction(layerId) {
  map.on('mouseenter', layerId, () => { map.getCanvas().style.cursor = 'pointer' })
  map.on('mouseleave', layerId, () => { map.getCanvas().style.cursor = '' })
  map.on('click', layerId, (e) => {
    const feature = e?.features?.[0]
    if (!feature) return
    const props = feature.properties || {}
    const container = document.createElement('div')
    const app = createApp(MapPopup, { properties: props })
    app.mount(container)
    const popup = new mapboxgl.Popup({ offset: 8 })
      .setLngLat(e.lngLat)
      .setDOMContent(container)
      .addTo(map)
    popup.on('close', () => app.unmount())
  })
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
    attachPopupInteraction(lid)
  } else if (geomType.includes('Line')) {
    const lid = `${ds.id}-lines`
    map.addLayer({
      id: lid,
      type: 'line',
      source: sourceId,
      paint: { 'line-color': ds.color, 'line-width': 2 },
      layout: { visibility: ds.visible ? 'visible' : 'none' }
    })
    layerIds.push(lid)
    attachPopupInteraction(lid)
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
    attachPopupInteraction(fillId)
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
function applyDistrictFilter() {
  for (const ds of datasets.value) {
    const cache = datasetCache.get(ds.id)
    if (!cache) continue
    const filter = selectedDistrict.value
      ? ['==', ['get', '行政區'], selectedDistrict.value]
      : null
    for (const lid of cache.layerIds) {
      if (map.getLayer(lid)) map.setFilter(lid, filter)
    }
  }
  computeNearbyForCurrentCenter()
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

// 1km 內據點（尊重「目前可見資料集」與行政區 filter）
function computeNearby(lon, lat) {
  const results = []
  for (const ds of datasets.value) {
    if (!ds.visible) continue
    const cache = datasetCache.get(ds.id)
    if (!cache) continue
    const feats = cache.geo?.features || []
    for (const f of feats) {
      if (selectedDistrict.value && (f?.properties?.['行政區']?.trim() !== selectedDistrict.value)) continue
      const g = f.geometry
      if (!g || g.type !== 'Point') continue
      const [flon, flat] = g.coordinates
      const d = distM(lon, lat, flon, flat)
      if (d <= 1000) {
        results.push({
          dsid: ds.id,
          name: f?.properties?.['館所名稱'] || f?.properties?.['場地名稱'] || '(未命名)',
          addr: f?.properties?.['地址'] || '',
          dist: Math.round(d),
          lon: flon, lat: flat,
          props: f.properties
        })
      }
    }
  }
  results.sort((a,b) => a.dist - b.dist)
  nearbyList.value = results.slice(0, 50)
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
    return { lon, lat, place: f?.properties?.['館所名稱'] || '' }
  }
  return null
}

function flyToLngLat(lon, lat, zoom = 15) {
  map?.flyTo({ center: [lon, lat], zoom })
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
          return { lon, lat, place: f.place_name }
        }
      }
    }
    return null
  } catch (_) { return null }
}

// ===== 搜尋與清除 =====
async function goSearch() {
  applyDistrictFilter() 

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
  } else {
    alert('找不到此地點（或不在台北市範圍內），請輸入更精確的名稱或地址')
  }
}

function clearSearch() {
  searchText.value = ''
  lastSearchLonLat.value = null
  originMode.value = 'gps'
  clearSearchMarker()
  // 回到 GPS 並以 GPS 為中心重新計算
  const c = userLonLat.value || { lon: TPE_CENTER[0], lat: TPE_CENTER[1] }
  map.flyTo({ center: [c.lon, c.lat], zoom: Math.max(map.getZoom() ?? 0, 14) })
  computeNearby(c.lon, c.lat)
}

// ===== Map 初始化 =====
onMounted(async () => {
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
      for (const ds of datasets.value) await ensureDatasetLoaded(ds)
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
    } catch (err) {
      console.warn('Failed to load datasets:', err)
    }
  })
})

onBeforeUnmount(() => {
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
  <section class="h-full flex flex-col">
    <!-- 上排：輸入地址 + 搜尋 + 清除 -->
    <div class="flex items-center gap-2 py-2 px-2 flex-wrap">
      <input
        v-model="searchText"
        @keyup.enter="goSearch"
        type="text"
        placeholder="輸入台北市內的地點或地址（例如：台北101、永康街）"
        class="px-3 py-2 border rounded-md flex-1 min-w-[220px]"
      />
      <button @click="goSearch" class="px-3 py-2 rounded-md bg-blue-600 text-white">搜尋</button>
      <button @click="clearSearch" class="px-3 py-2 rounded-md border">清除</button>
    </div>

    <!-- 下排：行政區選擇 + 圖層開關（僅影響顯示與 1km 清單） -->
    <div class="flex items-center gap-3 py-2 px-2 flex-wrap border-t">
      <select v-model="selectedDistrict" @change="applyDistrictFilter" class="px-3 py-2 border rounded-md">
        <option value="">全部行政區（台北市）</option>
        <option v-for="d in districtOptions" :key="d" :value="d">{{ d }}</option>
      </select>

      <div class="flex items-center gap-4 flex-wrap">
        <label v-for="ds in datasets" :key="ds.id" class="inline-flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            v-model="ds.visible"
            @change="() => { setDatasetVisibility(ds, ds.visible); computeNearbyForCurrentCenter() }"
          />
          <span>{{ ds.name }}</span>
        </label>
      </div>
    </div>

    <!-- 地圖 -->
    <div ref="mapEl" class="flex-1 min-h-[400px]" />

    <!-- 底部 1km 內清單 -->
    <div class="w-full bg-white/90 border-t">
      <button
        class="w-full text-left px-4 py-3 font-medium flex items-center justify-between"
        @click="showNearby = !showNearby"
      >
        <span>距中心點 1 公里內的據點（{{ nearbyList.length }}）</span>
        <span class="text-sm text-gray-500">{{ showNearby ? '收合' : '展開' }}</span>
      </button>
      <div v-if="showNearby" class="max-h-64 overflow-auto px-4 pb-4">
        <p v-if="!userLonLat && !lastSearchLonLat" class="text-sm text-gray-500">等待 GPS 定位中，或先進行一次搜尋。</p>
        <ul v-else>
          <li
            v-for="(it, idx) in nearbyList"
            :key="idx"
            class="py-2 border-b flex items-center justify-between"
          >
            <div class="min-w-0">
              <div class="font-medium truncate">{{ it.name }}</div>
              <div class="text-xs text-gray-600 truncate">{{ it.addr }}</div>
            </div>
            <div class="flex items-center gap-3">
              <div class="text-sm font-semibold whitespace-nowrap">{{ it.dist }} 公尺</div>
              <button
                class="px-2 py-1 text-xs rounded border"
                @click="map && map.flyTo({ center: [it.lon, it.lat], zoom: 16 })"
              >
                前往
              </button>
            </div>
          </li>
          <li v-if="nearbyList.length === 0" class="py-3 text-sm text-gray-500">
            1 公里內沒有符合條件的據點
          </li>
        </ul>
      </div>
    </div>
  </section>
</template>

<style scoped>
/* 可視需要細調手機間距/字級 */
</style>
