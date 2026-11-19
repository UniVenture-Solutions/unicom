<script setup>
import { Button } from 'frappe-ui'

defineProps({
  scheduleType: { type: String, required: true },
  disabled: { type: Boolean, default: false },
})
defineEmits(['review', 'dismiss'])
</script>

<template>
  <div class="rounded-md border border-gray-200 bg-gray-50 p-3 text-sm">
    <p>{{ scheduleType === 'Meeting' ? 'Schedule a meeting from this comment?' : 'Schedule a follow-up from this comment?' }}</p>
    <div class="mt-2 flex flex-wrap gap-2">
      <Button size="sm" :disabled="disabled" @click="$emit('review')">Review planned event</Button>
      <Button size="sm" variant="ghost" :disabled="disabled" @click="$emit('dismiss')">Dismiss</Button>
    </div>
  </div>
</template>
