<script setup>
import { Button } from 'frappe-ui'
defineProps({ title:String, metric:Object, loading:Boolean, error:String, formatAmount:Function })
defineEmits(['retry'])
</script>
<template>
  <section class="min-w-0 rounded-lg border border-gray-200 bg-white p-5 sm:p-6">
    <h2 class="text-base font-medium">{{title}}</h2>
    <p v-if="!metric && !error" role="status" class="mt-3 text-sm text-gray-500">Loading…</p>
    <p v-else-if="error" role="alert" class="mt-3 text-sm text-gray-600">{{error}} <Button size="sm" variant="ghost" @click="$emit('retry')">Retry</Button></p>
    <p v-else-if="!metric?.available" class="mt-3 text-sm text-gray-500">Unavailable with your current accounting access.</p>
    <ul v-else class="mt-3 space-y-3">
      <li v-for="item in metric.items" :key="item.company" class="min-w-0" :title="item.company">
        <p v-if="metric.items.length>1" class="text-xs text-gray-500">{{item.company}}</p>
        <div v-if="item.available" class="mt-1 flex flex-wrap items-baseline gap-2"><span class="text-sm text-gray-600">{{item.currency}}</span><span class="break-all text-2xl font-semibold tabular-nums">{{formatAmount(item.amount)}}</span></div>
        <p v-else class="mt-1 text-sm text-gray-500" title="Required data, category or read access is unavailable.">Unavailable</p>
      </li>
    </ul>
  </section>
</template>
