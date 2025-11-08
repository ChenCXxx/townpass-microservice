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
</script>

<template>
  <nav class="relative flex border-b border-gray-200 bg-white" style="z-index: 100; position: relative;">
    <!-- 地圖 -->
    <button
      type="button"
      class="relative flex-1 py-3 text-center text-base cursor-pointer"
      style="z-index: 101; position: relative;"
      :class="props.active === 'map' ? 'text-blue-900 font-semibold border-b-2 border-blue-900' : 'text-gray-400'"
      @click.stop="select('map')"
    >地圖</button>
    <!-- 公告 -->
    <button
      type="button"
      class="relative flex-1 py-3 text-center text-base cursor-pointer"
      style="z-index: 101; position: relative;"
      :class="props.active === 'announcement' ? 'text-blue-900 font-semibold border-b-2 border-blue-900' : 'text-gray-400'"
      @click.stop="select('announcement')"
    >公告</button>
    <!-- 收藏 -->
    <button
      type="button"
      class="relative flex-1 py-3 text-center text-base cursor-pointer"
      style="z-index: 101; position: relative;"
      :class="props.active === 'recommend' ? 'text-blue-900 font-semibold border-b-2 border-blue-900' : 'text-gray-400'"
      @click.stop="select('recommend')"
    >收藏</button>
    <!-- 偵測 -->
    <button
      type="button"
      class="relative flex-1 py-3 text-center text-base cursor-pointer"
      style="z-index: 101; position: relative;"
      :class="props.active === 'watch' ? 'text-blue-900 font-semibold border-b-2 border-blue-900' : 'text-gray-400'"
      @click.stop="select('watch')"
    >偵測</button>
  </nav>
</template>
