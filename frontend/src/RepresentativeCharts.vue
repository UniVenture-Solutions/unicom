<script setup>
import {computed} from 'vue'
import {AreaChart,BarChart} from 'frappe-ui-charts/charts'
import {monthLabel} from './monthLabel'
const props=defineProps({kind:String,series:Object,buckets:Array,formatAmount:Function})
const emit=defineEmits(['select'])
function number(value){if(value===null||value===undefined||value==='')return null;const parsed=Number(value);return Number.isFinite(parsed)?parsed:null}
const data=computed(()=>props.kind==='sales' ? (props.series.points||[]).map(point=>({month:point.month,label:monthLabel(point.month+'-01','',point.month).trim(),amount:number(point.amount)})) : props.buckets.map(bucket=>({bucket:bucket.key,label:bucket.label,amount:number(props.series.buckets[bucket.key]?.amount)})))
const compact=value=>new Intl.NumberFormat('en',{notation:'compact',maximumFractionDigits:1}).format(value)
const valueAxis=computed(()=>({format:value=>props.series.currency+' '+props.formatAmount(String(value)),echartOptions:{axisLabel:{formatter:compact},splitLine:{lineStyle:{color:'#e5e7eb',type:'dashed'}}}}))
const salesStyle={amount:{label:'Net sales',color:'#0b5a94',echartOptions:{areaStyle:{color:'rgba(11,90,148,0.14)'},lineStyle:{width:2}}}}
const ageingStyle={amount:{label:'Outstanding',color:'#0b5a94',echartOptions:{barMaxWidth:24,itemStyle:{borderRadius:[0,3,3,0]}}}}
function select(event){if(props.kind==='ageing' && props.buckets.some(bucket=>bucket.key===event?.row?.bucket))emit('select',event.row.bucket)}
</script>
<template>
<div class="rep-native-chart" style="height:270px;min-width:0;width:100%">
  <AreaChart v-if="kind==='sales'" :data="data" x="label" y="amount" :x-axis="{type:'category'}" :y-axis="valueAxis" :series-config="salesStyle" :show-data-points="true" :echart-options="{animation:false}"/>
  <BarChart v-else :data="data" x="label" y="amount" horizontal :x-axis="{type:'category'}" :y-axis="valueAxis" :series-config="ageingStyle" :echart-options="{animation:false}" @select="select"/>
</div>
</template>
