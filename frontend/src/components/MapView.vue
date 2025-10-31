<script setup>
import { onMounted, onBeforeUnmount, ref } from 'vue'
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'

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


