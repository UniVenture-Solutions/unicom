<script setup>
import { communicationHint, followUpHint } from './communicationPrompt'
import { ref, reactive, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { Button, FormControl, Dialog, TextEditor, Badge, Avatar, FeatherIcon, ListView, ListFooter, FileUploader, ErrorMessage, Breadcrumbs, Dropdown, Popover, Switch } from 'frappe-ui'

const view=ref('mine'), rows=ref([]), issue=ref(null), people=ref([]), error=ref(''), busy=ref(false), page=ref(0), search=ref(''), filter=ref(''), showNew=ref(false), showLog=ref(false), showEdit=ref(false)
const currentUser=ref(''), sidebarCollapsed=ref(false), pageLength=ref(20), detailsOpen=ref(true), attachmentsOpen=ref(true)
const showDashboard=ref(true), today=ref(new Date())
const todayLabel=computed(()=>new Intl.DateTimeFormat(undefined,{weekday:'long',year:'numeric',month:'long',day:'numeric'}).format(today.value))
const notificationsOpen=ref(false), notificationRows=ref([]), notificationCount=ref(0), notificationHasMore=ref(false), notificationNext=ref(0), notificationLoading=ref(false), notificationOpening=ref(false), notificationError=ref('')
let notificationTimer=null
const detailGrid=ref(null), detailGridWidth=ref(0), detailViewport=ref(window.innerWidth), detailPreferred=ref(null)
const detailMin=280, detailMax=720, mainMin=360, detailStorageKey='unicom.issueDetailsWidth'
const detailLimit=computed(()=>Math.max(detailMin,Math.min(detailMax,detailGridWidth.value ? detailGridWidth.value-mainMin : detailMax)))
const detailWidth=computed(()=>Math.max(detailMin,Math.min(detailPreferred.value ?? (detailViewport.value>=1280?420:350),detailLimit.value)))
let detailObserver=null, detailDrag=null
function updateDetailViewport(){detailViewport.value=window.innerWidth}
function saveDetailWidth(){try{localStorage.setItem(detailStorageKey,String(detailPreferred.value))}catch(_){}}
function resetDetailWidth(){detailPreferred.value=null;try{localStorage.removeItem(detailStorageKey)}catch(_){}}
function setDetailWidth(value){detailPreferred.value=Math.round(Math.max(detailMin,Math.min(value,detailLimit.value)))}
function startDetailResize(event){if(event.button!==0)return;event.preventDefault();detailDrag={id:event.pointerId,x:event.clientX,width:detailWidth.value,previous:detailPreferred.value};event.currentTarget.setPointerCapture(event.pointerId)}
function moveDetailResize(event){if(detailDrag && event.pointerId===detailDrag.id)setDetailWidth(detailDrag.width+detailDrag.x-event.clientX)}
function endDetailResize(event,cancel=false){if(!detailDrag || event.pointerId!==detailDrag.id)return;if(cancel)detailPreferred.value=detailDrag.previous;else saveDetailWidth();detailDrag=null}
function detailResizeKey(event){let target;if(event.key==='ArrowLeft')target=detailWidth.value+20;else if(event.key==='ArrowRight')target=detailWidth.value-20;else if(event.key==='Home')target=detailMin;else if(event.key==='End')target=detailLimit.value;else return;event.preventDefault();setDetailWidth(target);saveDetailWidth()}
watch(detailGrid, element=>{detailObserver?.disconnect();detailObserver=null;if(element){detailGridWidth.value=element.clientWidth;detailObserver=new ResizeObserver(entries=>{detailGridWidth.value=entries[0].contentRect.width});detailObserver.observe(element)}else detailGridWidth.value=0})
const assignDraft=ref([]), assignError=ref(''), assignSaving=ref(false), assignContext=ref(0), assignOpen=ref(false), assignQuery=ref(''), assignSearchOpen=ref(false)
let assignSavePromise=null
const showResolve=ref(false), resolutionNote=ref(''), resolveError=ref('')
const timelineCategories=['Comments','Communications','Notes','Activity']
const timelineSelection=ref(new Set(timelineCategories))
const inlineField=ref(''), inlineValue=ref(''), inlineError=ref(''), inlineEditor=ref(null), inlineKey=ref(0)
const inlineRegion=ref(null), inlineSaving=ref(false), inlineDeferred=ref(false)
let inlineSavePromise=null, inlineOverlay=false, inlineSaveAgain=false
const pendingImages=reactive({})
const hasPendingImages=computed(()=>Object.values(pendingImages).some(Boolean))
const richMenu=[['Paragraph','Heading 2','Heading 3','Heading 4'],'Separator','Bold','Italic','Separator','Bullet List','Numbered List','Separator','Align Left','Align Center','Align Right','FontColor','Separator','Link','Blockquote','Code','Horizontal Rule',['InsertTable','AddColumnBefore','AddColumnAfter','DeleteColumn','AddRowBefore','AddRowAfter','DeleteRow','MergeCells','SplitCell','ToggleHeaderColumn','ToggleHeaderRow','ToggleHeaderCell','DeleteTable']]
const communicationPrompts=ref({})
const commentBody=ref(''), commentError=ref(''), commentEditorKey=ref(0)
const commentEditor=ref(null), replyEditor=ref(null)
const replyRoot=ref(null), replyBody=ref(''), replyError=ref(''), replyEditorKey=ref(0), replyWindowSizes=ref({})
watch(() => issue.value?.name, () => { communicationPrompts.value={};showLog.value=false; commentBody.value=''; commentError.value=''; commentEditorKey.value++; replyRoot.value=null; replyBody.value=''; replyError.value=''; replyEditorKey.value++; replyWindowSizes.value={}; timelineSelection.value=new Set(timelineCategories); for(const controller of pasteControllers.values())controller.abort();pasteControllers.clear();for(const key of Object.keys(pendingImages)) delete pendingImages[key]; pendingImageTargets.clear(); inlineField.value=''; inlineValue.value=''; inlineError.value=''; inlineDeferred.value=false; inlineOverlay=false; inlineSaveAgain=false;assignContext.value++;assignDraft.value=participantsFor(issue.value);assignError.value='';assignOpen.value=false;assignQuery.value='';assignSearchOpen.value=false;showResolve.value=false;resolutionNote.value='';resolveError.value='' }, {flush:'sync'})
const blank=()=>({title:'',description:'',accountable_owner:'',coordination_user:'',next_action:'',next_action_date:'',participants:[],follow_up_assignees:[]})
const form=reactive(blank()), edit=reactive({}), log=reactive({channel:'Internal Note',happened_at:'',contact:'',body:'',next_action:'',next_action_date:'',resolution_note:'',source_comment:null,set_follow_up:false})
const columns = [{label:'Issue ID',key:'issue_id',width:'1.3fr'},{label:'Issue',key:'title',width:'3fr'},{label:'Status',key:'status',width:'1.5fr'},{label:'Issue Owner',key:'accountable_owner',width:'2fr'},{label:'Next action date',key:'next_action_date',width:'1.5fr'}]
const safeInlineError = computed(() => { const el=document.createElement('div'); el.textContent=inlineError.value; return el.innerHTML })
const safeError = computed(() => { const el=document.createElement('div'); el.textContent=error.value; return el.innerHTML })
const safeCommentError = computed(() => { const el=document.createElement('div'); el.textContent=commentError.value; return el.innerHTML })
const safeReplyError = computed(() => { const el=document.createElement('div'); el.textContent=replyError.value; return el.innerHTML })
const timelineThreads = computed(() => { const events=issue.value?.timeline || []; const replies=new Map(); for(const event of events) if(event.reply_to){if(!replies.has(event.reply_to)) replies.set(event.reply_to,[]); replies.get(event.reply_to).push(event)} return events.filter(event=>!event.reply_to).reverse().map(event=>({event,replies:replies.get(event.name)||[]})) })
const allTimelineSelected=computed(()=>timelineSelection.value.size===timelineCategories.length)
function timelineCategory(event){if(event.kind==='Comment')return 'Comments';if(event.kind==='Communication')return event.channel==='Internal Note'?'Notes':'Communications';return 'Activity'}
const filteredThreads=computed(()=>timelineThreads.value.filter(thread=>timelineSelection.value.has(timelineCategory(thread.event))))
const hiddenReplyDraft=computed(()=>!!replyRoot.value && !filteredThreads.value.some(thread=>thread.event.name===replyRoot.value))
function selectAllTimeline(){if(!hasPendingImages.value)timelineSelection.value=new Set(timelineCategories)}
function toggleTimelineCategory(category){if(hasPendingImages.value)return;const next=allTimelineSelected.value?new Set():new Set(timelineSelection.value);if(next.has(category))next.delete(category);else next.add(category);timelineSelection.value=next}
const statuses=['Open','In Progress','Waiting','Resolved'], channels=['Internal Note','Call','Meeting','Email','WhatsApp']
const userOptions=computed(()=>[{label:'Select user',value:''},...people.value.map(p=>({label:p.full_name+' ('+p.name+')',value:p.name}))])
const coordinationOptions=computed(()=>[{label:'Select user',value:''},...people.value.filter(p=>p.user_type==='System User').map(p=>({label:p.full_name+' ('+p.name+')',value:p.name}))])
const inlineCoordinationOptions=computed(()=>{const options=coordinationOptions.value;const current=issue.value?.coordination_user;if(current && !options.some(o=>o.value===current))return [...options,{label:authorName(current)+' (unavailable)',value:current}];return options})
const editCoordinationOptions=computed(()=>{const options=coordinationOptions.value;const current=edit.coordination_user;if(current && !options.some(o=>o.value===current)) return [...options,{label:authorName(current)+' (unavailable)',value:current}];return options})
const assignmentOptions=computed(()=>{
  const options=people.value.map(p=>({label:p.full_name+' ('+p.name+')',value:p.name}))
  const extras=[...assignDraft.value,...(issue.value?.access||[]).filter(x=>x.reason==='Participant').map(x=>x.user),currentUser.value]
  for(const user of extras)if(user && user!=='Guest' && !options.some(o=>o.value===user))options.push({label:authorName(user)+' ('+user+')'+(user===currentUser.value?'':' (unavailable)'),value:user})
  return options
})
const filteredAssignmentOptions=computed(()=>{const q=assignQuery.value.trim().toLowerCase();const matches=assignmentOptions.value.filter(option=>!q || option.label.toLowerCase().includes(q) || option.value.toLowerCase().includes(q));const selected=matches.filter(option=>assignDraft.value.includes(option.value));const others=matches.filter(option=>!assignDraft.value.includes(option.value));return [...selected,...others.slice(0,Math.max(0,50-selected.length))]})
const safeAssignError=computed(()=>{const el=document.createElement('div');el.textContent=assignError.value;return el.innerHTML})
const safeResolveError=computed(()=>{const el=document.createElement('div');el.textContent=resolveError.value;return el.innerHTML})
const mentionOptions=computed(()=>people.value.map(p=>({value:p.name,label:p.full_name})))
const followup=ref(''), editParticipant=ref(''), editFollowup=ref('')
function add(list, value){if(value && !list.includes(value)) list.push(value)}
function goDesk(){location.assign('/app')}
function openHelp(){window.open('https://docs.frappe.io/framework/user/en', '_blank', 'noopener,noreferrer')}
function logout(){location.assign('/api/method/logout')}
function csrf(){return window.csrf_token || (document.cookie.match(/(?:^|; )csrf_token=([^;]+)/)||[])[1] || ''}
async function api(method, data={}, post=false){
  const opts={method:post?'POST':'GET',headers:{'Content-Type':'application/json','X-Frappe-CSRF-Token':csrf()},credentials:'same-origin'}
  let url='/api/method/unicom.api.'+method
  if(post) opts.body=JSON.stringify(data); else url+='?'+new URLSearchParams(data)
  const res=await fetch(url,opts), result=await res.json(); if(!res.ok){let msg=result.exception || 'Request failed'; try { const m=JSON.parse(result._server_messages || '[]'); if(m.length) msg=JSON.parse(m[0]).message } catch {} throw new Error(msg)} return result.message
}
async function run(fn){busy.value=true; error.value=''; try{await fn()}catch(e){error.value=e.message}finally{busy.value=false}}
async function refreshNotifications(reset=true){
  if(notificationLoading.value || notificationOpening.value)return
  notificationLoading.value=true;notificationError.value=''
  try{
    const result=await api('list_notifications',{start:reset?0:notificationNext.value,page_length:20})
    if(!result || !Array.isArray(result.items))throw new Error('Invalid notification response')
    notificationRows.value=reset?result.items:[...new Map([...notificationRows.value,...result.items].map(row=>[row.name,row])).values()]
    notificationCount.value=result.unread_count;notificationHasMore.value=result.has_more;notificationNext.value=result.next_start
  }catch(_){notificationError.value='Could not load notifications. Please try again.'}
  finally{notificationLoading.value=false}
}
function notificationFocus(){if(!document.hidden){today.value=new Date();if(!notificationOpening.value)refreshNotifications()}}
function toggleNotifications(togglePopover){if(notificationsOpen.value){togglePopover(false);return}togglePopover(true);refreshNotifications()}
async function openNotification(row){
  if(notificationOpening.value)return
  notificationOpening.value=true;notificationError.value=''
  try{
    await open(row.issue_name)
    if(issue.value?.name!==row.issue_name)return
    await api('mark_notification_read',{name:row.name},true)
    const current=notificationRows.value.find(item=>item.name===row.name)
    if(current && !current.read){current.read=true;notificationCount.value=Math.max(0,notificationCount.value-1)}
    notificationsOpen.value=false
  }catch(_){notificationError.value='Could not mark this notification as read. Please try again.'}
  finally{notificationOpening.value=false}
}
async function load(){await run(async()=>{rows.value=await api('list_issues',{view:view.value,status:filter.value,search:search.value,start:page.value*pageLength.value,page_length:pageLength.value})})}
function setPageLength(value){pageLength.value=value;page.value=0;load()}
async function canLeaveInline(){if(assignSavePromise && !await assignSavePromise)return false;if(assignmentDirty.value)return false;if(inlineDeferred.value || hasPendingImages.value)return false;const name=issue.value?.name;if(inlineSavePromise && !await inlineSavePromise)return false;if(issue.value?.name!==name)return false;return !inlineField.value || inlineValue.value===(issue.value?.[inlineField.value]||'') || window.confirm('Discard your unsaved issue edit?')}
async function open(name,push=true,skipGuard=false){if(!skipGuard && issue.value?.name!==name && !await canLeaveInline())return;await run(async()=>{issue.value=await api('get_issue',{name});showDashboard.value=false;if(!notificationOpening.value)refreshNotifications(); if(push) history.pushState({},'', '/unicom/'+encodeURIComponent(name))})}
function listRoute(v){return '/unicom?view='+encodeURIComponent(v)}
function currentRoute(){return issue.value?'/unicom/'+encodeURIComponent(issue.value.name):showDashboard.value?'/unicom':listRoute(view.value)}
function locationView(){const name=decodeURIComponent(location.pathname.replace(/^\/unicom\/?/,''));const requested=new URLSearchParams(location.search).get('view');return name?{name}:['mine','overdue','all'].includes(requested)?{view:requested}:{dashboard:true}}
async function applyLocation(){const target=locationView();if(target.name){await open(target.name,false,true);return}issue.value=null;error.value='';page.value=0;showDashboard.value=!!target.dashboard;if(target.view){view.value=target.view;await load()}}
async function goDashboard(){if(!await canLeaveInline())return;issue.value=null;showDashboard.value=true;today.value=new Date();error.value='';history.pushState({},'','/unicom')}
async function goList(v){if(!await canLeaveInline())return;view.value=v;showDashboard.value=false;issue.value=null;page.value=0;history.pushState({},'',listRoute(v));load()}
function resetForm(){Object.assign(form,blank())}
async function create(){if(!await canLeaveInline())return;await run(async()=>{const doc=await api('create_issue',form,true);showNew.value=false;resetForm();showDashboard.value=false;issue.value=doc;history.pushState({},'','/unicom/'+encodeURIComponent(doc.name))})}
function editDescription(event){if(event.target.closest('a'))return;if(event.type==='keydown')event.preventDefault();startInline('description')}
async function startInline(field){
  if(inlineField.value===field)return
  if(inlineField.value && !await saveInline())return
  if(!issue.value || busy.value)return
  inlineKey.value++;inlineField.value=field;inlineValue.value=issue.value[field]||'';inlineError.value='';inlineOverlay=false
  await nextTick()
  if(inlineField.value===field){if(field==='description')inlineEditor.value?.editor?.commands.focus();else inlineRegion.value?.querySelector('input,select')?.focus()}
}
function cancelInline(){if(inlineSaving.value || hasPendingImages.value)return;inlineField.value='';inlineValue.value='';inlineError.value='';inlineDeferred.value=false;inlineOverlay=false}
async function saveInline(){
  if(inlineSavePromise)return inlineSavePromise
  if(!inlineField.value)return true
  if(hasPendingImages.value){inlineDeferred.value=true;return false}
  if(busy.value)return false
  const name=issue.value?.name,field=inlineField.value,key=inlineKey.value,value=inlineValue.value
  if(value===(issue.value?.[field]||'')){cancelInline();return true}
  inlineSaving.value=true;busy.value=true;inlineError.value=''
  inlineSavePromise=(async()=>{
    let succeeded=false
    try{
      const updated=await api('update_issue',{name,values:{[field]:value}},true)
      if(issue.value?.name!==name || inlineField.value!==field || inlineKey.value!==key)return false
      issue.value=updated;succeeded=true
      if(inlineValue.value===value){inlineField.value='';inlineValue.value='';inlineOverlay=false;return true}
      return false
    }catch(e){if(issue.value?.name===name && inlineField.value===field && inlineKey.value===key)inlineError.value=e.message;return false}
    finally{busy.value=false;inlineSaving.value=false;inlineSavePromise=null;if(inlineSaveAgain){inlineSaveAgain=false;if(succeeded)nextTick(()=>saveInline())}}
  })()
  return inlineSavePromise
}
function inlineInteraction(event){
  if(!inlineField.value)return
  const target=event.target
  if(!(target instanceof Element) || target===document.body || target===document.documentElement)return
  if(inlineRegion.value?.contains(target)){
    if(inlineField.value==='description' && target.closest('.inline-flex'))inlineOverlay=true
    return
  }
  // The active @ picker is portalled to body; selecting it is still an editor interaction.
  if(inlineField.value==='description' && target.closest('[data-tippy-root]') && inlineEditor.value?.editor?.view.dom.querySelector('.suggestion[data-decoration-id]'))return
  if(inlineField.value==='description' && inlineOverlay && (target.closest('#frappeui-popper-root') || target.closest('[role=dialog]')))return
  inlineOverlay=false
  if(inlineSaving.value)inlineSaveAgain=true;else saveInline()
}
function onInlineFocusOut(){setTimeout(()=>{const active=document.activeElement;if(active && active!==document.body && active!==document.documentElement)inlineInteraction({target:active})},0)}
function setInlineEditor(component){inlineEditor.value=component;labelEditor(component,inlineEditor,'description-editor-label','description')}
async function editIssue(){if(assignSavePromise && !await assignSavePromise)return false;if(assignmentDirty.value)return false;if(inlineField.value && !await saveInline())return false;Object.assign(edit,{title:issue.value.title,description:issue.value.description||'',accountable_owner:issue.value.accountable_owner,coordination_user:issue.value.coordination_user||'',status:issue.value.status,next_action:issue.value.next_action||'',next_action_date:issue.value.next_action_date||'',resolution_note:issue.value.resolution_note||'',participants:issue.value.access.filter(x=>x.reason==='Participant').map(x=>x.user),follow_up_assignees:issue.value.access.filter(x=>x.reason==='Follow-up').map(x=>x.user)});showEdit.value=true;return true}
watch(issue,doc=>{if(!assignSaving.value && !assignError.value)assignDraft.value=participantsFor(doc)},{flush:'sync'})
function participantsFor(doc){return [...new Set((doc?.access||[]).filter(row=>row.reason==='Participant' && row.user).map(row=>row.user))]}
function sameParticipants(a,b){return a.length===b.length && a.every(user=>b.includes(user))}
const assignmentDirty=computed(()=>!sameParticipants(assignDraft.value,participantsFor(issue.value)))
async function openAssignments(togglePopover){
  if(assignOpen.value){togglePopover(false);return}
  const name=issue.value?.name
  if(inlineField.value && !await saveInline())return
  if(!issue.value || issue.value.name!==name || (busy.value && !assignSaving.value))return
  assignQuery.value='';assignSearchOpen.value=false;togglePopover(true)
}
function setAssignment(users){
  assignDraft.value=[...new Set(users)]
  assignError.value=''
  saveAssignments()
}
function toggleAssignment(user){setAssignment(assignDraft.value.includes(user)?assignDraft.value.filter(value=>value!==user):[...assignDraft.value,user])}
function toggleAssignMe(){if(currentUser.value && currentUser.value!=='Guest')toggleAssignment(currentUser.value)}
async function saveAssignments(){
  if(assignSavePromise)return assignSavePromise
  if(!issue.value)return false
  if(!assignmentDirty.value){assignError.value='';return true}
  if(busy.value && !assignSaving.value){assignError.value='Please wait and retry.';return false}
  const name=issue.value.name,context=assignContext.value
  assignSaving.value=true;busy.value=true;assignError.value=''
  assignSavePromise=(async()=>{
    try{
      while(issue.value?.name===name && assignContext.value===context){
        const participants=[...assignDraft.value]
        if(sameParticipants(participants,participantsFor(issue.value)))return true
        const updated=await api('update_issue',{name,values:{participants}},true)
        if(issue.value?.name!==name || assignContext.value!==context)return false
        issue.value=updated
      }
      return false
    }catch(e){if(issue.value?.name===name && assignContext.value===context)assignError.value=e.message;return false}
    finally{assignSaving.value=false;busy.value=false;assignSavePromise=null}
  })()
  return assignSavePromise
}
async function resolveIssue(){
  if(busy.value || !issue.value)return
  if(!resolutionNote.value.trim()){resolveError.value='Resolution note is required';return}
  const name=issue.value.name,note=resolutionNote.value
  busy.value=true;resolveError.value=''
  try{const updated=await api('update_issue',{name,values:{status:'Resolved',resolution_note:note}},true);if(issue.value?.name===name){issue.value=updated;showResolve.value=false;resolutionNote.value=''}}
  catch(e){if(issue.value?.name===name)resolveError.value=e.message}
  finally{busy.value=false}
}
function statusColor(status){return ({Open:'bg-blue-500','In Progress':'bg-amber-500',Waiting:'bg-orange-500',Resolved:'bg-green-500'})[status]||'bg-gray-500'}
async function changeStatus(status){
  if(!issue.value || !statuses.includes(status))return
  const name=issue.value.name
  if(inlineField.value && !await saveInline())return
  if(busy.value || issue.value?.name!==name || issue.value.status===status)return
  if(status==='Resolved'){resolutionNote.value='';resolveError.value='';showResolve.value=true;return}
  await run(async()=>{const updated=await api('update_issue',{name,values:{status}},true);if(issue.value?.name===name)issue.value=updated})
}
async function saveEdit(){await run(async()=>{issue.value=await api('update_issue',{name:issue.value.name,values:edit},true);showEdit.value=false})}
async function logIssue(channel='Internal Note'){if(assignSavePromise && !await assignSavePromise)return;if(assignmentDirty.value)return;if(inlineField.value && !await saveInline())return;Object.assign(log,{channel,happened_at:new Date(Date.now()-new Date().getTimezoneOffset()*60000).toISOString().slice(0,16),contact:'',body:'',next_action:'',next_action_date:'',resolution_note:'',source_comment:null,set_follow_up:false});showLog.value=true;return true}
async function saveLog(){await run(async()=>{const dom=new DOMParser().parseFromString(log.body,'text/html'); const mentions=[...dom.querySelectorAll('[data-type="mention"][data-id]')].map(x=>x.getAttribute('data-id'));const name=issue.value.name;const updated=await api('log_communication',{name,...log,mentions},true);if(issue.value?.name===name){issue.value=updated;if(log.source_comment)delete communicationPrompts.value[log.source_comment];showLog.value=false}})}
async function logFromComment(event){
  const name=issue.value.name
  if(!await logIssue() || issue.value?.name!==name)return
  const hint=communicationPrompts.value[event.name]
  if(!hint){showLog.value=false;return}
  Object.assign(log,{channel:hint.channel,happened_at:'',contact:hint.contact,body:event.body,next_action:'',next_action_date:hint.followUpDate,source_comment:event.name,set_follow_up:false})
}
function submitShortcut(event,root=null){
  if(event.key!=='Enter' || !(event.metaKey || event.ctrlKey) || event.isComposing || event.keyCode===229)return
  event.preventDefault()
  if(event.repeat || busy.value || hasPendingImages.value)return
  if(root)saveReply(root);else saveComment()
}
async function saveComment(){
  if(busy.value || hasPendingImages.value) return
  busy.value=true; commentError.value=''
  const name=issue.value.name, previous=new Set(issue.value.timeline.map(event=>event.name))
  try { const updated=await api('add_comment',{name,body:commentBody.value},true); if(issue.value?.name===name){issue.value=updated;suggestCommunication(updated,previous);commentBody.value='';commentEditorKey.value++} }
  catch(e){if(issue.value?.name===name) commentError.value=e.message}
  finally{busy.value=false}
}
function suggestCommunication(updated,previous){
  const posted=updated.timeline.filter(event=>!previous.has(event.name) && event.kind==='Comment' && event.actor===currentUser.value)
  if(posted.length!==1)return
  const event=posted[0], dom=new DOMParser().parseFromString(event.body,'text/html')
  const text=dom.body.textContent, hint=communicationHint(text)
  if(hint && !updated.timeline.some(row=>row.source_comment===event.name))communicationPrompts.value[event.name]={...hint,followUpDate:followUpHint(text,event.recorded_at)}
}
async function jumpToSource(name){
  if(hasPendingImages.value)return
  const source=issue.value.timeline.find(event=>event.name===name)
  if(!source)return
  const root=source.reply_to ? issue.value.timeline.find(event=>event.name===source.reply_to) : source
  if(!root)return
  timelineSelection.value=new Set([...timelineSelection.value,timelineCategory(root)])
  if(source.reply_to)replyWindowSizes.value={...replyWindowSizes.value,[root.name]:issue.value.timeline.filter(event=>event.reply_to===root.name).length}
  await nextTick()
  const element=document.getElementById('comment-'+name)
  element?.scrollIntoView({block:'center',behavior:'smooth'})
  element?.focus({preventScroll:true})
}
function replyParticipants(thread){return [...new Set(thread.replies.map(reply=>reply.actor).filter(Boolean))].slice(0,3)}
function visibleReplies(thread){return thread.replies.slice(-(replyWindowSizes.value[thread.event.name] || 3))}
function earlierReplyCount(thread){return Math.max(0,thread.replies.length-visibleReplies(thread).length)}
function loadEarlierReplies(root){replyWindowSizes.value={...replyWindowSizes.value,[root]:(replyWindowSizes.value[root] || 3)+3};if(replyRoot.value===root) nextTick(()=>{if(replyRoot.value===root) replyEditor.value?.editor?.commands.focus()})}
function labelEditor(component, current, labelId, scope){
  if(!component) return
  nextTick(()=>{
    if(current && current.value!==component) return
    const editor=component.editor
    if(!editor || editor.isDestroyed) return
    const props=editor.options.editorProps || {}
    editor.setOptions({editorProps:{...props,...(current ? {handlePaste:(_view,event)=>pasteImages(event,current,scope),handleDrop:(_view,event)=>Array.from(event.dataTransfer?.files||[]).some(file=>file.type.startsWith('image/'))} : {}),attributes:{...props.attributes,role:'textbox','aria-multiline':'true','aria-labelledby':labelId}}})
  })
}
function setCommentEditor(component){commentEditor.value=component;labelEditor(component,commentEditor,'comment-editor-label','comment')}
function setReplyEditor(component,root){replyEditor.value=component;labelEditor(component,replyEditor,'reply-editor-label-'+root,'reply')}
const pendingImageTargets = new Map(), pasteControllers = new Map()
let pasteSequence=0
function validateImage(file, key){if(file.size>10*1024*1024)return 'Maximum image size is 10 MB'; pendingImages[key]=true;return null}
function beginImageUpload(open, target, scope, key){
  pendingImageTargets.set(key,{name:issue.value?.name,editor:target?.editor,root:replyRoot.value,commentKey:commentEditorKey.value,replyKey:replyEditorKey.value,field:inlineField.value})
  open()
}
function insertImage(file, target, scope, key, bookmark=null){
  const context=pendingImageTargets.get(key); if(!bookmark){pendingImageTargets.delete(key);delete pendingImages[key]}
  const uploadedFor=new URL(file.file_url,location.origin).searchParams.get('name')
  const editor=target?.editor
  if(!context || !issue.value || context.name!==issue.value.name || uploadedFor!==context.name || !editor || editor!==context.editor || editor.isDestroyed) return
  if(scope==='comment' && context.commentKey!==commentEditorKey.value) return
  if(scope==='reply' && (context.replyKey!==replyEditorKey.value || context.root!==replyRoot.value)) return
  if(scope==='description' && (context.field!=='description' || inlineField.value!=='description')) return
  const src='/api/method/unicom.api.inline_image?'+new URLSearchParams({name:uploadedFor,attachment:file.name})
  if(bookmark){
    const selection=bookmark.nextPos===null?bookmark.current.resolve(editor.state.doc):{from:bookmark.nextPos,to:bookmark.nextPos}
    if(!editor.commands.insertContentAt({from:selection.from,to:selection.to},{type:'image',attrs:{src,alt:file.file_name}},{updateSelection:false}))throw new Error('Could not insert pasted image')
    let end=null;editor.state.doc.descendants((node,pos)=>{if(node.type.name==='image' && node.attrs.src===src)end=pos+node.nodeSize})
    if(end===null)throw new Error('Could not insert pasted image')
    bookmark.nextPos=end
  }
  else editor.chain().focus().setImage({src,alt:file.file_name}).run()
  if(!issue.value.attachments.some(x=>x.name===file.name)) issue.value.attachments.push(file)
  if(!bookmark && scope==='description' && inlineDeferred.value){inlineDeferred.value=false;nextTick(()=>saveInline())}
}
function setPasteError(scope, message){
  if(scope==='description')inlineError.value=message
  else if(scope==='comment')commentError.value=message
  else replyError.value=message
}
function pasteImages(event,target,scope){
  const clipboard=event.clipboardData
  const fromItems=Array.from(clipboard?.items||[]).filter(item=>item.type?.startsWith('image/')).map(item=>item.getAsFile()).filter(Boolean)
  const files=fromItems.length ? fromItems : Array.from(clipboard?.files||[]).filter(file=>file.type?.startsWith('image/'))
  if(!files.length)return false
  event.preventDefault()
  if(busy.value || hasPendingImages.value){setPasteError(scope,'Wait for the current operation before pasting an image.');return true}
  if(files.some(file=>file.size>10*1024*1024)){setPasteError(scope,'Maximum image size is 10 MB');return true}
  const editor=target.value?.editor
  if(!editor || editor.isDestroyed || !issue.value){setPasteError(scope,'Unable to paste image. Please try again.');return true}
  setPasteError(scope,'')
  const key='paste:'+scope+':'+(++pasteSequence), controller=new AbortController()
  const context={name:issue.value.name,editor,root:replyRoot.value,commentKey:commentEditorKey.value,replyKey:replyEditorKey.value,field:inlineField.value}
  const bookmark={current:editor.state.selection.getBookmark(),nextPos:null}
  const mapBookmark=({transaction})=>{bookmark.current=bookmark.current.map(transaction.mapping);if(bookmark.nextPos!==null)bookmark.nextPos=transaction.mapping.map(bookmark.nextPos,1)}
  editor.on('transaction',mapBookmark)
  pendingImageTargets.set(key,context);pendingImages[key]=true;pasteControllers.set(key,controller)
  void uploadPastedImages(files,target,scope,key,context,bookmark,controller).finally(()=>editor.off('transaction',mapBookmark))
  return true
}
async function uploadPastedImages(files,target,scope,key,context,bookmark,controller){
  let succeeded=false
  try{
    for(let i=0;i<files.length;i++){
      const form=new FormData(), file=files[i]
      const extension=({'image/jpeg':'jpg','image/png':'png','image/gif':'gif','image/webp':'webp'})[file.type]||'image'
      form.append('file',file,'pasted-image-'+(i+1)+'.'+extension);form.append('docname',context.name)
      const response=await fetch('/api/method/unicom.api.upload_image',{method:'POST',credentials:'same-origin',headers:{'X-Frappe-CSRF-Token':csrf()},body:form,signal:controller.signal})
      const result=await response.json()
      if(!response.ok){let message=result.exception||'Image upload failed';try{const messages=JSON.parse(result._server_messages||'[]');if(messages.length)message=JSON.parse(messages[0]).message}catch{}throw new Error(message)}
      if(pendingImageTargets.get(key)!==context) return
      insertImage(result.message,target.value,scope,key,bookmark)
    }
    succeeded=true
  }catch(e){if(pendingImageTargets.get(key)===context && e.name!=='AbortError')setPasteError(scope,e.message||'Image upload failed')}
  finally{
    if(pendingImageTargets.get(key)===context){pendingImageTargets.delete(key);delete pendingImages[key];if(scope==='description' && inlineDeferred.value){inlineDeferred.value=false;if(succeeded)nextTick(()=>saveInline())}}
    pasteControllers.delete(key)
  }
}
function imageUploadFailed(key,scope){delete pendingImages[key];pendingImageTargets.delete(key);if(scope==='description' && inlineDeferred.value){inlineDeferred.value=false;inlineError.value='Image upload failed. Your description draft is still available.'}}
function startReply(root){if(hasPendingImages.value)return;if(replyRoot.value!==root){replyRoot.value=root;replyBody.value='';replyError.value='';replyEditorKey.value++} nextTick(()=>replyEditor.value?.editor?.commands.focus())}
function cancelReply(){replyRoot.value=null;replyBody.value='';replyError.value='';replyEditorKey.value++}
async function saveReply(root){
  if(busy.value || hasPendingImages.value || replyRoot.value!==root) return
  busy.value=true; replyError.value=''
  const name=issue.value.name, previous=new Set(issue.value.timeline.map(event=>event.name))
  try { const updated=await api('add_comment',{name,body:replyBody.value,reply_to:root},true); if(issue.value?.name===name && replyRoot.value===root){issue.value=updated;suggestCommunication(updated,previous);cancelReply()} }
  catch(e){if(issue.value?.name===name && replyRoot.value===root) replyError.value=e.message}
  finally{busy.value=false}
}
async function uploadDone(){ await open(issue.value.name,false) }
function userProfile(user){return issue.value?.user_profiles?.find(person=>person.name===user) || people.value.find(person=>person.name===user)}
function authorName(user){return userProfile(user)?.full_name || user || 'Unknown user'}
function userImage(user){return userProfile(user)?.user_image || ''}
// Frappe timestamps are site-local wall times; format the components without converting zones.
function formatSiteTime(value){
  if(!value) return '—'
  const match=String(value).match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?/)
  if(!match) return String(value)
  const date=new Date(Date.UTC(+match[1],+match[2]-1,+match[3],+(match[4]||0),+(match[5]||0),+(match[6]||0)))
  if(Number.isNaN(date.getTime())) return String(value)
  return new Intl.DateTimeFormat(undefined,{timeZone:'UTC',year:'numeric',month:'short',day:'numeric',...(match[4] ? {hour:'numeric',minute:'2-digit'} : {})}).format(date)
}
function fieldLabel(key){return ({accountable_owner:'Issue Owner',coordination_user:'Coordinating with',next_action:'Next action',next_action_date:'Next action date',resolution_note:'Resolution note',follow_up_assignees:'Follow-up assignees'})[key] || key.replaceAll('_',' ').replace(/^./,c=>c.toUpperCase())}
function changeValue(value,key){if(value===null || value===undefined || value==='') return '—'; if(Array.isArray(value)) return value.length ? value.join(', ') : '—'; if(typeof value==='object') return JSON.stringify(value); if(key==='next_action_date') return formatSiteTime(value); return String(value)}
function descriptionSummary(value){
  const doc=new DOMParser().parseFromString(typeof value==='string'?value:'','text/html')
  const images=doc.body.querySelectorAll('img').length
  doc.body.querySelectorAll('img,script,style,iframe,object,embed,video,audio,source,link').forEach(node=>node.remove())
  doc.body.querySelectorAll('p,div,li,blockquote,pre,h1,h2,h3,h4,h5,h6,tr').forEach(node=>node.append(' '))
  return {text:(doc.body.textContent||'').replace(/\s+/g,' ').trim(),images}
}
function descriptionChange(value){
  const before=descriptionSummary(value?.from),after=descriptionSummary(value?.to)
  if(before.text===after.text && before.images===after.images)return 'Description updated'
  const show=part=>[part.text,part.images ? part.images+' '+(part.images===1?'image':'images') : ''].filter(Boolean).join(' · ')||'—'
  return show(before)+' → '+show(after)
}
function changes(event){try{const data=JSON.parse(event.changes||'{}');return Object.entries(data).map(([key,value])=>key==='description'?{label:fieldLabel(key),text:descriptionChange(value),raw:null}:{label:fieldLabel(key),text:changeValue(value?.from,key)+' → '+changeValue(value?.to,key),raw:JSON.stringify(value)})}catch{return event.changes ? [{label:'Changes',text:event.changes,raw:event.changes}] : []}}


