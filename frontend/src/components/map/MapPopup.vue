<script setup>
import { computed, ref, onMounted, onBeforeUnmount, watch } from 'vue'
import fieldMapping from '@/config/fieldMapping.json'
import { createFavorite, getFavorites, deleteFavorite } from '@/service/api'

const props = defineProps({
  properties: { type: Object, required: true },
  datasetId: { type: String, default: 'attraction' },
  lon: { type: Number, default: null },
  lat: { type: Number, default: null }
})

const emit = defineEmits(['favorite-updated'])

const isFavorited = ref(false)
const isProcessing = ref(false)
const userId = ref(null)

// 測試用的預設 user_id（當沒有 Flutter 環境時使用）
const DEFAULT_TEST_USER_ID = '7f3562f4-bb3f-4ec7-89b9-da3b4b5ff250'

// 監聽收藏更新事件，實時更新收藏狀態
function handleFavoritesUpdated() {
  if (userId.value && props.lon && props.lat) {
    checkFavoriteStatus()
  }
}

// 從 localStorage 或 window 獲取 userId
onMounted(async () => {
  // 嘗試從 localStorage 獲取
  try {
    const stored = localStorage.getItem('userId')
    if (stored && stored.length > 10 && stored !== '1') {
      userId.value = stored
    }
  } catch (e) {}

  // 如果沒有，嘗試從 Flutter 獲取
  if (!userId.value) {
    userId.value = await getUserIdFromFlutter()
  }

  // 如果還是沒有，使用測試用的預設值（開發/測試環境）
  if (!userId.value) {
    console.warn('⚠️ 無法從 Flutter 獲取 user_id，使用測試用的預設值')
    userId.value = DEFAULT_TEST_USER_ID
    try {
      localStorage.setItem('userId', DEFAULT_TEST_USER_ID)
    } catch (e) {}
  }

  // 檢查是否已收藏
  if (userId.value && props.lon && props.lat) {
    await checkFavoriteStatus()
  }

  // 監聽收藏更新事件
  if (typeof window !== 'undefined') {
    window.addEventListener('map-favorites-updated', handleFavoritesUpdated)
  }
})

// 清理事件監聽器
onBeforeUnmount(() => {
  if (typeof window !== 'undefined') {
    window.removeEventListener('map-favorites-updated', handleFavoritesUpdated)
  }
})

// 當 props 或 userId 變化時重新檢查收藏狀態
watch([() => props.lon, () => props.lat, () => props.properties?.id, () => userId.value], async () => {
  if (userId.value && props.lon && props.lat) {
    await checkFavoriteStatus()
  }
})

// 從 Flutter 獲取 user_id
async function getUserIdFromFlutter() {
  return new Promise((resolve) => {
    if (typeof window === 'undefined') {
      resolve(null)
      return
    }
    
    let resolved = false
    
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
        let msg = null
        if (typeof event === 'string') {
          msg = JSON.parse(event)
        } else if (event?.data) {
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
          const id = msg.data?.user_id ?? ''
          
          if (typeof window !== 'undefined') {
            window.removeEventListener('message', handleUserIdMessage)
            if (window.flutterObject?.removeEventListener) {
              window.flutterObject.removeEventListener('message', handleUserIdMessage)
            }
          }
          
          if (id && id.length > 0) {
            console.log('✅ Received user_id from Flutter:', id)
            try {
              localStorage.setItem('userId', id)
            } catch (e) {}
            doResolve(id)
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
      if (resolved) return
      
      try {
        const stored = localStorage.getItem('userId')
        if (stored && stored.length > 10 && stored !== '1') {
          doResolve(stored)
          return
        } else if (stored === '1') {
          localStorage.removeItem('userId')
        }
      } catch (e) {}
      
      // 如果沒有 Flutter 環境，返回測試用的預設值
      console.warn('⚠️ Flutter 環境不可用，使用測試用的預設 user_id')
      doResolve(DEFAULT_TEST_USER_ID)
    }, 1500)
  })
}

// 檢查是否已收藏
async function checkFavoriteStatus() {
  if (!userId.value || !props.lon || !props.lat) return
  
  try {
    const favoritesList = await getFavorites(userId.value)
    const placeId = props.properties?.id || `${props.lon.toFixed(6)},${props.lat.toFixed(6)}`
    
    isFavorited.value = favoritesList.some((fav) => {
      if (fav.type !== 'place') return false
      if (fav.place_data?.id === placeId) return true
      if (fav.lon && fav.lat) {
        const dist = Math.abs(fav.lon - props.lon) + Math.abs(fav.lat - props.lat)
        return dist < 0.0001
      }
      return false
    })
  } catch (error) {
    console.error('Failed to check favorite status:', error)
  }
}

