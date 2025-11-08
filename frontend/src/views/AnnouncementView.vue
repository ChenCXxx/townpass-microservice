<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import TopTabs from '@/components/TopTabs.vue'
import UpcomingConstruction from '@/components/UpcomingConstruction.vue'
import OngoingConstruction from '@/components/OngoingConstruction.vue'
import { getConstructionData, getConstructionNotices } from '@/service/api'

const router = useRouter()
const currentTab = ref('announcement')
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

function selectTab(tab) {
  if (tab === 'map') {
    router.push('/map')
  } else if (tab === 'recommend') {
    router.push('/')
  } else if (tab === 'announcement') {
    currentTab.value = 'announcement'
  }
}

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
  <div class="bg-white min-h-screen">
    <section class="mx-auto flex h-dvh w-full max-w-[720px] flex-col overflow-hidden px-4 pt-3 pb-5">
      <TopTabs :active="currentTab" @select="selectTab" />

      <div class="mt-3 flex flex-1 flex-col gap-4 overflow-hidden min-h-0">
        <!-- 即將開始的施工 -->
        <div class="flex h-1/2 flex-col overflow-hidden">
          <UpcomingConstruction :notices="upcomingNotices" />
        </div>

        <!-- 進行中的施工 -->
        <div class="flex h-1/2 flex-col overflow-hidden">
          <OngoingConstruction 
            :notices="ongoingNotices" 
            :loading="loading"
            :error="error"
            :has-upcoming="upcomingNotices.length > 0"
          />
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
</style>