onBeforeUnmount(()=>{clearInterval(notificationTimer);window.removeEventListener('focus',notificationFocus);document.removeEventListener('visibilitychange',notificationFocus);detailObserver?.disconnect();window.removeEventListener('resize',updateDetailViewport);for(const controller of pasteControllers.values())controller.abort();pasteControllers.clear();pendingImageTargets.clear();for(const key of Object.keys(pendingImages))delete pendingImages[key];document.removeEventListener('pointerdown',inlineInteraction,true);document.removeEventListener('focusin',inlineInteraction,true);document.removeEventListener('focusout',onInlineFocusOut,true)})
onMounted(async()=>{refreshNotifications();window.addEventListener('focus',notificationFocus);document.addEventListener('visibilitychange',notificationFocus);notificationTimer=setInterval(()=>{if(!document.hidden){today.value=new Date();if(!notificationsOpen.value)refreshNotifications()}},30000);try{const saved=Number(localStorage.getItem(detailStorageKey));if(Number.isFinite(saved) && saved>=detailMin && saved<=detailMax)detailPreferred.value=saved}catch(_){}window.addEventListener('resize',updateDetailViewport);document.addEventListener('pointerdown',inlineInteraction,true);document.addEventListener('focusin',inlineInteraction,true);document.addEventListener('focusout',onInlineFocusOut,true);fetch('/api/method/frappe.auth.get_logged_user',{credentials:'same-origin'}).then(r=>r.ok?r.json():null).then(r=>{currentUser.value=r?.message||''}).catch(()=>{});await run(async()=>{people.value=await api('users');await applyLocation()});window.onpopstate=async()=>{if(!await canLeaveInline()){history.pushState({},'',currentRoute());return}await applyLocation()};window.addEventListener('beforeunload',event=>{if(inlineField.value && inlineValue.value!==(issue.value?.[inlineField.value]||'')){event.preventDefault();event.returnValue=''}})})
</script>
<template>
<div class="h-screen overflow-hidden flex flex-col md:flex-row">
  <aside class="bg-gray-50 border-b md:border-b-0 md:border-r border-gray-200 shrink-0 flex flex-col min-w-0" :class="sidebarCollapsed?'md:w-16':'md:w-60'">
    <div class="p-2 shrink-0">
      <Dropdown :options="[{label:'Frappe Desk',onClick:goDesk},{label:'Log out',onClick:logout}]" class="w-full">
        <Button variant="ghost" class="w-full !h-12 !justify-start !px-2" :aria-label="'Account menu'+(currentUser ? ' for '+authorName(currentUser) : '')" :title="currentUser ? authorName(currentUser) : 'Account menu'">
          <template #prefix><span class="flex items-center justify-center h-8 w-8 rounded-md bg-gray-200 text-gray-700"><FeatherIcon name="message-square" class="h-4 w-4"/></span></template>
          <span class="min-w-0 text-left" :class="sidebarCollapsed?'md:sr-only':''"><span class="block font-semibold">UniCom</span><span class="block max-w-40 truncate text-xs text-gray-500">{{currentUser ? authorName(currentUser) : 'Account'}}</span></span>
          <template #suffix><FeatherIcon name="chevron-down" class="ml-auto h-4 w-4 text-gray-500" :class="sidebarCollapsed?'md:hidden':''"/></template>
        </Button>
      </Dropdown>
    </div>
    <nav aria-label="UniCom navigation" class="px-2 pb-2 flex flex-row md:flex-col gap-1 overflow-x-auto md:overflow-x-hidden">
      <Button variant="ghost" icon-left="layout" class="!justify-start !h-7 !rounded !text-base !font-[420] !text-gray-700 [&>svg]:text-gray-800 shrink-0 md:w-full" :class="[sidebarCollapsed?'md:!justify-center':'',showDashboard && !issue?'!bg-white !text-gray-900 shadow-sm ring-1 ring-gray-200':'']" aria-label="Dashboard" :aria-current="showDashboard && !issue?'page':undefined" title="Dashboard" @click="goDashboard"><span :class="sidebarCollapsed?'md:sr-only':''">Dashboard</span></Button>
      <Button v-for="item in [{view:'mine',label:'My Issues',icon:'user'},{view:'overdue',label:'Overdue',icon:'clock'},{view:'all',label:'All Accessible Issues',icon:'list'}]" :key="item.view" :variant="'ghost'" :icon-left="item.icon" class="!justify-start !h-7 !rounded !text-base !font-[420] !text-gray-700 [&>svg]:text-gray-800 shrink-0 md:w-full" :class="[sidebarCollapsed?'md:!justify-center':'',!showDashboard && view===item.view?'!bg-white !text-gray-900 shadow-sm ring-1 ring-gray-200':'']" :aria-label="item.label" :aria-current="!showDashboard && view===item.view?'page':undefined" :title="item.label" @click="goList(item.view)"><span :class="sidebarCollapsed?'md:sr-only':''">{{item.label}}</span></Button>
    </nav>
    <div class="hidden md:flex mt-auto p-2 flex-col gap-1">
      <Button variant="ghost" icon-left="help-circle" class="w-full !justify-start !h-7 !rounded !text-base !font-[420] !text-gray-700 [&>svg]:text-gray-800" :class="sidebarCollapsed?'!justify-center':''" aria-label="Frappe help" title="Frappe help" @click="openHelp"><span :class="sidebarCollapsed?'sr-only':''">Help</span></Button>
      <Button variant="ghost" :icon-left="sidebarCollapsed?'chevrons-right':'chevrons-left'" class="w-full !justify-start !h-7 !rounded !text-base !font-[420] !text-gray-700 [&>svg]:text-gray-800" :class="sidebarCollapsed?'!justify-center':''" :aria-label="sidebarCollapsed?'Expand sidebar':'Collapse sidebar'" :title="sidebarCollapsed?'Expand sidebar':'Collapse sidebar'" @click="sidebarCollapsed=!sidebarCollapsed"><span :class="sidebarCollapsed?'sr-only':''">{{sidebarCollapsed?'Expand sidebar':'Collapse sidebar'}}</span></Button>
    </div>
  </aside>
  <main class="min-w-0 min-h-0 flex-1 flex flex-col">
    <header class="border-b border-gray-200 h-12 shrink-0 px-4 sm:px-6 flex items-center justify-between gap-2"><div class="min-w-0 flex-1 overflow-hidden"><Breadcrumbs class="unicom-breadcrumbs" :items="issue ? [{label:'Issues',onClick:()=>goList(view)},{label:'List',kind:'list',onClick:()=>goList(view)},{label:issue.title}] : showDashboard ? [{label:'Dashboard',onClick:goDashboard}] : [{label:'Issues',onClick:()=>goList(view)},{label:'List',kind:'list',onClick:()=>goList(view)}]"><template #prefix="{item}"><FeatherIcon v-if="item.kind==='list'" name="menu" class="h-4 w-4 mr-1 text-gray-600"/></template></Breadcrumbs></div><div class="flex shrink-0 items-center gap-2"><Popover v-model:show="notificationsOpen" placement="bottom-end"><template #target="{togglePopover}"><Button variant="ghost" icon="bell" class="relative" :label="'Notifications'+(notificationCount ? ' ('+notificationCount+' unread)' : '')" title="Notifications" @click="toggleNotifications(togglePopover)"><template #suffix><span v-if="notificationCount" class="absolute -right-1 -top-1 rounded-full bg-red-600 px-1.5 text-xs leading-4 text-white">{{notificationCount>99?'99+':notificationCount}}</span></template></Button></template><template #body><div role="region" aria-label="UniCom notifications" class="mt-1 w-96 max-w-[calc(100vw-2rem)] rounded-lg border border-gray-200 bg-white p-2 shadow-lg"><div class="flex items-center justify-between px-2 py-1"><span class="font-semibold">Notifications</span><Button size="sm" variant="ghost" icon="refresh-cw" label="Refresh notifications" :disabled="notificationLoading" @click="refreshNotifications()"/></div><p v-if="notificationError" role="alert" class="px-2 py-2 text-sm text-red-600">{{notificationError}} <Button size="sm" variant="ghost" :disabled="notificationLoading" @click="refreshNotifications()">Retry</Button></p><div class="max-h-96 overflow-y-auto"><button v-for="row in notificationRows" :key="row.name" type="button" class="block w-full rounded-md px-3 py-2 text-left hover:bg-gray-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-500" :class="row.read?'text-gray-600':'bg-gray-50 text-gray-900'" :disabled="notificationOpening || notificationLoading || busy || hasPendingImages" @click="openNotification(row)"><span class="flex gap-2"><span v-if="!row.read" class="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-blue-500" aria-label="Unread"/><span class="min-w-0"><span class="block text-sm" :class="row.read?'':'font-medium'">{{row.subject}}</span><span class="mt-1 block text-xs text-gray-500">{{formatSiteTime(row.creation)}}</span></span></span></button><p v-if="!notificationRows.length && !notificationLoading && !notificationError" class="px-3 py-6 text-center text-sm text-gray-500">No notifications yet.</p><p v-if="notificationLoading" role="status" class="px-3 py-3 text-center text-sm text-gray-500">Loading notifications…</p><Button v-if="notificationHasMore" variant="ghost" class="mt-1 w-full" :disabled="notificationLoading" @click="refreshNotifications(false)">Load more</Button></div></div></template></Popover><Popover v-if="issue" v-model:show="assignOpen" placement="bottom-end"><template #target="{togglePopover}"><Button :variant="assignDraft.length>1 ? 'ghost' : 'subtle'" :class="assignDraft.length>1 ? '!bg-transparent' : ''" :disabled="busy &amp;&amp; !inlineSaving &amp;&amp; !assignSaving" :title="assignError ? 'Assign To: unsaved changes' : 'Assign To'" @click="openAssignments(togglePopover)"><span v-if="!assignDraft.length" class="flex items-center gap-1"><FeatherIcon name="user-plus" class="h-4 w-4"/><span class="hidden sm:inline">Assign To</span></span><span v-else-if="assignDraft.length===1" class="flex items-center gap-2"><Avatar :key="assignDraft[0]+userImage(assignDraft[0])" size="sm" :label="authorName(assignDraft[0])" :image="userImage(assignDraft[0])"/><span class="hidden max-w-32 truncate sm:inline">{{authorName(assignDraft[0])}}</span></span><span v-else class="flex items-center"><span class="flex -space-x-1"><span v-for="user in assignDraft.slice(0,3)" :key="user" role="img" :aria-label="authorName(user)" :title="authorName(user)"><Avatar :key="user+userImage(user)" size="md" class="rounded-full bg-gray-100 ring-2 ring-white" :label="authorName(user)" :image="userImage(user)"/></span></span><span v-if="assignDraft.length>3" class="ml-1 text-xs">+{{assignDraft.length-3}}</span></span><span v-if="assignError" class="ml-1 text-red-600" aria-label="Unsaved assignment changes">!</span></Button></template><template #body><div class="mt-1 w-[470px] max-w-[calc(100vw-2rem)] rounded-lg border border-gray-200 bg-white p-3 shadow-lg"><div class="mb-2 text-base text-gray-600">Assign To</div><div class="w-full"><Popover v-model:show="assignSearchOpen" class="w-full" placement="bottom-start"><template #target="{togglePopover}"><div role="button" tabindex="0" aria-label="Choose participants" class="flex min-h-14 w-full flex-wrap items-start gap-1 rounded-lg bg-gray-100 p-2" @click="togglePopover()" @keydown.enter.self.prevent="togglePopover()" @keydown.space.self.prevent="togglePopover()"><span v-for="user in assignDraft" :key="user" class="inline-flex max-w-full items-center gap-1 rounded-full border border-gray-200 bg-white px-1 py-0.5"><Avatar :key="user+userImage(user)" size="xs" :label="authorName(user)" :image="userImage(user)"/><span class="max-w-36 truncate text-base text-gray-700">{{authorName(user)}}<span v-if="user!==currentUser &amp;&amp; !people.some(person=>person.name===user)"> (unavailable)</span></span><Button size="sm" variant="ghost" icon="x" :label="'Remove '+authorName(user)" :title="'Remove '+authorName(user)" @click.stop="toggleAssignment(user)"/></span><span v-if="!assignDraft.length" class="text-base text-gray-500">Choose people</span></div></template><template #body><div class="mt-1 w-56 max-w-[calc(100vw-2rem)] rounded-lg border border-gray-200 bg-white p-2 shadow-lg"><FormControl v-model="assignQuery" placeholder="Search" aria-label="Search users"/><div class="mt-2 max-h-52 overflow-y-auto"><Button v-for="option in filteredAssignmentOptions" :key="option.value" variant="ghost" class="w-full !justify-start" :aria-pressed="assignDraft.includes(option.value)" @click="toggleAssignment(option.value)"><template #prefix><Avatar :key="option.value+userImage(option.value)" size="sm" :label="authorName(option.value)" :image="userImage(option.value)"/></template><span class="truncate" :title="option.label">{{authorName(option.value)}}<span v-if="option.value!==currentUser &amp;&amp; !people.some(person=>person.name===option.value)"> (unavailable)</span></span><template #suffix><FeatherIcon v-if="assignDraft.includes(option.value)" name="check" class="h-4 w-4"/></template></Button><div v-if="!filteredAssignmentOptions.length" class="p-2 text-sm text-gray-500">No users found</div></div><Button variant="ghost" icon-left="x" class="mt-2 w-full !justify-start border-t" @click="setAssignment([])">Clear</Button></div></template></Popover></div><div class="mt-2"><Switch class="[&amp;>span>span]:!font-normal [&amp;>span>span]:!text-gray-500" label="Assign To Me" :model-value="assignDraft.includes(currentUser)" :disabled="!currentUser || currentUser==='Guest'" @update:model-value="toggleAssignMe"/></div><p v-if="assignDraft.some(user=>user!==currentUser &amp;&amp; !people.some(person=>person.name===user))" class="mt-2 text-xs text-gray-600">If an unavailable participant prevents saving, remove them.</p><div v-if="assignSaving" role="status" class="mt-2 text-xs text-gray-500">Saving assignments…</div><div v-if="assignError" class="mt-2"><ErrorMessage :message="safeAssignError"/><Button size="sm" class="mt-1" @click="saveAssignments">Retry</Button></div></div></template></Popover><Dropdown v-if="issue" :options="statuses.map(status=>({label:status,onClick:()=>changeStatus(status)}))"><Button :disabled="busy &amp;&amp; !inlineSaving" class="whitespace-nowrap" :title="'Status: '+issue.status"><template #prefix><span :class="statusColor(issue.status)" class="h-2 w-2 rounded-full" aria-hidden="true"/></template>{{issue.status}}<span v-if="issue.overdue" class="ml-1 text-red-600">· Overdue</span><template #suffix><FeatherIcon name="chevron-down" class="h-4 w-4"/></template></Button></Dropdown><Button variant="solid" icon-left="plus" class="shrink-0 whitespace-nowrap" @click="showNew=true">Create</Button></div></header>
    <ErrorMessage v-if="error" class="mx-6 mt-4" :message="safeError"/>
    <div v-if="showDashboard && !issue" class="min-h-0 flex-1 overflow-y-auto px-4 py-6 sm:px-6">
      <div class="mx-auto max-w-5xl space-y-6">
        <div><h1 class="text-2xl font-semibold">Dashboard</h1></div>
        <section aria-labelledby="dashboard-today" class="rounded-lg border border-gray-200 bg-white p-5 sm:p-6">
          <div class="flex flex-wrap items-start justify-between gap-4"><div><h2 id="dashboard-today" class="flex items-center gap-2 text-lg font-semibold"><FeatherIcon name="calendar" class="h-5 w-5 text-gray-500"/>Today</h2><p class="mt-2 text-sm text-gray-500">{{todayLabel}}</p></div><Button variant="subtle" icon-right="arrow-right" @click="goList('mine')">View my issues</Button></div>
        </section>
        <div class="grid gap-6 md:grid-cols-2">
          <section aria-labelledby="dashboard-tasks" class="rounded-lg border border-gray-200 bg-white p-5 sm:p-6"><div class="flex items-center justify-between gap-3"><h2 id="dashboard-tasks" class="flex items-center gap-2 text-lg font-semibold"><FeatherIcon name="check-square" class="h-5 w-5 text-gray-500"/>Tasks</h2><Badge theme="gray">Coming soon</Badge></div><div class="flex min-h-44 flex-col items-center justify-center py-8 text-center"><FeatherIcon name="check-square" class="mb-3 h-8 w-8 text-gray-400"/><p class="text-sm text-gray-500">Task tracking is coming soon.</p></div></section>
          <section aria-labelledby="dashboard-activity" class="rounded-lg border border-gray-200 bg-white p-5 sm:p-6"><div class="flex flex-wrap items-center justify-between gap-3"><h2 id="dashboard-activity" class="flex items-center gap-2 text-lg font-semibold"><FeatherIcon name="activity" class="h-5 w-5 text-gray-500"/>Activity</h2><Button icon-left="plus" disabled title="Activity logging is coming soon" aria-describedby="activity-coming-soon">Log activity</Button></div><div class="flex min-h-44 flex-col items-center justify-center py-8 text-center"><FeatherIcon name="activity" class="mb-3 h-8 w-8 text-gray-400"/><p id="activity-coming-soon" class="text-sm font-medium text-gray-700">Activity logging is coming soon.</p></div></section>
        </div>
      </div>
    </div>
    <template v-else-if="!issue">
      <div class="min-h-0 flex-1 flex flex-col">
        <div class="flex gap-2 px-4 sm:px-6 py-4 flex-wrap shrink-0"><FormControl v-model="search" placeholder="Search title" aria-label="Search title" @keydown.enter="page=0;load()"/><FormControl type="select" v-model="filter" aria-label="Filter by status" :options="[{label:'All statuses',value:''},...statuses.map(x=>({label:x,value:x}))]" @change="page=0;load()"/><Button @click="page=0;load()">Search</Button></div>
        <div class="min-h-0 flex-1 overflow-auto px-4 sm:px-6"><ListView :columns="columns" :rows="rows" row-key="name" :options="{selectable:false,onRowClick:row=>open(row.name),emptyState:{title:'No issues found'}}"><template #cell="{column,row,item}"><Badge v-if="column.key==='status'" :theme="row.overdue?'red':'gray'">{{row.overdue?'Overdue · ':''}}{{item}}</Badge><span v-else-if="column.key==='accountable_owner'" class="flex items-center gap-2 min-w-0"><Avatar :key="item+userImage(item)" size="sm" :label="authorName(item)" :image="userImage(item)"/><span class="text-sm truncate">{{authorName(item)}}</span></span><span v-else class="text-sm truncate">{{item||'—'}}</span></template></ListView></div>
        <ListFooter class="px-4 sm:px-6 py-3 border-t border-gray-200 shrink-0" :model-value="pageLength" @update:model-value="setPageLength"><template #right><div class="flex items-center gap-2"><span class="text-sm text-gray-500">Page {{page+1}} · {{rows.length}} {{rows.length===1?'issue':'issues'}} shown</span><Button :disabled="page===0" @click="page--;load()">Previous</Button><Button :disabled="rows.length<pageLength" @click="page++;load()">Next</Button></div></template></ListFooter>
      </div>
    </template>
    <div v-else class="min-h-0 flex-1 overflow-y-auto">
      <div ref="detailGrid" class="grid min-w-0 lg:grid-cols-[minmax(0,1fr)_var(--issue-details-width)] lg:grid-rows-[auto_1fr]" :style="{'--issue-details-width':detailWidth+'px'}">
        <div class="order-1 w-full min-w-0 max-w-4xl mx-auto p-6 flex flex-wrap justify-between gap-4 items-start"><div class="min-w-0 flex-1 basis-64"><div v-if="inlineField==='title'" ref="inlineRegion" class="space-y-2"><FormControl v-model="inlineValue" label="Title" @keydown.enter="saveInline" @keydown.esc="cancelInline"/><ErrorMessage :message="safeInlineError"/><Button v-if="inlineError" size="sm" @click="saveInline">Retry</Button></div><h1 v-else class="text-2xl font-semibold break-words"><Button variant="ghost" class="!h-auto !p-0 !text-2xl" aria-label="Edit title" @click="startInline('title')">{{issue.title}}</Button></h1><p class="text-sm text-gray-500 mt-2">{{issue.issue_id || issue.name}} · Created by {{authorName(issue.owner)}}</p></div></div>
        <section class="order-3 lg:order-2 w-full min-w-0 max-w-4xl mx-auto px-6 pb-6 space-y-6 break-words"><div><h2 class="font-semibold mb-2">Description</h2><div v-if="inlineField==='description'" ref="inlineRegion" class="space-y-2"><div id="description-editor-label" class="text-sm">Edit description</div><FileUploader v-for="uploadKey in [issue.name+':description:'+inlineKey]" :key="uploadKey" file-types="image/png,image/jpeg,image/gif,image/webp" :upload-args="{upload_endpoint:'/api/method/unicom.api.upload_image',docname:issue.name,private:true}" :validate-file="f=>validateImage(f,uploadKey)" @success="file=>insertImage(file,inlineEditor,'description',uploadKey)" @failure="imageUploadFailed(uploadKey,'description')"><template #default="{openFileSelector,uploading,error:uploadError}"><TextEditor :ref="setInlineEditor" class="rich-editor" :content="inlineValue" :fixed-menu="richMenu" :mentions="mentionOptions" placeholder="Write a description; type @ to mention someone" @change="value=>inlineValue=value"><template #bottom><div class="editor-image-action"><Button size="sm" variant="ghost" icon="image" label="Attach image" title="Attach image" :loading="uploading" :disabled="busy || uploading || hasPendingImages" @click="beginImageUpload(openFileSelector,inlineEditor,'description',uploadKey)"/></div></template></TextEditor><ErrorMessage :message="uploadError"/><ErrorMessage :message="safeInlineError"/><Button v-if="inlineError" size="sm" @click="saveInline">Retry</Button></template></FileUploader></div><div v-else><div class="prose prose-sm max-w-none text-gray-700" role="button" tabindex="0" aria-label="Edit description" @click="editDescription" @keydown.enter="editDescription" @keydown.space="editDescription" v-html="issue.description || '—'"></div></div></div><div>
          <div class="flex flex-wrap items-center justify-between gap-2 mb-4"><h2 class="font-semibold">Timeline</h2><div role="group" aria-label="Filter timeline" class="flex flex-wrap gap-1"><Button size="sm" :variant="allTimelineSelected?'subtle':'ghost'" :aria-pressed="allTimelineSelected" :disabled="hasPendingImages" @click="selectAllTimeline">All</Button><Button v-for="category in timelineCategories" :key="category" size="sm" :variant="!allTimelineSelected && timelineSelection.has(category)?'subtle':'ghost'" :aria-pressed="!allTimelineSelected && timelineSelection.has(category)" :disabled="hasPendingImages" @click="toggleTimelineCategory(category)">{{category}}</Button></div></div><div class="mb-4 flex justify-end"><Dropdown :options="channels.map(channel=>({label:channel,onClick:()=>logIssue(channel)}))"><Button variant="solid" class="whitespace-nowrap" :disabled="(busy &amp;&amp; !inlineSaving) || issue.status==='Resolved'">Log communication<template #suffix><FeatherIcon name="chevron-down" class="h-4 w-4"/></template></Button></Dropdown></div>
          <p v-if="hasPendingImages" role="status" class="mb-3 text-xs text-gray-600">Uploading image… Timeline filters will be available when the upload finishes.</p><div class="mb-8 rounded-lg border border-gray-200 p-3 space-y-2">
            <div id="comment-editor-label" class="text-xs font-medium text-gray-600">Add a comment</div><FileUploader v-for="uploadKey in [issue.name+':comment:'+commentEditorKey]" :key="uploadKey" file-types="image/png,image/jpeg,image/gif,image/webp" :upload-args="{upload_endpoint:'/api/method/unicom.api.upload_image',docname:issue.name,private:true}" :validate-file="f=>validateImage(f,uploadKey)" @success="file=>insertImage(file,commentEditor,'comment',uploadKey)" @failure="delete pendingImages[uploadKey]"><template #default="{openFileSelector,uploading,error:uploadError}"><div @keydown="submitShortcut($event)"><TextEditor :ref="setCommentEditor" :key="commentEditorKey" class="timeline-editor rich-editor" :content="commentBody" :fixed-menu="richMenu" :mentions="mentionOptions" placeholder="Write a comment; type @ to mention someone" @change="value=>commentBody=value"><template #bottom><div class="editor-image-action"><Button size="sm" variant="ghost" icon="image" label="Attach image" title="Attach image" :loading="uploading" :disabled="busy || uploading || hasPendingImages" @click="beginImageUpload(openFileSelector,commentEditor,'comment',uploadKey)"/></div></template></TextEditor></div><ErrorMessage :message="uploadError"/><ErrorMessage :message="safeCommentError"/><div class="flex justify-end"><Button variant="solid" :loading="busy" :disabled="busy || uploading || hasPendingImages" title="Post comment (Ctrl+Enter or Cmd+Enter)" @click="saveComment">Post comment</Button></div></template></FileUploader>
          </div>
          <div v-if="hiddenReplyDraft" class="mb-4 text-xs text-gray-600">A reply draft is in a hidden thread. Select its category or All to continue.</div>
          <div v-if="!filteredThreads.length" class="py-4 text-sm text-gray-600">{{timelineSelection.size ? 'No entries match the selected filters.' : 'Select a category to see timeline entries.'}} <Button size="sm" variant="ghost" :disabled="hasPendingImages" @click="selectAllTimeline">Show all</Button></div>
          <div class="space-y-5">
            <div v-for="thread in filteredThreads" :key="thread.event.name">
              <article tabindex="-1" :id="'comment-'+thread.event.name" v-if="['Comment','Communication'].includes(thread.event.kind)" class="overflow-hidden rounded border border-gray-200 bg-white">
                <div class="flex gap-3 p-4"><Avatar :key="thread.event.actor+userImage(thread.event.actor)" size="xl" :label="authorName(thread.event.actor)" :image="userImage(thread.event.actor)"/>
                <div class="min-w-0 flex-1">
                  <div class="flex flex-wrap items-center gap-x-2 gap-y-1"><span class="text-sm font-semibold">{{authorName(thread.event.actor)}}</span><Badge theme="gray">{{thread.event.channel || thread.event.kind}}</Badge><span class="text-xs text-gray-500" :title="'Recorded: '+thread.event.recorded_at">{{formatSiteTime(thread.event.recorded_at)}}</span></div>
                  <div v-if="thread.event.happened_at" class="mt-1 text-xs text-gray-500" :title="'Happened: '+thread.event.happened_at">Happened {{formatSiteTime(thread.event.happened_at)}}</div>
                  <p v-if="thread.event.contact" class="text-xs text-gray-500 mt-1">Contact: {{thread.event.contact}}</p>
                  <div v-if="thread.event.body" class="prose prose-sm max-w-none text-gray-800 mt-2" v-html="thread.event.body"></div>
                  <div v-if="communicationPrompts[thread.event.name] && issue.status!=='Resolved'" class="mt-3 rounded-md border border-gray-200 bg-gray-50 p-3 text-sm"><p>Log this conversation as a communication?</p><div class="mt-2 flex gap-2"><Button size="sm" :disabled="busy || hasPendingImages" @click="logFromComment(thread.event)">Review communication</Button><Button size="sm" variant="ghost" @click="delete communicationPrompts[thread.event.name]">Dismiss</Button></div></div>
                  <a v-if="thread.event.source_comment" class="mt-2 block text-xs text-blue-600 hover:underline" :href="'#comment-'+thread.event.source_comment" @click.prevent="jumpToSource(thread.event.source_comment)">From original comment</a><p v-if="thread.event.follow_up_date || thread.event.follow_up_action" class="mt-1 text-xs text-gray-600">Communication follow-up: {{thread.event.follow_up_date}}<span v-if="thread.event.follow_up_action"> {{thread.event.follow_up_action}}</span></p>
                  <p v-for="change in changes(thread.event)" :key="change.label" class="text-xs text-gray-600 mt-1" :title="change.raw">{{change.label}}: {{change.text}}</p>
                  <div class="flex flex-wrap items-center gap-2 mt-2">
                    <Button variant="ghost" size="sm" :disabled="busy || hasPendingImages || (replyRoot && replyRoot!==thread.event.name)" :aria-label="'Reply to '+authorName(thread.event.actor)" @click="startReply(thread.event.name)">Reply</Button>
                    <span v-if="thread.replies.length" class="inline-flex max-w-full items-center gap-2 text-base text-gray-700">
                      <span class="flex -space-x-2" aria-hidden="true"><Avatar v-for="user in replyParticipants(thread)" :key="user+userImage(user)" size="md" class="rounded-full ring-2 ring-white" :label="authorName(user)" :image="userImage(user)"/></span>
                      <FeatherIcon name="corner-up-left" class="h-4 w-4 text-gray-600" aria-hidden="true"/><span class="whitespace-nowrap">{{thread.replies.length}} {{thread.replies.length===1?'reply':'replies'}}</span>
                    </span><span v-if="thread.replies.length" class="text-xs text-gray-500" :title="'Last reply: '+thread.replies[thread.replies.length-1].recorded_at">Last reply {{formatSiteTime(thread.replies[thread.replies.length-1].recorded_at)}}</span>
                  </div>
                </div></div>
                  <div v-if="thread.replies.length || replyRoot===thread.event.name" :id="'thread-'+thread.event.name" class="ml-6 sm:ml-[3.75rem] mr-4 mb-4 border-l-2 border-gray-200 pl-3 space-y-3">
                    <Button v-if="earlierReplyCount(thread)" variant="ghost" size="sm" @click="loadEarlierReplies(thread.event.name)">Load more replies ({{earlierReplyCount(thread)}} earlier)</Button>
                    <div tabindex="-1" v-for="reply in visibleReplies(thread)" :id="'comment-'+reply.name" :key="reply.name" class="flex gap-2"><Avatar :key="reply.actor+userImage(reply.actor)" size="md" :label="authorName(reply.actor)" :image="userImage(reply.actor)"/><div class="min-w-0 flex-1"><div class="flex flex-wrap items-center gap-x-2"><span class="text-sm font-medium">{{authorName(reply.actor)}}</span><span class="text-xs text-gray-500" :title="'Recorded: '+reply.recorded_at">{{formatSiteTime(reply.recorded_at)}}</span></div><div class="prose prose-sm max-w-none text-gray-800 mt-1" v-html="reply.body"></div><div v-if="communicationPrompts[reply.name] && issue.status!=='Resolved'" class="mt-2 rounded border border-gray-200 bg-gray-50 p-2 text-sm"><p>Log this conversation as a communication?</p><Button size="sm" :disabled="busy || hasPendingImages" @click="logFromComment(reply)">Review communication</Button><Button size="sm" variant="ghost" @click="delete communicationPrompts[reply.name]">Dismiss</Button></div><Button variant="ghost" size="sm" class="mt-1" :disabled="busy || hasPendingImages || (replyRoot && replyRoot!==thread.event.name)" :aria-label="'Reply to '+authorName(reply.actor)+' in this thread'" @click="startReply(thread.event.name)">Reply<span class="sr-only"> to {{authorName(reply.actor)}} in this thread</span></Button></div></div>
                    <div v-if="replyRoot===thread.event.name" class="space-y-2"><div :id="'reply-editor-label-'+thread.event.name" class="text-xs font-medium text-gray-600">Reply in thread</div><FileUploader v-for="uploadKey in [issue.name+':reply:'+replyRoot+':'+replyEditorKey]" :key="uploadKey" file-types="image/png,image/jpeg,image/gif,image/webp" :upload-args="{upload_endpoint:'/api/method/unicom.api.upload_image',docname:issue.name,private:true}" :validate-file="f=>validateImage(f,uploadKey)" @success="file=>insertImage(file,replyEditor,'reply',uploadKey)" @failure="delete pendingImages[uploadKey]"><template #default="{openFileSelector,uploading,error:uploadError}"><div @keydown="submitShortcut($event,thread.event.name)"><TextEditor :ref="component=>setReplyEditor(component,thread.event.name)" :key="replyEditorKey" class="timeline-editor rich-editor" :content="replyBody" :fixed-menu="richMenu" :mentions="mentionOptions" placeholder="Write a reply; type @ to mention someone" @change="value=>replyBody=value"><template #bottom><div class="editor-image-action"><Button size="sm" variant="ghost" icon="image" label="Attach image" title="Attach image" :loading="uploading" :disabled="busy || uploading || hasPendingImages" @click="beginImageUpload(openFileSelector,replyEditor,'reply',uploadKey)"/></div></template></TextEditor></div><ErrorMessage :message="uploadError"/><ErrorMessage :message="safeReplyError"/><div class="flex justify-end gap-2"><Button :disabled="busy || uploading || hasPendingImages" @click="cancelReply">Cancel</Button><Button variant="solid" :loading="busy" :disabled="busy || uploading || hasPendingImages" title="Post reply (Ctrl+Enter or Cmd+Enter)" @click="saveReply(thread.event.name)">Post reply</Button></div></template></FileUploader></div>
                  </div>
              </article>
              <div v-else class="flex gap-3 rounded-md bg-gray-50 px-3 py-2 text-xs text-gray-600">
                <FeatherIcon name="activity" class="h-4 w-4 mt-0.5"/><div class="min-w-0"><div><span class="font-medium text-gray-700">{{authorName(thread.event.actor)}}</span> · {{thread.event.kind}} · <span :title="'Recorded: '+thread.event.recorded_at">{{formatSiteTime(thread.event.recorded_at)}}</span></div><div v-if="thread.event.happened_at" :title="'Happened: '+thread.event.happened_at">Happened {{formatSiteTime(thread.event.happened_at)}}</div><div v-if="thread.event.channel">{{thread.event.channel}}</div><div v-if="thread.event.contact">Contact: {{thread.event.contact}}</div><div v-if="thread.event.body" v-html="thread.event.body"></div><p v-for="change in changes(thread.event)" :key="change.label" class="mt-1" :title="change.raw">{{change.label}}: {{change.text}}</p></div>
              </div>
            </div>
          </div>
        </div></section>
        <div role="separator" aria-label="Resize issue details" aria-orientation="vertical" aria-controls="issue-details-sidebar" :aria-valuemin="detailMin" :aria-valuemax="detailLimit" :aria-valuenow="detailWidth" tabindex="0" class="hidden lg:flex lg:col-start-2 lg:row-start-1 lg:row-span-2 relative z-10 w-2 -ml-1 self-stretch cursor-col-resize touch-none justify-center hover:bg-gray-200 focus-visible:bg-gray-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-500" @keydown="detailResizeKey" @dblclick="resetDetailWidth" @pointerdown="startDetailResize" @pointermove="moveDetailResize" @pointerup="endDetailResize" @pointercancel="event=>endDetailResize(event,true)"><span class="w-px bg-gray-200" aria-hidden="true"/></div>
        <aside id="issue-details-sidebar" class="order-2 lg:order-3 min-w-0 border-t lg:border-t-0 lg:border-l text-base break-words lg:col-start-2 lg:row-start-1 lg:row-span-2 lg:sticky lg:top-0 lg:self-start lg:min-h-[calc(100vh-3rem)] lg:max-h-[calc(100vh-3rem)] lg:overflow-y-auto">
          <div class="border-b border-gray-200 px-5 py-4 text-lg font-medium">{{issue.issue_id || issue.name}}</div>
          <div class="flex gap-3 px-5 py-5 border-b border-gray-200"><Avatar size="3xl" :label="issue.issue_id || 'Issue'"/><div class="min-w-0"><div class="text-2xl font-medium break-words">{{authorName(issue.accountable_owner)}}<template v-if="issue.coordination_user"> in coordination with {{authorName(issue.coordination_user)}}</template><template v-if="issue.reference_doctype && issue.reference_name"> on <a class="text-blue-600 hover:underline" :href="'/desk/'+encodeURIComponent(issue.reference_doctype.toLowerCase().replaceAll(' ','-'))+'/'+encodeURIComponent(issue.reference_name)">{{issue.reference_doctype}}: {{issue.reference_name}}</a></template></div><div class="flex gap-2 mt-3"><Button icon="edit-2" label="Edit issue" title="Edit issue" @click="editIssue"/><Button icon="message-square" label="Log communication" title="Log communication" :disabled="issue.status==='Resolved'" @click="logIssue()"/></div></div></div>
          <div class="border-b border-gray-200 px-5 py-4"><div class="flex items-center justify-between"><Button variant="ghost" :icon-left="detailsOpen?'chevron-down':'chevron-right'" :aria-expanded="detailsOpen" aria-controls="issue-details" class="!px-0 font-semibold" @click="detailsOpen=!detailsOpen">Details</Button><Button variant="ghost" icon="edit-2" label="Edit issue details" title="Edit issue details" @click="editIssue"/></div>
            <dl v-if="detailsOpen" id="issue-details" class="mt-4 grid grid-cols-[clamp(110px,42%,180px)_minmax(0,1fr)] gap-x-3 gap-y-4 text-base"><dt class="min-w-0 whitespace-normal text-gray-600" title="Issue Owner">Issue Owner</dt><dd><div v-if="inlineField==='accountable_owner'" ref="inlineRegion" class="space-y-2"><FormControl v-model="inlineValue" type="select" aria-label="Issue Owner" :options="userOptions" @change="saveInline"/><ErrorMessage :message="safeInlineError"/><Button v-if="inlineError" size="sm" @click="saveInline">Retry</Button></div><Button v-else variant="ghost" class="!h-auto !p-0" aria-label="Edit Issue Owner" @click="startInline('accountable_owner')"><template #prefix><Avatar size="sm" :label="authorName(issue.accountable_owner)" :image="userImage(issue.accountable_owner)"/></template>{{authorName(issue.accountable_owner)}}</Button></dd><dt class="min-w-0 whitespace-normal text-gray-600" title="Coordinating with">Coordinating with</dt><dd><div v-if="inlineField==='coordination_user'" ref="inlineRegion" class="space-y-2"><FormControl v-model="inlineValue" type="select" aria-label="Coordinating with" :options="inlineCoordinationOptions" @change="saveInline"/><ErrorMessage :message="safeInlineError"/><Button v-if="inlineError" size="sm" @click="saveInline">Retry</Button></div><Button v-else variant="ghost" class="!h-auto !p-0" aria-label="Edit Coordinating with" @click="startInline('coordination_user')"><template v-if="issue.coordination_user" #prefix><Avatar size="sm" :label="authorName(issue.coordination_user)" :image="userImage(issue.coordination_user)"/></template>{{issue.coordination_user ? authorName(issue.coordination_user) : '—'}}</Button></dd><template v-if="issue.reference_doctype && issue.reference_name"><dt class="min-w-0 whitespace-normal text-gray-600" title="Source document">Source document</dt><dd class="min-w-0 break-words"><a class="text-blue-600 hover:underline" :href="'/desk/'+encodeURIComponent(issue.reference_doctype.toLowerCase().replaceAll(' ','-'))+'/'+encodeURIComponent(issue.reference_name)">{{issue.reference_doctype}}: {{issue.reference_name}}</a></dd></template><dt class="min-w-0 whitespace-normal text-gray-600" title="Next action date">Next action date</dt><dd>{{issue.next_action_date||'—'}}</dd><template v-if="issue.resolution_note"><dt class="min-w-0 whitespace-normal text-gray-600" title="Resolution">Resolution</dt><dd>{{issue.resolution_note}}</dd></template><dt class="min-w-0 whitespace-normal text-gray-600" title="Participants">Participants</dt><dd :title="participantsFor(issue).map(user=>authorName(user)).join(', ')"><span v-if="participantsFor(issue).length" class="flex flex-wrap items-center -space-x-0.5"><span v-for="user in participantsFor(issue).slice(0,3)" :key="user" role="img" :aria-label="authorName(user)" :title="authorName(user)"><Avatar :key="user+userImage(user)" size="sm" class="rounded-full bg-gray-100 ring-2 ring-white" :label="authorName(user)" :image="userImage(user)"/></span><span v-if="participantsFor(issue).length>3" class="ml-2 text-xs text-gray-600">+{{participantsFor(issue).length-3}}</span></span><span v-else>—</span></dd><dt class="min-w-0 whitespace-normal text-gray-600" title="Follow-up assignees">Follow-up assignees</dt><dd>{{issue.access.filter(x=>x.reason==='Follow-up').map(x=>authorName(x.user)).join(', ')||'—'}}</dd></dl>
          </div>
          <div class="px-5 py-4"><Button variant="ghost" :icon-left="attachmentsOpen?'chevron-down':'chevron-right'" :aria-expanded="attachmentsOpen" aria-controls="issue-attachments" class="!px-0 font-semibold" @click="attachmentsOpen=!attachmentsOpen">Attachments</Button><div v-if="attachmentsOpen" id="issue-attachments" class="mt-3"><a v-for="f in issue.attachments" :key="f.name" :href="f.file_url" target="_blank" class="block text-blue-600 underline">{{f.file_name}}</a><FileUploader :upload-args="{upload_endpoint:'/api/method/unicom.api.upload_attachment',docname:issue.name,private:true}" :validate-file="f=>f.size>10*1024*1024?'Maximum attachment size is 10 MB':null" @success="uploadDone"><template #default="{openFileSelector,uploading,error:uploadError}"><Button class="mt-2" :loading="uploading" @click="openFileSelector">Add private file</Button><ErrorMessage :message="uploadError"/></template></FileUploader></div></div>
        </aside>
      </div>
    </div>
  </main>
