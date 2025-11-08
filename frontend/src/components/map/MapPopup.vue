<script setup>
import { computed } from 'vue'
import fieldMapping from '@/config/fieldMapping.json'

const props = defineProps({
  properties: { type: Object, required: true },
  datasetId: { type: String, default: 'attraction' }
})

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


