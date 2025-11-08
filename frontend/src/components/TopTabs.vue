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
  <nav class="flex border-b border-gray-200 bg-white">
    <button
      type="button"
      class="flex-1 py-3 text-center text-base"
      :class="props.active === 'map' ? 'text-sky-600 font-semibold border-b-2 border-sky-500' : 'text-gray-400'"
      @click="select('map')"
    >地圖</button>
    <button
      type="button"
      class="flex-1 py-3 text-center text-base"
      :class="props.active === 'recommend' ? 'text-sky-600 font-semibold border-b-2 border-sky-500' : 'text-gray-400'"
      @click="select('recommend')"
    >推薦</button>
  </nav>
</template>