</div>
<Dialog v-model="showNew" :options="{title:'New issue',size:'2xl'}"><template #body-content><ErrorMessage v-if="error" class="mb-3" :message="safeError"/><div class="space-y-3"><FormControl v-model="form.title" label="Title"/><div><label id="new-description-label" class="text-sm">Description</label><TextEditor :ref="component=>labelEditor(component,null,'new-description-label')" class="rich-editor" :content="form.description" :fixed-menu="richMenu" :mentions="mentionOptions" placeholder="Write a description; type @ to mention someone" @change="value=>form.description=value"/></div><p class="text-xs text-gray-500">Images can be added after creating the issue.</p><div class="grid gap-3 sm:grid-cols-2"><FormControl v-model="form.accountable_owner" type="select" label="Issue Owner" :options="userOptions"/><FormControl v-model="form.coordination_user" type="select" label="Coordinating with" :options="coordinationOptions"/></div><div><label class="text-sm">Follow-up assignees</label><div class="flex gap-2"><FormControl v-model="followup" type="select" :options="userOptions"/><Button @click="add(form.follow_up_assignees,followup);followup=''">Add</Button></div><div v-for="u in form.follow_up_assignees" :key="u" class="text-sm">{{u}} <Button variant="ghost" @click="form.follow_up_assignees=form.follow_up_assignees.filter(x=>x!==u)">Remove</Button></div></div></div></template><template #actions><Button variant="solid" :loading="busy" @click="create">Create issue</Button></template></Dialog>
<Dialog v-model="showEdit" :options="{title:'Edit issue',size:'2xl'}"><template #body-content><ErrorMessage v-if="error" class="mb-3" :message="safeError"/><div class="space-y-3"><FormControl v-model="edit.title" label="Title"/><div><label id="edit-description-label" class="text-sm">Description</label><TextEditor :ref="component=>labelEditor(component,null,'edit-description-label')" class="rich-editor" :content="edit.description" :fixed-menu="richMenu" :mentions="mentionOptions" placeholder="Write a description; type @ to mention someone" @change="value=>edit.description=value"/></div><FormControl v-model="edit.accountable_owner" type="select" label="Issue Owner" :options="userOptions"/><FormControl v-model="edit.coordination_user" type="select" label="Coordinating with" :options="editCoordinationOptions"/><FormControl v-model="edit.status" type="select" label="Status" :options="statuses"/><FormControl v-model="edit.next_action" label="Next action"/><FormControl v-model="edit.next_action_date" type="date" label="Next action date"/><FormControl v-model="edit.resolution_note" type="textarea" label="Resolution note (required to resolve)"/><div><div class="text-sm">Participants</div><FormControl v-model="editParticipant" type="select" :options="userOptions"/><Button @click="add(edit.participants,editParticipant);editParticipant=''">Add</Button><div v-for="u in edit.participants" :key="u" class="text-sm">{{u}} <Button variant="ghost" @click="edit.participants=edit.participants.filter(x=>x!==u)">Remove</Button></div></div><div><div class="text-sm">Follow-up assignees</div><FormControl v-model="editFollowup" type="select" :options="userOptions"/><Button @click="add(edit.follow_up_assignees,editFollowup);editFollowup=''">Add</Button><div v-for="u in edit.follow_up_assignees" :key="u" class="text-sm">{{u}} <Button variant="ghost" @click="edit.follow_up_assignees=edit.follow_up_assignees.filter(x=>x!==u)">Remove</Button></div></div></div></template><template #actions><Button variant="solid" :loading="busy" @click="saveEdit">Save</Button></template></Dialog>
<Dialog v-model="showResolve" :disable-outside-click-to-close="busy" :options="{title:'Resolve issue',size:'lg'}"><template #body-content><FormControl v-model="resolutionNote" type="textarea" label="Resolution note" required/><ErrorMessage :message="safeResolveError"/></template><template #actions><Button :disabled="busy" @click="showResolve=false">Cancel</Button><Button variant="solid" :loading="busy" :disabled="busy" @click="resolveIssue">Resolve</Button></template></Dialog>
<Dialog v-model="showLog" :options="{title:'Log communication',size:'2xl'}"><template #body-content><ErrorMessage v-if="error" class="mb-3" :message="safeError"/><div class="space-y-3"><FormControl v-model="log.channel" type="select" label="Channel" :options="[{label:'Select channel',value:''},...channels]"/><p v-if="log.source_comment" class="text-sm text-gray-600">Confirm the channel and when this communication happened. The original comment stays unchanged.</p><FormControl v-model="log.happened_at" type="datetime-local" label="Happened at"/><FormControl v-model="log.contact" label="Contact / person"/><div><label class="text-sm">Outcome / body (type @ to mention a user)</label><TextEditor :content="log.body" :mentions="mentionOptions" @change="value=>log.body=value"/></div><p v-if="issue.next_action_date" class="text-sm text-gray-600">Current issue follow-up date: {{issue.next_action_date}}</p><FormControl v-model="log.next_action" label="Communication follow-up action (optional)"/><FormControl v-model="log.next_action_date" type="date" label="Communication follow-up date"/><label class="flex items-center gap-2 text-sm"><input v-model="log.set_follow_up" type="checkbox">Set as issue follow-up</label><p class="text-xs text-gray-600">Only updates the issue date when checked. The issue’s next action changes only when an action is entered.</p><FormControl v-model="log.resolution_note" type="textarea" label="Resolution note (optional; resolves issue)"/></div></template><template #actions><Button variant="solid" :loading="busy" @click="saveLog">Save communication</Button></template></Dialog>
</template>
