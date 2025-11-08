<script setup>
import { defineProps } from 'vue'

const props = defineProps({
  notices: {
    type: Array,
    required: true,
    default: () => []
  }
})

function formatDate(dateStr) {
  if (!dateStr) return ''
  try {
    const date = new Date(dateStr)
    return date.toLocaleDateString('zh-TW')
  } catch {
    return dateStr
  }
}
</script>

<template>
  <div class="flex h-full flex-col">
    <div class="mb-3 flex shrink-0 items-center justify-between">
      <h2 class="text-lg font-semibold text-gray-800">即將開始的施工</h2>
      <span class="text-sm text-gray-500">共 {{ notices.length }} 則</span>
    </div>

    <div v-if="notices.length === 0" class="flex-1 flex items-center justify-center text-center text-gray-500">
      目前沒有即將開始的施工
    </div>

    <ul v-else class="flex-1 space-y-3 overflow-y-auto pr-2">
      <li
        v-for="notice in notices"
        :key="notice.id"
        class="rounded-lg border border-amber-200 bg-amber-50 shadow-sm p-4"
      >
        <div class="flex items-start gap-3">
          <!-- 圖示 -->
          <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-amber-500 text-white">
            <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"></circle>
              <polyline points="12 6 12 12 16 14"></polyline>
            </svg>
          </div>

          <!-- 內容 -->
          <div class="flex-1">
            <h3 class="text-sm font-semibold text-gray-800">{{ notice.name }}</h3>
            <p v-if="notice.road" class="mt-1 text-xs text-gray-600">{{ notice.road }}</p>
            <p v-if="notice.type" class="mt-0.5 text-xs text-gray-500">類型：{{ notice.type }}</p>
            <p v-if="notice.unit" class="mt-0.5 text-xs text-gray-500">單位：{{ notice.unit }}</p>
            
            <div v-if="notice.start_date || notice.end_date" class="mt-2 flex items-center gap-2 text-xs text-amber-700">
              <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
                <line x1="16" y1="2" x2="16" y2="6"></line>
                <line x1="8" y1="2" x2="8" y2="6"></line>
                <line x1="3" y1="10" x2="21" y2="10"></line>
              </svg>
              <span v-if="notice.start_date">{{ formatDate(notice.start_date) }}</span>
              <span v-if="notice.start_date && notice.end_date">至</span>
              <span v-if="notice.end_date">{{ formatDate(notice.end_date) }}</span>
            </div>
            
            <a 
              v-if="notice.url" 
              :href="notice.url" 
              target="_blank"
              class="mt-2 inline-block text-xs text-blue-600 hover:text-blue-800 underline"
            >
              查看詳細資訊 →
            </a>
          </div>
        </div>
      </li>
    </ul>
  </div>
</template>

<style scoped>
</style>

