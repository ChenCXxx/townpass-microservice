<script setup>
import { onMounted, onBeforeUnmount, ref, createApp } from 'vue'
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import MapPopup from './map/MapPopup.vue'

const mapEl = ref(null)
let map = null

onMounted(() => {
  const token = import.meta.env.VITE_MAPBOXTOKEN
  const rawStyle = import.meta.env.VITE_MAPBOXTILE

  let styleUrl = 'mapbox://styles/mapbox/streets-v12'
  if (rawStyle) {
    const v = String(rawStyle).trim()
    if (v.startsWith('mapbox://') || v.startsWith('http')) {
      styleUrl = v
    } else if (v.includes('/')) {
      styleUrl = `mapbox://styles/${v}`
    } else if (v.includes('.')) {
      // allow tileset-like "user.styleid" to be used as style "user/styleid"
      const normalized = v.replace('.', '/')
      styleUrl = `mapbox://styles/${normalized}`
    }
  }

  if (!token) {
    console.warn('VITE_MAPBOXTOKEN is missing')
    return
  }

  mapboxgl.accessToken = token
  map = new mapboxgl.Map({
    container: mapEl.value,
    style: styleUrl,
    center: [121.5654, 25.0330],
    zoom: 11
  })

  map.addControl(new mapboxgl.NavigationControl())

  map.on('error', (e) => {
    console.warn('Mapbox error:', e?.error || e)
  })

  map.on('load', async () => {
    const url = '/mapData/accessibility_new_tpe.geojson'
    try {
      // Fetch once to compute bounds
      const geo = await fetch(url).then(r => r.json())

      if (!map.getSource('accessibility')) {
        map.addSource('accessibility', {
          type: 'geojson',
          data: geo
        })
      }

      // Determine geometry type from first feature
      const first = geo?.features?.[0]
      const geomType = first?.geometry?.type || ''

      if (geomType.includes('Point')) {
        if (!map.getLayer('accessibility-points')) {
          map.addLayer({
            id: 'accessibility-points',
            type: 'circle',
            source: 'accessibility',
            paint: {
              'circle-radius': 6,
              'circle-color': '#10b981',
              'circle-stroke-width': 1,
              'circle-stroke-color': '#064e3b'
            }
          })
        }

        // Interactions for point features
        map.on('mouseenter', 'accessibility-points', () => {
          map.getCanvas().style.cursor = 'pointer'
        })
        map.on('mouseleave', 'accessibility-points', () => {
          map.getCanvas().style.cursor = ''
        })
        map.on('click', 'accessibility-points', (e) => {
          const feature = e?.features?.[0]
          if (!feature) return
          const coords = feature.geometry?.coordinates?.slice?.() || e.lngLat?.toArray?.() || [0, 0]
          const props = feature.properties || {}

          const container = document.createElement('div')
          const app = createApp(MapPopup, { properties: props })
          app.mount(container)

          const popup = new mapboxgl.Popup({ offset: 8 })
            .setLngLat(coords)
            .setDOMContent(container)
            .addTo(map)

          popup.on('close', () => {
            app.unmount()
          })
        })
      } else if (geomType.includes('Line')) {
        if (!map.getLayer('accessibility-lines')) {
          map.addLayer({
            id: 'accessibility-lines',
            type: 'line',
            source: 'accessibility',
            paint: {
              'line-color': '#0ea5e9',
              'line-width': 2
            }
          })
        }
      } else {
        // Polygon family
        if (!map.getLayer('accessibility-fill')) {
          map.addLayer({
            id: 'accessibility-fill',
            type: 'fill',
            source: 'accessibility',
            paint: {
              'fill-color': '#3b82f6',
              'fill-opacity': 0.2
            }
          })
        }
        if (!map.getLayer('accessibility-outline')) {
          map.addLayer({
            id: 'accessibility-outline',
            type: 'line',
            source: 'accessibility',
            paint: {
              'line-color': '#1d4ed8',
              'line-width': 1
            }
          })
        }
      }

      // Fit bounds to data
      const bounds = new mapboxgl.LngLatBounds()
      for (const f of geo.features || []) {
        const g = f.geometry
        if (!g) continue
        if (g.type === 'Point') {
          bounds.extend(g.coordinates)
        } else if (g.type === 'MultiPoint') {
          for (const c of g.coordinates) bounds.extend(c)
        } else if (g.type === 'LineString') {
          for (const c of g.coordinates) bounds.extend(c)
        } else if (g.type === 'MultiLineString' || g.type === 'Polygon') {
          for (const ring of g.coordinates) {
            for (const c of ring) bounds.extend(c)
          }
        } else if (g.type === 'MultiPolygon') {
          for (const poly of g.coordinates) {
            for (const ring of poly) {
              for (const c of ring) bounds.extend(c)
            }
          }
        }
      }
      if (!bounds.isEmpty()) {
        map.fitBounds(bounds, { padding: 40, duration: 500 })
      }
    } catch (err) {
      console.warn('Failed to load GeoJSON:', err)
    }
  })
})

onBeforeUnmount(() => {
  if (map) {
    map.remove()
    map = null
  }
})
</script>

<template>
  <section class="h-full flex flex-col">
    <h1 class="my-3 text-2xl font-semibold">地圖</h1>
    <div ref="mapEl" class="flex-1 min-h-[400px]" />
  </section>
  
  
</template>

<style scoped>
</style>


