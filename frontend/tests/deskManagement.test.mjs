import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import vm from 'node:vm'
const source=readFileSync(new URL('../../unicom/public/js/desk.js',import.meta.url),'utf8')
for(const roles of [['Management'],['System Manager']]){
  let refresh,lookups=0
  const buttons=[]
  const document={readyState:'loading',addEventListener(){}}
  const frappe={user_roles:roles,call:async args=>{lookups++;assert.equal(args.method,'unicom.api.source_issue');return {message:{exists:false}}}}
  const jquery=()=>({on:(event,handler)=>{assert.equal(event,'form-refresh.unicom');refresh=handler}})
  vm.runInNewContext(source,{document,frappe,window:{frappe,jQuery:jquery},$:jquery,__:text=>text})
  assert.equal(typeof refresh,'function')
  refresh(null,{doc:{name:'INV-EXAMPLE'},doctype:'Sales Invoice',meta:{},is_new:()=>false,add_custom_button:(label)=>buttons.push(label)})
  await Promise.resolve();await Promise.resolve()
  assert.equal(lookups,roles.includes('Management')?1:0)
  assert.deepEqual(buttons,roles.includes('Management')?['Create issue']:[])
}
console.log('Desk form refresh executes for Management; nonmember has no lookup/button')
