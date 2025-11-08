<script setup>
const props = defineProps({
  active: {
    type: String,
    required: true,
  },
})

const emit = defineEmits(['select'])

function select(tab) {
  emit('select', tab)
}

// 處理觸摸事件（用於移動設備和 Flutter WebView）
function handleTouchStart(tab, event) {
  event.preventDefault()
  event.stopPropagation()
  select(tab)
}

// 處理點擊事件
function handleClick(tab, event) {
  event.preventDefault()
  event.stopPropagation()
  select(tab)
}
</script>

<template>
  <nav class="relative flex border-b border-gray-200 bg-white" style="z-index: 100; position: relative;">
    <!-- 地圖 -->
    <button
      type="button"
      class="relative flex-1 py-3 text-center text-base cursor-pointer tab-button"
      style="z-index: 101; position: relative;"
      :class="props.active === 'map' ? 'text-blue-900 font-semibold border-b-2 border-blue-900' : 'text-gray-400'"
      @click="handleClick('map', $event)"
      @touchstart="handleTouchStart('map', $event)"
    >地圖</button>
    <!-- 公告 -->
    <button
      type="button"
      class="relative flex-1 py-3 text-center text-base cursor-pointer tab-button"
      style="z-index: 101; position: relative;"
      :class="props.active === 'announcement' ? 'text-blue-900 font-semibold border-b-2 border-blue-900' : 'text-gray-400'"
      @click="handleClick('announcement', $event)"
      @touchstart="handleTouchStart('announcement', $event)"
    >公告</button>
    <!-- 收藏 -->
    <button
      type="button"
      class="relative flex-1 py-3 text-center text-base cursor-pointer tab-button"
      style="z-index: 101; position: relative;"
      :class="props.active === 'recommend' ? 'text-blue-900 font-semibold border-b-2 border-blue-900' : 'text-gray-400'"
      @click="handleClick('recommend', $event)"
      @touchstart="handleTouchStart('recommend', $event)"
    >收藏</button>
    <!-- 偵測 -->
    <button
      type="button"
      class="relative flex-1 py-3 text-center text-base cursor-pointer tab-button"
      style="z-index: 101; position: relative;"
      :class="props.active === 'watch' ? 'text-blue-900 font-semibold border-b-2 border-blue-900' : 'text-gray-400'"
      @click="handleClick('watch', $event)"
      @touchstart="handleTouchStart('watch', $event)"
    >偵測</button>
  </nav>
</template>

<style scoped>
.tab-button {
  -webkit-tap-highlight-color: transparent;
  touch-action: manipulation;
  user-select: none;
  -webkit-user-select: none;
  pointer-events: auto;
  outline: none;
}

.tab-button:active {
  opacity: 0.7;
}
</style>
