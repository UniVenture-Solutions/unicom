<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { Button, FormControl, Dialog, TextEditor, Badge, Avatar, FeatherIcon, ListView, ListFooter, FileUploader, ErrorMessage, Breadcrumbs, Dropdown, Popover } from 'frappe-ui'

const view=ref('mine'), rows=ref([]), issue=ref(null), people=ref([]), error=ref(''), busy=ref(false), page=ref(0), search=ref(''), filter=ref(''), showNew=ref(false), showLog=ref(false), showEdit=ref(false)
const currentUser=ref(''), sidebarCollapsed=ref(false), pageLength=ref(20), detailsOpen=ref(true), attachmentsOpen=ref(true)
const assignDraft=ref([]), assignError=ref(''), assignSaving=ref(false), assignContext=ref(0), assignOpen=ref(false), assignQuery=ref('')
const showResolve=ref(false), resolutionNote=ref(''), resolveError=ref('')
const timelineCategories=['Comments','Communications','Notes','Activity']
const timelineSelection=ref(new Set(timelineCategories))
const inlineField=ref(''), inlineValue=ref(''), inlineError=ref(''), inlineEditor=ref(null), inlineKey=ref(0)
const inlineRegion=ref(null), inlineSaving=ref(false), inlineDeferred=ref(false)
let inlineSavePromise=null, inlineOverlay=false, inlineSaveAgain=false
const pendingImages=reactive({})
const hasPendingImages=computed(()=>Object.values(pendingImages).some(Boolean))
const richMenu=[['Paragraph','Heading 2','Heading 3','Heading 4'],'Separator','Bold','Italic','Separator','Bullet List','Numbered List','Separator','Align Left','Align Center','Align Right','FontColor','Separator','Link','Blockquote','Code','Horizontal Rule',['InsertTable','AddColumnBefore','AddColumnAfter','DeleteColumn','AddRowBefore','AddRowAfter','DeleteRow','MergeCells','SplitCell','ToggleHeaderColumn','ToggleHeaderRow','ToggleHeaderCell','DeleteTable']]
const commentBody=ref(''), commentError=ref(''), commentEditorKey=ref(0)
const commentEditor=ref(null), replyEditor=ref(null)
const replyRoot=ref(null), replyBody=ref(''), replyError=ref(''), replyEditorKey=ref(0), replyWindowSizes=ref({})
watch(() => issue.value?.name, () => { commentBody.value=''; commentError.value=''; commentEditorKey.value++; replyRoot.value=null; replyBody.value=''; replyError.value=''; replyEditorKey.value++; replyWindowSizes.value={}; timelineSelection.value=new Set(timelineCategories); for(const key of Object.keys(pendingImages)) delete pendingImages[key]; pendingImageTargets.clear(); inlineField.value=''; inlineValue.value=''; inlineError.value=''; inlineDeferred.value=false; inlineOverlay=false; inlineSaveAgain=false;assignContext.value++;assignDraft.value=[];assignError.value='';assignOpen.value=false;assignQuery.value='';showResolve.value=false;resolutionNote.value='';resolveError.value='' }, {flush:'sync'})
const blank=()=>({title:'',description:'',accountable_owner:'',coordination_user:'',next_action:'',next_action_date:'',participants:[],follow_up_assignees:[]})
const form=reactive(blank()), edit=reactive({}), log=reactive({channel:'Internal Note',happened_at:'',contact:'',body:'',next_action:'',next_action_date:'',resolution_note:''})
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
const participants=ref(''), followup=ref(''), editParticipant=ref(''), editFollowup=ref('')
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
async function load(){await run(async()=>{rows.value=await api('list_issues',{view:view.value,status:filter.value,search:search.value,start:page.value*pageLength.value,page_length:pageLength.value})})}
function setPageLength(value){pageLength.value=value;page.value=0;load()}
async function canLeaveInline(){if(inlineDeferred.value || hasPendingImages.value)return false;const name=issue.value?.name;if(inlineSavePromise && !await inlineSavePromise)return false;if(issue.value?.name!==name)return false;return !inlineField.value || inlineValue.value===(issue.value?.[inlineField.value]||'') || window.confirm('Discard your unsaved issue edit?')}
async function open(name,push=true,skipGuard=false){if(!skipGuard && issue.value?.name!==name && !await canLeaveInline())return;await run(async()=>{issue.value=await api('get_issue',{name}); if(push) history.pushState({},'', '/unicom/'+encodeURIComponent(name))})}
async function goList(v){if(!await canLeaveInline())return;view.value=v;issue.value=null;page.value=0;history.pushState({},'','/unicom');load()}
function resetForm(){Object.assign(form,blank())}
async function create(){if(!await canLeaveInline())return;await run(async()=>{const doc=await api('create_issue',form,true);showNew.value=false;resetForm();issue.value=doc;history.pushState({},'','/unicom/'+encodeURIComponent(doc.name))})}
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
  if(inlineField.value==='description' && inlineOverlay && (target.closest('#frappeui-popper-root') || target.closest('[role=dialog]')))return
  inlineOverlay=false
  if(inlineSaving.value)inlineSaveAgain=true;else saveInline()
}
function onInlineFocusOut(){setTimeout(()=>{const active=document.activeElement;if(active && active!==document.body && active!==document.documentElement)inlineInteraction({target:active})},0)}
function setInlineEditor(component){inlineEditor.value=component;labelEditor(component,inlineEditor,'description-editor-label')}
async function editIssue(){if(inlineField.value && !await saveInline())return false;Object.assign(edit,{title:issue.value.title,description:issue.value.description||'',accountable_owner:issue.value.accountable_owner,coordination_user:issue.value.coordination_user||'',status:issue.value.status,next_action:issue.value.next_action||'',next_action_date:issue.value.next_action_date||'',resolution_note:issue.value.resolution_note||'',participants:issue.value.access.filter(x=>x.reason==='Participant').map(x=>x.user),follow_up_assignees:issue.value.access.filter(x=>x.reason==='Follow-up').map(x=>x.user)});showEdit.value=true;return true}
async function openAssignments(togglePopover){
  if(assignOpen.value){togglePopover(false);return}
  const name=issue.value?.name
  if(inlineField.value && !await saveInline())return
  if(!issue.value || issue.value.name!==name || busy.value)return
  assignDraft.value=[...new Set(issue.value.access.filter(x=>x.reason==='Participant' && x.user).map(x=>x.user))]
  assignError.value='';assignQuery.value='';togglePopover(true)
}
function toggleAssignment(user){if(assignSaving.value)return;assignDraft.value=assignDraft.value.includes(user)?assignDraft.value.filter(value=>value!==user):[...assignDraft.value,user]}
function toggleAssignMe(){if(!currentUser.value || currentUser.value==='Guest' || assignSaving.value)return;assignDraft.value=assignDraft.value.includes(currentUser.value)?assignDraft.value.filter(user=>user!==currentUser.value):[...assignDraft.value,currentUser.value]}
async function applyAssignments(close){
  if(busy.value || assignSaving.value || !issue.value)return
  const name=issue.value.name, context=assignContext.value, participants=[...assignDraft.value]
  const existing=[...new Set(issue.value.access.filter(x=>x.reason==='Participant' && x.user).map(x=>x.user))]
  if(participants.length===existing.length && participants.every(user=>existing.includes(user))){close();return}
  assignSaving.value=true;busy.value=true;assignError.value=''
  try{const updated=await api('update_issue',{name,values:{participants}},true);if(issue.value?.name===name && assignContext.value===context){issue.value=updated;close()}}
  catch(e){if(issue.value?.name===name && assignContext.value===context)assignError.value=e.message}
  finally{assignSaving.value=false;busy.value=false}
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
  if(issue.value.status==='Resolved' && (!issue.value.next_action || !issue.value.next_action_date)){
    if(await editIssue())edit.status=status
    return
  }
  await run(async()=>{const updated=await api('update_issue',{name,values:{status}},true);if(issue.value?.name===name)issue.value=updated})
}
async function saveEdit(){await run(async()=>{issue.value=await api('update_issue',{name:issue.value.name,values:edit},true);showEdit.value=false})}
async function logIssue(){if(inlineField.value && !await saveInline())return;Object.assign(log,{channel:'Internal Note',happened_at:new Date(Date.now()-new Date().getTimezoneOffset()*60000).toISOString().slice(0,16),contact:'',body:'',next_action:issue.value.next_action||'',next_action_date:issue.value.next_action_date||'',resolution_note:''});showLog.value=true}
async function saveLog(){await run(async()=>{const dom=new DOMParser().parseFromString(log.body,'text/html'); const mentions=[...dom.querySelectorAll('[data-type="mention"][data-id]')].map(x=>x.getAttribute('data-id'));issue.value=await api('log_communication',{name:issue.value.name,...log,mentions},true);showLog.value=false})}
function submitShortcut(event,root=null){
  if(event.key!=='Enter' || !(event.metaKey || event.ctrlKey) || event.isComposing || event.keyCode===229)return
  event.preventDefault()
  if(event.repeat || busy.value || hasPendingImages.value)return
  if(root)saveReply(root);else saveComment()
}
async function saveComment(){
  if(busy.value) return
  busy.value=true; commentError.value=''
  const name=issue.value.name
  try { const updated=await api('add_comment',{name,body:commentBody.value},true); if(issue.value?.name===name){issue.value=updated;commentBody.value='';commentEditorKey.value++} }
  catch(e){if(issue.value?.name===name) commentError.value=e.message}
  finally{busy.value=false}
}
function replyParticipants(thread){return [...new Set(thread.replies.map(reply=>reply.actor).filter(Boolean))].slice(0,3)}
function visibleReplies(thread){return thread.replies.slice(-(replyWindowSizes.value[thread.event.name] || 3))}
function earlierReplyCount(thread){return Math.max(0,thread.replies.length-visibleReplies(thread).length)}
function loadEarlierReplies(root){replyWindowSizes.value={...replyWindowSizes.value,[root]:(replyWindowSizes.value[root] || 3)+3};if(replyRoot.value===root) nextTick(()=>{if(replyRoot.value===root) replyEditor.value?.editor?.commands.focus()})}
function labelEditor(component, current, labelId){
  if(!component) return
  nextTick(()=>{
    if(current.value!==component) return
    const editor=component.editor
    if(!editor || editor.isDestroyed) return
    const props=editor.options.editorProps || {}
    editor.setOptions({editorProps:{...props,handlePaste:(_view,event)=>Array.from(event.clipboardData?.items||[]).some(item=>item.type.startsWith('image/')),handleDrop:(_view,event)=>Array.from(event.dataTransfer?.files||[]).some(file=>file.type.startsWith('image/')),attributes:{...props.attributes,role:'textbox','aria-multiline':'true','aria-labelledby':labelId}}})
  })
}
function setCommentEditor(component){commentEditor.value=component;labelEditor(component,commentEditor,'comment-editor-label')}
function setReplyEditor(component,root){replyEditor.value=component;labelEditor(component,replyEditor,'reply-editor-label-'+root)}
const pendingImageTargets = new Map()
function validateImage(file, key){if(file.size>10*1024*1024)return 'Maximum image size is 10 MB'; pendingImages[key]=true;return null}
function beginImageUpload(open, target, scope, key){
  pendingImageTargets.set(key,{name:issue.value?.name,editor:target?.editor,root:replyRoot.value,commentKey:commentEditorKey.value,replyKey:replyEditorKey.value,field:inlineField.value})
  open()
}
function insertImage(file, target, scope, key){
  const context=pendingImageTargets.get(key); pendingImageTargets.delete(key); delete pendingImages[key]
  const uploadedFor=new URL(file.file_url,location.origin).searchParams.get('name')
  const editor=target?.editor
  if(!context || !issue.value || context.name!==issue.value.name || uploadedFor!==context.name || !editor || editor!==context.editor || editor.isDestroyed) return
  if(scope==='comment' && context.commentKey!==commentEditorKey.value) return
  if(scope==='reply' && (context.replyKey!==replyEditorKey.value || context.root!==replyRoot.value)) return
  if(scope==='description' && (context.field!=='description' || inlineField.value!=='description')) return
  const src='/api/method/unicom.api.inline_image?'+new URLSearchParams({name:uploadedFor,attachment:file.name})
  editor.chain().focus().setImage({src,alt:file.file_name}).run()
  if(!issue.value.attachments.some(x=>x.name===file.name)) issue.value.attachments.push(file)
  if(scope==='description' && inlineDeferred.value){inlineDeferred.value=false;nextTick(()=>saveInline())}
}
function imageUploadFailed(key,scope){delete pendingImages[key];pendingImageTargets.delete(key);if(scope==='description' && inlineDeferred.value){inlineDeferred.value=false;inlineError.value='Image upload failed. Your description draft is still available.'}}
function startReply(root){if(hasPendingImages.value)return;if(replyRoot.value!==root){replyRoot.value=root;replyBody.value='';replyError.value='';replyEditorKey.value++} nextTick(()=>replyEditor.value?.editor?.commands.focus())}
function cancelReply(){replyRoot.value=null;replyBody.value='';replyError.value='';replyEditorKey.value++}
async function saveReply(root){
  if(busy.value || replyRoot.value!==root) return
  busy.value=true; replyError.value=''
  const name=issue.value.name
  try { const updated=await api('add_comment',{name,body:replyBody.value,reply_to:root},true); if(issue.value?.name===name && replyRoot.value===root){issue.value=updated;cancelReply()} }
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
function changes(event){try{const data=JSON.parse(event.changes||'{}');return Object.entries(data).map(([key,value])=>({label:fieldLabel(key),text:`${changeValue(value?.from,key)} → ${changeValue(value?.to,key)}`,raw:JSON.stringify(value)}))}catch{return event.changes ? [{label:'Changes',text:event.changes,raw:event.changes}] : []}}

onBeforeUnmount(()=>{document.removeEventListener('pointerdown',inlineInteraction,true);document.removeEventListener('focusin',inlineInteraction,true);document.removeEventListener('focusout',onInlineFocusOut,true)})
onMounted(async()=>{document.addEventListener('pointerdown',inlineInteraction,true);document.addEventListener('focusin',inlineInteraction,true);document.addEventListener('focusout',onInlineFocusOut,true);fetch('/api/method/frappe.auth.get_logged_user',{credentials:'same-origin'}).then(r=>r.ok?r.json():null).then(r=>{currentUser.value=r?.message||''}).catch(()=>{});await run(async()=>{people.value=await api('users'); const name=decodeURIComponent(location.pathname.replace(/^\/unicom\/?/,'')); if(name) await open(name,false); else await load()});window.onpopstate=async()=>{const name=decodeURIComponent(location.pathname.replace(/^\/unicom\/?/,''));if(name){if(issue.value?.name!==name && !await canLeaveInline()){history.pushState({},'', '/unicom/'+encodeURIComponent(issue.value.name));return}open(name,false,true)}else{if(!await canLeaveInline()){history.pushState({},'', '/unicom/'+encodeURIComponent(issue.value.name));return}issue.value=null;load()}};window.addEventListener('beforeunload',event=>{if(inlineField.value && inlineValue.value!==(issue.value?.[inlineField.value]||'')){event.preventDefault();event.returnValue=''}})})
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
    <nav aria-label="Issues" class="px-2 pb-2 flex flex-row md:flex-col gap-1 overflow-x-auto md:overflow-x-hidden">
      <Button v-for="item in [{view:'mine',label:'My Issues',icon:'user'},{view:'overdue',label:'Overdue',icon:'clock'},{view:'all',label:'All Accessible Issues',icon:'list'}]" :key="item.view" :variant="'ghost'" :icon-left="item.icon" class="!justify-start !h-7 !rounded !text-base !font-[420] !text-gray-700 [&>svg]:text-gray-800 shrink-0 md:w-full" :class="[sidebarCollapsed?'md:!justify-center':'',view===item.view?'!bg-white !text-gray-900 shadow-sm ring-1 ring-gray-200':'']" :aria-label="item.label" :aria-current="view===item.view?'page':undefined" :title="item.label" @click="goList(item.view)"><span :class="sidebarCollapsed?'md:sr-only':''">{{item.label}}</span></Button>
    </nav>
    <div class="hidden md:flex mt-auto p-2 flex-col gap-1">
      <Button variant="ghost" icon-left="help-circle" class="w-full !justify-start !h-7 !rounded !text-base !font-[420] !text-gray-700 [&>svg]:text-gray-800" :class="sidebarCollapsed?'!justify-center':''" aria-label="Frappe help" title="Frappe help" @click="openHelp"><span :class="sidebarCollapsed?'sr-only':''">Help</span></Button>
      <Button variant="ghost" :icon-left="sidebarCollapsed?'chevrons-right':'chevrons-left'" class="w-full !justify-start !h-7 !rounded !text-base !font-[420] !text-gray-700 [&>svg]:text-gray-800" :class="sidebarCollapsed?'!justify-center':''" :aria-label="sidebarCollapsed?'Expand sidebar':'Collapse sidebar'" :title="sidebarCollapsed?'Expand sidebar':'Collapse sidebar'" @click="sidebarCollapsed=!sidebarCollapsed"><span :class="sidebarCollapsed?'sr-only':''">{{sidebarCollapsed?'Expand sidebar':'Collapse sidebar'}}</span></Button>
    </div>
  </aside>
  <main class="min-w-0 min-h-0 flex-1 flex flex-col">
    <header class="border-b border-gray-200 h-12 shrink-0 px-4 sm:px-6 flex items-center justify-between gap-2"><div class="min-w-0 flex-1 overflow-hidden"><Breadcrumbs class="unicom-breadcrumbs" :items="issue ? [{label:'Issues',onClick:()=>goList(view)},{label:'List',kind:'list',onClick:()=>goList(view)},{label:issue.title}] : [{label:'Issues',onClick:()=>goList(view)},{label:'List',kind:'list',onClick:()=>goList(view)}]"><template #prefix="{item}"><FeatherIcon v-if="item.kind==='list'" name="menu" class="h-4 w-4 mr-1 text-gray-600"/></template></Breadcrumbs></div><div class="flex shrink-0 items-center gap-2"><Popover v-if="issue" v-model:show="assignOpen" placement="bottom-end"><template #target="{togglePopover}"><Button :disabled="busy &amp;&amp; !inlineSaving" icon-left="user-plus" title="Assign To" @click="openAssignments(togglePopover)"><span class="hidden sm:inline">Assign To</span><span v-if="issue.access.some(x=>x.reason==='Participant')" class="ml-1">{{new Set(issue.access.filter(x=>x.reason==='Participant' &amp;&amp; x.user).map(x=>x.user)).size}}</span></Button></template><template #body="{togglePopover}"><div class="mt-1 w-72 max-w-[calc(100vw-2rem)] rounded-lg border border-gray-200 bg-white p-2 shadow-lg" :class="assignSaving ? 'pointer-events-none opacity-60' : ''"><FormControl v-model="assignQuery" placeholder="Search users" aria-label="Search users"/><div class="mt-2 max-h-52 overflow-y-auto"><Button v-for="option in filteredAssignmentOptions" :key="option.value" variant="ghost" class="w-full !justify-start" :aria-pressed="assignDraft.includes(option.value)" @click="toggleAssignment(option.value)"><template #prefix><FeatherIcon v-if="assignDraft.includes(option.value)" name="check" class="h-4 w-4"/><span v-else class="h-4 w-4"/></template><span class="truncate">{{option.label}}</span></Button><div v-if="!filteredAssignmentOptions.length" class="p-2 text-sm text-gray-500">No users found</div></div><div class="mt-2 border-t border-gray-200 pt-2 space-y-2"><div class="text-xs text-gray-600">Selected: {{assignDraft.length ? assignDraft.map(user=>authorName(user)).join(', ') : 'None'}}</div><p v-if="assignDraft.some(user=>user!==currentUser &amp;&amp; !people.some(person=>person.name===user))" class="text-xs text-gray-600">If an unavailable participant prevents saving, remove them before applying changes.</p><ErrorMessage :message="safeAssignError"/><div class="flex flex-wrap items-center gap-2"><Button size="sm" :disabled="assignSaving || !currentUser || currentUser==='Guest'" @click="toggleAssignMe">{{assignDraft.includes(currentUser) ? 'Remove me' : 'Assign to me'}}</Button><Button size="sm" :disabled="assignSaving" @click="togglePopover(false)">Cancel</Button><Button size="sm" variant="solid" :loading="assignSaving" :disabled="assignSaving" @click="applyAssignments(()=>togglePopover(false))">Apply</Button></div></div></div></template></Popover><Dropdown v-if="issue" :options="statuses.map(status=>({label:status,onClick:()=>changeStatus(status)}))"><Button :disabled="busy &amp;&amp; !inlineSaving" class="whitespace-nowrap" :title="'Status: '+issue.status"><template #prefix><span :class="statusColor(issue.status)" class="h-2 w-2 rounded-full" aria-hidden="true"/></template>{{issue.status}}<span v-if="issue.overdue" class="ml-1 text-red-600">· Overdue</span><template #suffix><FeatherIcon name="chevron-down" class="h-4 w-4"/></template></Button></Dropdown><Button variant="solid" icon-left="plus" class="shrink-0 whitespace-nowrap" @click="showNew=true">Create</Button></div></header>
    <ErrorMessage v-if="error" class="mx-6 mt-4" :message="safeError"/>
    <template v-if="!issue">
      <div class="min-h-0 flex-1 flex flex-col">
        <div class="flex gap-2 px-4 sm:px-6 py-4 flex-wrap shrink-0"><FormControl v-model="search" placeholder="Search title" aria-label="Search title" @keydown.enter="page=0;load()"/><FormControl type="select" v-model="filter" aria-label="Filter by status" :options="[{label:'All statuses',value:''},...statuses.map(x=>({label:x,value:x}))]" @change="page=0;load()"/><Button @click="page=0;load()">Search</Button></div>
        <div class="min-h-0 flex-1 overflow-auto px-4 sm:px-6"><ListView :columns="columns" :rows="rows" row-key="name" :options="{selectable:false,onRowClick:row=>open(row.name),emptyState:{title:'No issues found'}}"><template #cell="{column,row,item}"><Badge v-if="column.key==='status'" :theme="row.overdue?'red':'gray'">{{row.overdue?'Overdue · ':''}}{{item}}</Badge><span v-else-if="column.key==='accountable_owner'" class="flex items-center gap-2 min-w-0"><Avatar :key="item+userImage(item)" size="sm" :label="authorName(item)" :image="userImage(item)"/><span class="text-sm truncate">{{authorName(item)}}</span></span><span v-else class="text-sm truncate">{{item||'—'}}</span></template></ListView></div>
        <ListFooter class="px-4 sm:px-6 py-3 border-t border-gray-200 shrink-0" :model-value="pageLength" @update:model-value="setPageLength"><template #right><div class="flex items-center gap-2"><span class="text-sm text-gray-500">Page {{page+1}} · {{rows.length}} {{rows.length===1?'issue':'issues'}} shown</span><Button :disabled="page===0" @click="page--;load()">Previous</Button><Button :disabled="rows.length<pageLength" @click="page++;load()">Next</Button></div></template></ListFooter>
      </div>
    </template>
    <div v-else class="min-h-0 flex-1 overflow-y-auto">
      <div class="grid min-w-0 lg:grid-cols-[minmax(0,1fr)_350px] lg:grid-rows-[auto_1fr]">
        <div class="order-1 w-full min-w-0 max-w-4xl mx-auto p-6 flex flex-wrap justify-between gap-4 items-start"><div class="min-w-0 flex-1 basis-64"><div v-if="inlineField==='title'" ref="inlineRegion" class="space-y-2"><FormControl v-model="inlineValue" label="Title" @keydown.enter="saveInline" @keydown.esc="cancelInline"/><ErrorMessage :message="safeInlineError"/><Button v-if="inlineError" size="sm" @click="saveInline">Retry</Button></div><h1 v-else class="text-2xl font-semibold break-words"><Button variant="ghost" class="!h-auto !p-0 !text-2xl" aria-label="Edit title" @click="startInline('title')">{{issue.title}}</Button></h1><p class="text-sm text-gray-500 mt-2">{{issue.issue_id || issue.name}} · Created by {{authorName(issue.owner)}}</p></div></div>
        <section class="order-3 lg:order-2 w-full min-w-0 max-w-4xl mx-auto px-6 pb-6 space-y-6 break-words"><div><h2 class="font-semibold mb-2">Description</h2><div v-if="inlineField==='description'" ref="inlineRegion" class="space-y-2"><div id="description-editor-label" class="text-sm">Edit description</div><FileUploader v-for="uploadKey in [issue.name+':description:'+inlineKey]" :key="uploadKey" file-types="image/png,image/jpeg,image/gif,image/webp" :upload-args="{upload_endpoint:'/api/method/unicom.api.upload_image',docname:issue.name,private:true}" :validate-file="f=>validateImage(f,uploadKey)" @success="file=>insertImage(file,inlineEditor,'description',uploadKey)" @failure="imageUploadFailed(uploadKey,'description')"><template #default="{openFileSelector,uploading,error:uploadError}"><TextEditor :ref="setInlineEditor" class="rich-editor" :content="inlineValue" :fixed-menu="richMenu" @change="value=>inlineValue=value"><template #bottom><div class="editor-image-action"><Button size="sm" variant="ghost" icon="image" label="Attach image" title="Attach image" :loading="uploading" :disabled="busy || uploading || pendingImages[uploadKey]" @click="beginImageUpload(openFileSelector,inlineEditor,'description',uploadKey)"/></div></template></TextEditor><ErrorMessage :message="uploadError"/><ErrorMessage :message="safeInlineError"/><Button v-if="inlineError" size="sm" @click="saveInline">Retry</Button></template></FileUploader></div><div v-else><div class="prose prose-sm max-w-none text-gray-700" role="button" tabindex="0" aria-label="Edit description" @click="editDescription" @keydown.enter="editDescription" @keydown.space="editDescription" v-html="issue.description || '—'"></div></div></div><div>
          <div class="flex flex-wrap items-center justify-between gap-2 mb-4"><h2 class="font-semibold">Timeline</h2><div role="group" aria-label="Filter timeline" class="flex flex-wrap gap-1"><Button size="sm" :variant="allTimelineSelected?'subtle':'ghost'" :aria-pressed="allTimelineSelected" :disabled="hasPendingImages" @click="selectAllTimeline">All</Button><Button v-for="category in timelineCategories" :key="category" size="sm" :variant="!allTimelineSelected && timelineSelection.has(category)?'subtle':'ghost'" :aria-pressed="!allTimelineSelected && timelineSelection.has(category)" :disabled="hasPendingImages" @click="toggleTimelineCategory(category)">{{category}}</Button></div></div>
          <div class="mb-4"><Button variant="solid" :disabled="(busy &amp;&amp; !inlineSaving) || issue.status==='Resolved'" @click="logIssue">Log communication</Button></div>
          <p v-if="hasPendingImages" role="status" class="mb-3 text-xs text-gray-600">Uploading image… Timeline filters will be available when the upload finishes.</p><div class="mb-8 rounded-lg border border-gray-200 p-3 space-y-2">
            <div id="comment-editor-label" class="text-xs font-medium text-gray-600">Add a comment</div><FileUploader v-for="uploadKey in [issue.name+':comment:'+commentEditorKey]" :key="uploadKey" file-types="image/png,image/jpeg,image/gif,image/webp" :upload-args="{upload_endpoint:'/api/method/unicom.api.upload_image',docname:issue.name,private:true}" :validate-file="f=>validateImage(f,uploadKey)" @success="file=>insertImage(file,commentEditor,'comment',uploadKey)" @failure="delete pendingImages[uploadKey]"><template #default="{openFileSelector,uploading,error:uploadError}"><div @keydown="submitShortcut($event)"><TextEditor :ref="setCommentEditor" :key="commentEditorKey" class="timeline-editor rich-editor" :content="commentBody" :fixed-menu="richMenu" :mentions="mentionOptions" placeholder="Write a comment; type @ to mention someone" @change="value=>commentBody=value"><template #bottom><div class="editor-image-action"><Button size="sm" variant="ghost" icon="image" label="Attach image" title="Attach image" :loading="uploading" :disabled="busy || uploading || pendingImages[uploadKey]" @click="beginImageUpload(openFileSelector,commentEditor,'comment',uploadKey)"/></div></template></TextEditor></div><ErrorMessage :message="uploadError"/><ErrorMessage :message="safeCommentError"/><div class="flex justify-end"><Button variant="solid" :loading="busy" :disabled="busy || uploading || pendingImages[uploadKey]" title="Post comment (Ctrl+Enter or Cmd+Enter)" @click="saveComment">Post comment</Button></div></template></FileUploader>
          </div>
          <div v-if="hiddenReplyDraft" class="mb-4 text-xs text-gray-600">A reply draft is in a hidden thread. Select its category or All to continue.</div>
          <div v-if="!filteredThreads.length" class="py-4 text-sm text-gray-600">{{timelineSelection.size ? 'No entries match the selected filters.' : 'Select a category to see timeline entries.'}} <Button size="sm" variant="ghost" :disabled="hasPendingImages" @click="selectAllTimeline">Show all</Button></div>
          <div class="space-y-5">
            <div v-for="thread in filteredThreads" :key="thread.event.name">
              <article v-if="['Comment','Communication'].includes(thread.event.kind)" class="overflow-hidden rounded border border-gray-200 bg-white">
                <div class="flex gap-3 p-4"><Avatar :key="thread.event.actor+userImage(thread.event.actor)" size="xl" :label="authorName(thread.event.actor)" :image="userImage(thread.event.actor)"/>
                <div class="min-w-0 flex-1">
                  <div class="flex flex-wrap items-center gap-x-2 gap-y-1"><span class="text-sm font-semibold">{{authorName(thread.event.actor)}}</span><Badge theme="gray">{{thread.event.channel || thread.event.kind}}</Badge><span class="text-xs text-gray-500" :title="'Recorded: '+thread.event.recorded_at">{{formatSiteTime(thread.event.recorded_at)}}</span></div>
                  <div v-if="thread.event.happened_at" class="mt-1 text-xs text-gray-500" :title="'Happened: '+thread.event.happened_at">Happened {{formatSiteTime(thread.event.happened_at)}}</div>
                  <p v-if="thread.event.contact" class="text-xs text-gray-500 mt-1">Contact: {{thread.event.contact}}</p>
                  <div v-if="thread.event.body" class="prose prose-sm max-w-none text-gray-800 mt-2" v-html="thread.event.body"></div>
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
                    <div v-for="reply in visibleReplies(thread)" :key="reply.name" class="flex gap-2"><Avatar :key="reply.actor+userImage(reply.actor)" size="md" :label="authorName(reply.actor)" :image="userImage(reply.actor)"/><div class="min-w-0 flex-1"><div class="flex flex-wrap items-center gap-x-2"><span class="text-sm font-medium">{{authorName(reply.actor)}}</span><span class="text-xs text-gray-500" :title="'Recorded: '+reply.recorded_at">{{formatSiteTime(reply.recorded_at)}}</span></div><div class="prose prose-sm max-w-none text-gray-800 mt-1" v-html="reply.body"></div><Button variant="ghost" size="sm" class="mt-1" :disabled="busy || hasPendingImages || (replyRoot && replyRoot!==thread.event.name)" :aria-label="'Reply to '+authorName(reply.actor)+' in this thread'" @click="startReply(thread.event.name)">Reply<span class="sr-only"> to {{authorName(reply.actor)}} in this thread</span></Button></div></div>
                    <div v-if="replyRoot===thread.event.name" class="space-y-2"><div :id="'reply-editor-label-'+thread.event.name" class="text-xs font-medium text-gray-600">Reply in thread</div><FileUploader v-for="uploadKey in [issue.name+':reply:'+replyRoot+':'+replyEditorKey]" :key="uploadKey" file-types="image/png,image/jpeg,image/gif,image/webp" :upload-args="{upload_endpoint:'/api/method/unicom.api.upload_image',docname:issue.name,private:true}" :validate-file="f=>validateImage(f,uploadKey)" @success="file=>insertImage(file,replyEditor,'reply',uploadKey)" @failure="delete pendingImages[uploadKey]"><template #default="{openFileSelector,uploading,error:uploadError}"><div @keydown="submitShortcut($event,thread.event.name)"><TextEditor :ref="component=>setReplyEditor(component,thread.event.name)" :key="replyEditorKey" class="timeline-editor rich-editor" :content="replyBody" :fixed-menu="richMenu" :mentions="mentionOptions" placeholder="Write a reply; type @ to mention someone" @change="value=>replyBody=value"><template #bottom><div class="editor-image-action"><Button size="sm" variant="ghost" icon="image" label="Attach image" title="Attach image" :loading="uploading" :disabled="busy || uploading || pendingImages[uploadKey]" @click="beginImageUpload(openFileSelector,replyEditor,'reply',uploadKey)"/></div></template></TextEditor></div><ErrorMessage :message="uploadError"/><ErrorMessage :message="safeReplyError"/><div class="flex justify-end gap-2"><Button :disabled="busy || uploading || pendingImages[uploadKey]" @click="cancelReply">Cancel</Button><Button variant="solid" :loading="busy" :disabled="busy || uploading || pendingImages[uploadKey]" title="Post reply (Ctrl+Enter or Cmd+Enter)" @click="saveReply(thread.event.name)">Post reply</Button></div></template></FileUploader></div>
                  </div>
              </article>
              <div v-else class="flex gap-3 rounded-md bg-gray-50 px-3 py-2 text-xs text-gray-600">
                <FeatherIcon name="activity" class="h-4 w-4 mt-0.5"/><div class="min-w-0"><div><span class="font-medium text-gray-700">{{authorName(thread.event.actor)}}</span> · {{thread.event.kind}} · <span :title="'Recorded: '+thread.event.recorded_at">{{formatSiteTime(thread.event.recorded_at)}}</span></div><div v-if="thread.event.happened_at" :title="'Happened: '+thread.event.happened_at">Happened {{formatSiteTime(thread.event.happened_at)}}</div><div v-if="thread.event.channel">{{thread.event.channel}}</div><div v-if="thread.event.contact">Contact: {{thread.event.contact}}</div><div v-if="thread.event.body" v-html="thread.event.body"></div><p v-for="change in changes(thread.event)" :key="change.label" class="mt-1" :title="change.raw">{{change.label}}: {{change.text}}</p></div>
              </div>
            </div>
          </div>
        </div></section>
        <aside class="order-2 lg:order-3 min-w-0 border-t lg:border-t-0 lg:border-l text-base break-words lg:col-start-2 lg:row-start-1 lg:row-span-2 lg:sticky lg:top-0 lg:self-start lg:min-h-[calc(100vh-3rem)] lg:max-h-[calc(100vh-3rem)] lg:overflow-y-auto">
          <div class="border-b border-gray-200 px-5 py-4 text-lg font-medium">{{issue.issue_id || issue.name}}</div>
          <div class="flex gap-3 px-5 py-5 border-b border-gray-200"><Avatar size="3xl" :label="issue.issue_id || 'Issue'"/><div class="min-w-0"><div class="text-2xl font-medium break-words">{{issue.title}}</div><div class="flex gap-2 mt-3"><Button icon="edit-2" label="Edit issue" title="Edit issue" @click="editIssue"/><Button icon="message-square" label="Log communication" title="Log communication" :disabled="issue.status==='Resolved'" @click="logIssue"/></div></div></div>
          <div class="border-b border-gray-200 px-5 py-4"><div class="flex items-center justify-between"><Button variant="ghost" :icon-left="detailsOpen?'chevron-down':'chevron-right'" :aria-expanded="detailsOpen" aria-controls="issue-details" class="!px-0 font-semibold" @click="detailsOpen=!detailsOpen">Details</Button><Button variant="ghost" icon="edit-2" label="Edit issue details" title="Edit issue details" @click="editIssue"/></div>
            <dl v-if="detailsOpen" id="issue-details" class="mt-4 grid grid-cols-[110px_minmax(0,1fr)] gap-x-3 gap-y-4 text-base"><dt class="min-w-0 truncate text-gray-600" title="Issue Owner">Issue Owner</dt><dd><div v-if="inlineField==='accountable_owner'" ref="inlineRegion" class="space-y-2"><FormControl v-model="inlineValue" type="select" aria-label="Issue Owner" :options="userOptions" @change="saveInline"/><ErrorMessage :message="safeInlineError"/><Button v-if="inlineError" size="sm" @click="saveInline">Retry</Button></div><Button v-else variant="ghost" class="!h-auto !p-0" aria-label="Edit Issue Owner" @click="startInline('accountable_owner')"><template #prefix><Avatar size="sm" :label="authorName(issue.accountable_owner)" :image="userImage(issue.accountable_owner)"/></template>{{authorName(issue.accountable_owner)}}</Button></dd><dt class="min-w-0 truncate text-gray-600" title="Coordinating with">Coordinating with</dt><dd><div v-if="inlineField==='coordination_user'" ref="inlineRegion" class="space-y-2"><FormControl v-model="inlineValue" type="select" aria-label="Coordinating with" :options="inlineCoordinationOptions" @change="saveInline"/><ErrorMessage :message="safeInlineError"/><Button v-if="inlineError" size="sm" @click="saveInline">Retry</Button></div><Button v-else variant="ghost" class="!h-auto !p-0" aria-label="Edit Coordinating with" @click="startInline('coordination_user')"><template v-if="issue.coordination_user" #prefix><Avatar size="sm" :label="authorName(issue.coordination_user)" :image="userImage(issue.coordination_user)"/></template>{{issue.coordination_user ? authorName(issue.coordination_user) : '—'}}</Button></dd><dt class="min-w-0 truncate text-gray-600" title="Next action date">Next action date</dt><dd>{{issue.next_action_date||'—'}}</dd><template v-if="issue.resolution_note"><dt class="min-w-0 truncate text-gray-600" title="Resolution">Resolution</dt><dd>{{issue.resolution_note}}</dd></template><dt class="min-w-0 truncate text-gray-600" title="Participants">Participants</dt><dd :title="issue.access.filter(x=>x.reason==='Participant').map(x=>authorName(x.user)).join(', ')">{{new Set(issue.access.filter(x=>x.reason==='Participant' && x.user).map(x=>x.user)).size}}</dd><dt class="min-w-0 truncate text-gray-600" title="Follow-up assignees">Follow-up assignees</dt><dd>{{issue.access.filter(x=>x.reason==='Follow-up').map(x=>authorName(x.user)).join(', ')||'—'}}</dd></dl>
          </div>
          <div class="px-5 py-4"><Button variant="ghost" :icon-left="attachmentsOpen?'chevron-down':'chevron-right'" :aria-expanded="attachmentsOpen" aria-controls="issue-attachments" class="!px-0 font-semibold" @click="attachmentsOpen=!attachmentsOpen">Attachments</Button><div v-if="attachmentsOpen" id="issue-attachments" class="mt-3"><a v-for="f in issue.attachments" :key="f.name" :href="f.file_url" target="_blank" class="block text-blue-600 underline">{{f.file_name}}</a><FileUploader :upload-args="{upload_endpoint:'/api/method/unicom.api.upload_attachment',docname:issue.name,private:true}" :validate-file="f=>f.size>10*1024*1024?'Maximum attachment size is 10 MB':null" @success="uploadDone"><template #default="{openFileSelector,uploading,error:uploadError}"><Button class="mt-2" :loading="uploading" @click="openFileSelector">Add private file</Button><ErrorMessage :message="uploadError"/></template></FileUploader></div></div>
        </aside>
      </div>
    </div>
  </main>
</div>
<Dialog v-model="showNew" :options="{title:'New issue',size:'2xl'}"><template #body-content><ErrorMessage v-if="error" class="mb-3" :message="safeError"/><div class="space-y-3"><FormControl v-model="form.title" label="Title"/><FormControl v-model="form.description" type="textarea" label="Description"/><p class="text-xs text-gray-500">After creating the issue, edit its description to add formatting or images.</p><FormControl v-model="form.accountable_owner" type="select" label="Issue Owner" :options="userOptions"/><FormControl v-model="form.coordination_user" type="select" label="Coordinating with" :options="coordinationOptions"/><FormControl v-model="form.next_action" label="Next action"/><FormControl v-model="form.next_action_date" type="date" label="Next action date"/><div><label class="text-sm">Participants</label><div class="flex gap-2"><FormControl v-model="participants" type="select" :options="userOptions"/><Button @click="add(form.participants,participants);participants=''">Add</Button></div><div v-for="u in form.participants" :key="u" class="text-sm">{{u}} <Button variant="ghost" @click="form.participants=form.participants.filter(x=>x!==u)">Remove</Button></div></div><div><label class="text-sm">Follow-up assignees</label><div class="flex gap-2"><FormControl v-model="followup" type="select" :options="userOptions"/><Button @click="add(form.follow_up_assignees,followup);followup=''">Add</Button></div><div v-for="u in form.follow_up_assignees" :key="u" class="text-sm">{{u}} <Button variant="ghost" @click="form.follow_up_assignees=form.follow_up_assignees.filter(x=>x!==u)">Remove</Button></div></div></div></template><template #actions><Button variant="solid" :loading="busy" @click="create">Create issue</Button></template></Dialog>
<Dialog v-model="showEdit" :options="{title:'Edit issue',size:'2xl'}"><template #body-content><ErrorMessage v-if="error" class="mb-3" :message="safeError"/><div class="space-y-3"><FormControl v-model="edit.title" label="Title"/><FormControl v-model="edit.description" type="textarea" label="Description"/><FormControl v-model="edit.accountable_owner" type="select" label="Issue Owner" :options="userOptions"/><FormControl v-model="edit.coordination_user" type="select" label="Coordinating with" :options="editCoordinationOptions"/><FormControl v-model="edit.status" type="select" label="Status" :options="statuses"/><FormControl v-model="edit.next_action" label="Next action"/><FormControl v-model="edit.next_action_date" type="date" label="Next action date"/><FormControl v-model="edit.resolution_note" type="textarea" label="Resolution note (required to resolve)"/><div><div class="text-sm">Participants</div><FormControl v-model="editParticipant" type="select" :options="userOptions"/><Button @click="add(edit.participants,editParticipant);editParticipant=''">Add</Button><div v-for="u in edit.participants" :key="u" class="text-sm">{{u}} <Button variant="ghost" @click="edit.participants=edit.participants.filter(x=>x!==u)">Remove</Button></div></div><div><div class="text-sm">Follow-up assignees</div><FormControl v-model="editFollowup" type="select" :options="userOptions"/><Button @click="add(edit.follow_up_assignees,editFollowup);editFollowup=''">Add</Button><div v-for="u in edit.follow_up_assignees" :key="u" class="text-sm">{{u}} <Button variant="ghost" @click="edit.follow_up_assignees=edit.follow_up_assignees.filter(x=>x!==u)">Remove</Button></div></div></div></template><template #actions><Button variant="solid" :loading="busy" @click="saveEdit">Save</Button></template></Dialog>
<Dialog v-model="showResolve" :disable-outside-click-to-close="busy" :options="{title:'Resolve issue',size:'lg'}"><template #body-content><FormControl v-model="resolutionNote" type="textarea" label="Resolution note" required/><ErrorMessage :message="safeResolveError"/></template><template #actions><Button :disabled="busy" @click="showResolve=false">Cancel</Button><Button variant="solid" :loading="busy" :disabled="busy" @click="resolveIssue">Resolve</Button></template></Dialog>
<Dialog v-model="showLog" :options="{title:'Log communication',size:'2xl'}"><template #body-content><ErrorMessage v-if="error" class="mb-3" :message="safeError"/><div class="space-y-3"><FormControl v-model="log.channel" type="select" label="Channel" :options="channels"/><FormControl v-model="log.happened_at" type="datetime-local" label="Happened at"/><FormControl v-model="log.contact" label="Contact / person"/><div><label class="text-sm">Outcome / body (type @ to mention a user)</label><TextEditor :content="log.body" :mentions="mentionOptions" @change="value=>log.body=value"/></div><FormControl v-model="log.next_action" label="Next action"/><FormControl v-model="log.next_action_date" type="date" label="Next action date"/><FormControl v-model="log.resolution_note" type="textarea" label="Resolution note (optional; resolves issue)"/></div></template><template #actions><Button variant="solid" :loading="busy" @click="saveLog">Save communication</Button></template></Dialog>
</template>