// 切換收藏狀態
async function toggleFavorite() {
  if (!userId.value) {
    alert('無法獲取用戶 ID，請稍後再試')
    return
  }

  if (!props.lon || !props.lat) {
    alert('地點座標資訊不完整')
    return
  }

  if (isProcessing.value) return
  isProcessing.value = true

  try {
    if (isFavorited.value) {
      // 刪除收藏
      const favoritesList = await getFavorites(userId.value)
      const favoriteToRemove = favoritesList.find((fav) => {
        if (fav.type !== 'place') return false
        const placeId = props.properties?.id || `${props.lon.toFixed(6)},${props.lat.toFixed(6)}`
        if (fav.place_data?.id === placeId) return true
        if (fav.lon && fav.lat) {
          const dist = Math.abs(fav.lon - props.lon) + Math.abs(fav.lat - props.lat)
          return dist < 0.0001
        }
        return false
      })

      if (favoriteToRemove?.id) {
        await deleteFavorite(favoriteToRemove.id, userId.value)
        isFavorited.value = false
        emit('favorite-updated')
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new CustomEvent('map-favorites-updated'))
        }
      }
    } else {
      // 創建收藏
      let placeName = props.properties?.name || props.properties?.title || '未命名地點'
      let address = props.properties?.address || props.properties?.addr || placeName
      
      // 如果是 construction 類型，使用 DIGADD 和 PURP 字段
      if (props.datasetId === 'construction') {
        placeName = props.properties?.DIGADD || props.properties?.['位置'] || placeName
        address = props.properties?.PURP || props.properties?.['用途'] || address
      }
      // 如果是 narrow_street 類型，使用 alley_name 字段
      else if (props.datasetId === 'narrow_street') {
        const config = fieldMapping[props.datasetId]
        if (config) {
          // 使用 fieldMapping 中定義的字段名來獲取值
          placeName = props.properties?.alley_name || placeName
          address = props.properties?.alley_name || address
        }
      }
      
      const payload = {
        type: 'place',
        name: placeName,
        address: address,
        lon: props.lon,
        lat: props.lat,
        place_data: {
          id: props.properties?.id || `${props.lon.toFixed(6)},${props.lat.toFixed(6)}`,
          ...props.properties
        },
        notification_enabled: false,
        distance_threshold: 100.0,
      }

      await createFavorite(payload, userId.value)
      isFavorited.value = true
      emit('favorite-updated')
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('map-favorites-updated'))
      }
    }
  } catch (error) {
    console.error('Failed to toggle favorite:', error)
    alert('操作失敗，請稍後再試')
  } finally {
    isProcessing.value = false
  }
}

// 根據資料集類型取得對應的欄位映射
const fieldConfig = computed(() => {
  return fieldMapping[props.datasetId] || fieldMapping.attraction
})

// 格式化值的顯示
function formatValue(value) {
  if (value === null || value === undefined) return '-'
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (typeof value === 'number') {
    // 如果是小數，保留一位小數
    if (value % 1 !== 0) return value.toFixed(1)
    return value.toString()
  }
  // 如果是 JSON 字串，嘗試解析
  if (typeof value === 'string' && value.startsWith('{')) {
    try {
      const parsed = JSON.parse(value)
      if (parsed.roadname && parsed.distance_m) {
        return `${parsed.roadname} (${parsed.distance_m} 公尺)`
      }
      return JSON.stringify(parsed, null, 2)
    } catch {
      return value
    }
  }
  return value
}

// 過濾並排序要顯示的欄位
const displayFields = computed(() => {
  const config = fieldConfig.value
  const fields = []
  
  // 只顯示配置檔案中定義的欄位
  for (const [displayName, fieldKey] of Object.entries(config)) {
    if (props.properties.hasOwnProperty(fieldKey)) {
      fields.push({
        displayName,
        fieldKey,
        value: props.properties[fieldKey]
      })
    }
  }
  
  return fields
})
</script>

<template>
  <div class="bg-white rounded-lg shadow-lg border border-gray-200 overflow-hidden">
    <!-- 收藏按鈕 -->
    <div v-if="lon && lat" class="flex items-center justify-end px-3 py-2 border-b border-gray-100">
      <button
        @click="toggleFavorite"
        type="button"
        :disabled="isProcessing || !userId"
        :class="[
          'flex h-8 w-8 items-center justify-center rounded-full border transition-colors',
          isFavorited
            ? 'border-red-400 bg-red-50 text-red-500'
            : 'border-gray-300 bg-white text-gray-400 hover:bg-gray-50',
          (isProcessing || !userId) ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'
        ]"
        :title="isFavorited ? '取消收藏' : '加入收藏'"
      >
        <svg v-if="isFavorited" class="h-4 w-4" viewBox="0 0 24 24" fill="currentColor">
          <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path>
        </svg>
        <svg v-else class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path>
        </svg>
      </button>
    </div>
    
    <div v-if="displayFields.length === 0" class="p-4 text-center text-gray-500 text-sm">
      無屬性資料
    </div>
    <div v-else class="divide-y divide-gray-100">
      <div v-for="field in displayFields" :key="field.fieldKey" class="px-4 py-2.5 hover:bg-gray-50 transition-colors">
        <div class="flex gap-3 min-w-0">
          <div class="min-w-[88px] text-gray-600 text-sm font-medium shrink-0">
            {{ field.displayName }}
          </div>
          <div class="text-gray-900 text-sm wrap-break-word flex-1 min-w-0">{{ formatValue(field.value) }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 使用 :global() 來定義 Mapbox popup 的外部樣式，但限制在組件範圍內 */
:global(.inset-card-popup .mapboxgl-popup-content) {
  padding: 0;
  background: transparent;
  border: none;
  border-radius: 0;
  box-shadow: none;
}

:global(.inset-card-popup .mapboxgl-popup-tip) {
  display: none;
}

:global(.inset-card-popup .mapboxgl-popup-close-button) {
  position: absolute;
  top: -10px;
  right: -10px;
  width: 24px;
  height: 24px;
  line-height: 24px;
  border-radius: 9999px;
  background: #fff;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15);
  color: #111;
}
</style>


