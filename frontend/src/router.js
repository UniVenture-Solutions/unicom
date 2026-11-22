import {createRouter,createWebHistory} from 'vue-router'
const Outlet={render:()=>null}
function home(to){
  const query={...to.query},representative=typeof query.representative==='string'?query.representative:'',view=query.view
  delete query.representative;delete query.view
  if(representative)return {name:'Representative',params:{representativeId:representative},query,hash:to.hash,replace:true}
  return {name:view==='overdue'?'OverdueIssues':view==='all'?'AllIssues':view==='mine'?'Issues':'Dashboard',query,hash:to.hash,replace:true}
}
export const routes=[
  {path:'/',name:'Home',redirect:home},
  {path:'/dashboard',name:'Dashboard',component:Outlet},
  {path:'/issues',name:'Issues',component:Outlet,meta:{view:'mine'}},
  {path:'/issues/overdue',name:'OverdueIssues',component:Outlet,meta:{view:'overdue'}},
  {path:'/issues/all',name:'AllIssues',component:Outlet,meta:{view:'all'}},
  {path:'/issues/:issueId',name:'Issue',component:Outlet},
  {path:'/representatives/:representativeId',name:'Representative',component:Outlet},
  {path:'/:issueId',name:'LegacyIssue',redirect:to=>({name:'Issue',params:{issueId:to.params.issueId},query:to.query,hash:to.hash,replace:true})},
  {path:'/:pathMatch(.*)*',redirect:to=>({name:'Dashboard',query:to.query,hash:to.hash,replace:true})},
]
export function createUniComRouter(history=createWebHistory('/unicom')){
  return createRouter({history,routes})
}
