<script setup>
import { monthLabel } from './monthLabel'
import {RouterLink} from 'vue-router'
const props=defineProps({report:Object,loading:Boolean,error:String,formatAmount:Function})
defineEmits(['retry'])
const salesLabel=value=>monthLabel(value,'Sales','Current Month Sales')
const columns=[{key:'sales',label:'Current Month Sales'},{key:'month_credit',label:'Current Month Credit'},{key:'total_credit',label:'Total Credit'},{key:'balance',label:'Balance'}]
</script>
<template>
<section aria-labelledby="representative-report-heading" class="rounded-lg border border-gray-200 bg-white overflow-hidden">
  <div class="flex items-center justify-between gap-3 px-5 py-4"><h2 id="representative-report-heading" class="text-lg font-semibold">Product representatives</h2><button v-if="error" type="button" class="text-sm underline" @click="$emit('retry')">Retry</button></div>
  <p v-if="loading && !report" role="status" class="px-5 pb-4 text-sm text-gray-500">Loading…</p>
  <p v-else-if="error" role="alert" class="px-5 pb-4 text-sm text-gray-600">{{error}}</p>
  <p v-else-if="!report?.available" class="px-5 pb-4 text-sm text-gray-500">Unavailable with your current access.</p>
  <p v-else-if="!report.items.length" class="px-5 pb-4 text-sm text-gray-500">No product representatives available.</p>
  <div v-else class="overflow-x-auto">
    <table class="w-full text-sm"><thead class="bg-gray-50 text-gray-600"><tr><th scope="col" class="px-5 py-3 text-left font-medium whitespace-nowrap">Product Representative</th><th v-for="column in columns" :key="column.key" scope="col" class="px-4 py-3 text-right font-medium whitespace-nowrap">{{column.key==='sales' ? salesLabel(props.report?.start_date) : column.key==='month_credit' ? salesLabel(props.report?.start_date).replace(/Sales$/,'Credit') : column.label}}</th></tr></thead>
      <tbody class="divide-y divide-gray-100"><tr v-for="row in report.items" :key="row.name" class="hover:bg-gray-50"><th scope="row" class="px-5 py-3 text-left font-medium whitespace-nowrap"><RouterLink :to="{name:'Representative',params:{representativeId:row.name}}" class="text-inherit hover:underline">{{row.label}}</RouterLink></th><td v-for="column in columns" :key="column.key" class="px-4 py-3 text-right tabular-nums whitespace-nowrap" :aria-label="row[column.key]===null ? column.label+': unavailable' : undefined"><div v-for="(entry,index) in row[column.key]||[]" :key="index" :title="entry.company||undefined"><span v-if="entry.currency" class="mr-1 text-xs text-gray-500">{{entry.currency}}</span>{{formatAmount(entry.amount)}}<span v-if="new Set((row[column.key]||[]).map(value=>value.company).filter(Boolean)).size>1" class="ml-1 text-xs text-gray-500">{{entry.company}}</span></div></td></tr></tbody>
      <tfoot v-if="report.totals" class="border-t-2 border-gray-200 bg-gray-50"><tr><th scope="row" class="px-5 py-3 text-left font-semibold">Total</th><td v-for="column in columns" :key="column.key" class="px-4 py-3 text-right font-semibold tabular-nums whitespace-nowrap" :aria-label="report.totals[column.key]===null ? column.label+': unavailable' : undefined"><div v-for="(entry,index) in report.totals[column.key]||[]" :key="index" :title="entry.company||undefined"><span v-if="entry.currency" class="mr-1 text-xs text-gray-500">{{entry.currency}}</span>{{formatAmount(entry.amount)}}<span v-if="new Set((report.totals[column.key]||[]).map(value=>value.company).filter(Boolean)).size>1" class="ml-1 text-xs text-gray-500">{{entry.company}}</span></div></td></tr></tfoot>
    </table>
  </div>
</section>
</template>
