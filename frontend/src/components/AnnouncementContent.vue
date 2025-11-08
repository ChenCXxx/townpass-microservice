<script setup>
import { ref, onMounted, computed } from 'vue'
import { getConstructionData, getConstructionNotices } from '@/service/api'
import UpcomingConstruction from '@/components/UpcomingConstruction.vue'
import OngoingConstruction from '@/components/OngoingConstruction.vue'

const props = defineProps({
  activeTab: {
    type: String,
    required: true,
    default: 'upcoming' // 'upcoming' | 'ongoing'
  }
})

const constructionData = ref([])
const constructionNotices = ref([])
const loading = ref(false)
const error = ref('')

onMounted(async () => {
  await Promise.all([
    loadConstructionData(),
    loadConstructionNotices()
  ])
})

async function loadConstructionData() {
  try {
    const data = await getConstructionData()
    // 取得施工資料並轉換為陣列
    if (data?.features) {
      constructionData.value = data.features.map((f, idx) => ({
        id: idx,
        name: f?.properties?.AP_NAME || f?.properties?.['場地名稱'] || '施工地點',
        purpose: f?.properties?.PURP || f?.properties?.['地址'] || '',
        startDate: f?.properties?.SDATE1 || '',
        endDate: f?.properties?.EDATE1 || '',
        properties: f?.properties || {}
      }))
    }
  } catch (e) {
    console.error('Failed to load construction data:', e)
    constructionData.value = []
  }
}

async function loadConstructionNotices() {
  try {
    loading.value = true
    error.value = ''
    const notices = await getConstructionNotices(0, 500)
    constructionNotices.value = notices || []
  } catch (e) {
    error.value = e?.message || String(e)
    constructionNotices.value = []
  } finally {
    loading.value = false
  }
}

// 分類施工公告：未開始和已開始
const today = new Date()
today.setHours(0, 0, 0, 0)

const upcomingNotices = computed(() => {
  return constructionNotices.value.filter(notice => {
    if (!notice.start_date) return false
    const startDate = new Date(notice.start_date)
    startDate.setHours(0, 0, 0, 0)
    return startDate > today
  }).sort((a, b) => {
    // 按開始日期排序
    const dateA = new Date(a.start_date || 0)
    const dateB = new Date(b.start_date || 0)
    return dateA - dateB
  })
})

const ongoingNotices = computed(() => {
  return constructionNotices.value.filter(notice => {
    if (!notice.start_date) return false
    const startDate = new Date(notice.start_date)
    startDate.setHours(0, 0, 0, 0)
    return startDate <= today
  }).sort((a, b) => {
    // 按開始日期倒序排序（最新的在前）
    const dateA = new Date(a.start_date || 0)
    const dateB = new Date(b.start_date || 0)
    return dateB - dateA
  })
})
</script>

<template>
  <div class="flex h-full flex-col overflow-hidden">
    <!-- 即將開始的施工 -->
    <div v-if="activeTab === 'upcoming'" class="flex h-full flex-col overflow-hidden">
      <UpcomingConstruction :notices="upcomingNotices" />
    </div>

    <!-- 進行中的施工 -->
    <div v-else-if="activeTab === 'ongoing'" class="flex h-full flex-col overflow-hidden">
      <OngoingConstruction 
        :notices="ongoingNotices" 
        :loading="loading"
        :error="error"
        :has-upcoming="upcomingNotices.length > 0"
      />
    </div>
  </div>
</template>

<style scoped>
</style>

