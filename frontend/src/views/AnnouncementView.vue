<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import TopTabs from '@/components/TopTabs.vue'
import AnnouncementContent from '@/components/AnnouncementContent.vue'

const router = useRouter()
const currentTab = ref('announcement')
const activeContentTab = ref('upcoming') // 'upcoming' | 'ongoing'

function selectTab(tab) {
  if (tab === 'map') {
    router.push('/map')
  } else if (tab === 'recommend') {
    router.push('/')
  } else if (tab === 'announcement') {
    currentTab.value = 'announcement'
  }
}

function selectContentTab(tab) {
  activeContentTab.value = tab
}
</script>

<template>
  <div class="bg-white min-h-screen">
    <section class="mx-auto flex h-dvh w-full max-w-[720px] flex-col overflow-hidden px-4 pt-3 pb-5">
      <TopTabs :active="currentTab" @select="selectTab" />

      <!-- 內容選擇器 -->
      <div class="mt-3 flex shrink-0 gap-2 border-b border-gray-200">
        <button
          @click="selectContentTab('upcoming')"
          type="button"
          :class="[
            'px-4 py-2 text-sm font-medium transition-colors',
            activeContentTab === 'upcoming'
              ? 'border-b-2 border-blue-600 text-blue-600'
              : 'text-gray-500 hover:text-gray-700'
          ]"
        >
          即將開始
        </button>
        <button
          @click="selectContentTab('ongoing')"
          type="button"
          :class="[
            'px-4 py-2 text-sm font-medium transition-colors',
            activeContentTab === 'ongoing'
              ? 'border-b-2 border-blue-600 text-blue-600'
              : 'text-gray-500 hover:text-gray-700'
          ]"
        >
          進行中
        </button>
      </div>

      <!-- 內容區域 -->
      <div class="mt-3 flex flex-1 overflow-hidden min-h-0">
        <AnnouncementContent :active-tab="activeContentTab" />
      </div>
    </section>
  </div>
</template>

<style scoped>
</style>
