<script setup>
import { ref, reactive, computed, onMounted, watch, nextTick } from 'vue'
import { Button, FormControl, Dialog, TextEditor, Badge, Avatar, FeatherIcon, ListView, ListFooter, FileUploader, ErrorMessage, Breadcrumbs, Dropdown } from 'frappe-ui'

const view=ref('mine'), rows=ref([]), issue=ref(null), people=ref([]), error=ref(''), busy=ref(false), page=ref(0), search=ref(''), filter=ref(''), showNew=ref(false), showLog=ref(false), showEdit=ref(false)
const currentUser=ref(''), sidebarCollapsed=ref(false)
const commentBody=ref(''), commentError=ref(''), commentEditorKey=ref(0)
const commentEditor=ref(null), replyEditor=ref(null)
const replyRoot=ref(null), replyBody=ref(''), replyError=ref(''), replyEditorKey=ref(0), expandedThreads=ref(new Set())
watch(() => issue.value?.name, () => { commentBody.value=''; commentError.value=''; commentEditorKey.value++; replyRoot.value=null; replyBody.value=''; replyError.value=''; replyEditorKey.value++; expandedThreads.value=new Set() }, {flush:'sync'})
const blank=()=>({title:'',description:'',accountable_owner:'',next_action:'',next_action_date:'',participants:[],follow_up_assignees:[]})
const form=reactive(blank()), edit=reactive({}), log=reactive({channel:'Internal Note',happened_at:'',contact:'',body:'',next_action:'',next_action_date:'',resolution_note:''})
const columns = [{label:'Issue',key:'title',width:'3fr'},{label:'Status',key:'status',width:'1.5fr'},{label:'Owner',key:'accountable_owner',width:'2fr'},{label:'Next action date',key:'next_action_date',width:'1.5fr'}]
const safeError = computed(() => { const el=document.createElement('div'); el.textContent=error.value; return el.innerHTML })
const safeCommentError = computed(() => { const el=document.createElement('div'); el.textContent=commentError.value; return el.innerHTML })
const safeReplyError = computed(() => { const el=document.createElement('div'); el.textContent=replyError.value; return el.innerHTML })
const timelineThreads = computed(() => { const events=issue.value?.timeline || []; const replies=new Map(); for(const event of events) if(event.reply_to){if(!replies.has(event.reply_to)) replies.set(event.reply_to,[]); replies.get(event.reply_to).push(event)} return events.filter(event=>!event.reply_to).reverse().map(event=>({event,replies:replies.get(event.name)||[]})) })
const statuses=['Open','In Progress','Waiting','Resolved'], channels=['Internal Note','Call','Meeting','Email','WhatsApp']
const userOptions=computed(()=>[{label:'Select user',value:''},...people.value.map(p=>({label:p.full_name+' ('+p.name+')',value:p.name}))])
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
async function load(){await run(async()=>{rows.value=await api('list_issues',{view:view.value,status:filter.value,search:search.value,start:page.value*20,page_length:20})})}
async function open(name,push=true){await run(async()=>{issue.value=await api('get_issue',{name}); if(push) history.pushState({},'', '/unicom/'+encodeURIComponent(name))})}
function goList(v){view.value=v;issue.value=null;page.value=0;history.pushState({},'','/unicom');load()}
function resetForm(){Object.assign(form,blank())}
async function create(){await run(async()=>{const doc=await api('create_issue',form,true);showNew.value=false;resetForm();issue.value=doc;history.pushState({},'','/unicom/'+encodeURIComponent(doc.name))})}
function editIssue(){Object.assign(edit,{title:issue.value.title,description:issue.value.description||'',accountable_owner:issue.value.accountable_owner,status:issue.value.status,next_action:issue.value.next_action||'',next_action_date:issue.value.next_action_date||'',resolution_note:issue.value.resolution_note||'',participants:issue.value.access.filter(x=>x.reason==='Participant').map(x=>x.user),follow_up_assignees:issue.value.access.filter(x=>x.reason==='Follow-up').map(x=>x.user)});showEdit.value=true}
async function saveEdit(){await run(async()=>{issue.value=await api('update_issue',{name:issue.value.name,values:edit},true);showEdit.value=false})}
function logIssue(){Object.assign(log,{channel:'Internal Note',happened_at:new Date(Date.now()-new Date().getTimezoneOffset()*60000).toISOString().slice(0,16),contact:'',body:'',next_action:issue.value.next_action||'',next_action_date:issue.value.next_action_date||'',resolution_note:''});showLog.value=true}
async function saveLog(){await run(async()=>{const dom=new DOMParser().parseFromString(log.body,'text/html'); const mentions=[...dom.querySelectorAll('[data-type="mention"][data-id]')].map(x=>x.getAttribute('data-id'));issue.value=await api('log_communication',{name:issue.value.name,...log,mentions},true);showLog.value=false})}
async function saveComment(){
  if(busy.value) return
  busy.value=true; commentError.value=''
  const name=issue.value.name
  try { const updated=await api('add_comment',{name,body:commentBody.value},true); if(issue.value?.name===name){issue.value=updated;commentBody.value='';commentEditorKey.value++} }
  catch(e){if(issue.value?.name===name) commentError.value=e.message}
  finally{busy.value=false}
}
function toggleThread(root){const next=new Set(expandedThreads.value); if(next.has(root)) next.delete(root); else next.add(root); expandedThreads.value=next}
function labelEditor(component, current, labelId){
  if(!component) return
  nextTick(()=>{
    if(current.value!==component) return
    const editor=component.editor
    if(!editor || editor.isDestroyed) return
    const props=editor.options.editorProps || {}
    editor.setOptions({editorProps:{...props,attributes:{...props.attributes,role:'textbox','aria-multiline':'true','aria-labelledby':labelId}}})
  })
}
function setCommentEditor(component){commentEditor.value=component;labelEditor(component,commentEditor,'comment-editor-label')}
function setReplyEditor(component,root){replyEditor.value=component;labelEditor(component,replyEditor,'reply-editor-label-'+root)}
function startReply(root){if(replyRoot.value!==root){replyRoot.value=root;replyBody.value='';replyError.value='';replyEditorKey.value++} const next=new Set(expandedThreads.value);next.add(root);expandedThreads.value=next;nextTick(()=>replyEditor.value?.editor?.commands.focus())}
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
function authorName(user){return people.value.find(person=>person.name===user)?.full_name || user || 'Unknown user'}
// Frappe timestamps are site-local wall times; format the components without converting zones.
function formatSiteTime(value){
  if(!value) return '—'
  const match=String(value).match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?/)
  if(!match) return String(value)
  const date=new Date(Date.UTC(+match[1],+match[2]-1,+match[3],+(match[4]||0),+(match[5]||0),+(match[6]||0)))
  if(Number.isNaN(date.getTime())) return String(value)
  return new Intl.DateTimeFormat(undefined,{timeZone:'UTC',year:'numeric',month:'short',day:'numeric',...(match[4] ? {hour:'numeric',minute:'2-digit'} : {})}).format(date)
}
function fieldLabel(key){return ({accountable_owner:'Accountable owner',next_action:'Next action',next_action_date:'Next action date',resolution_note:'Resolution note',follow_up_assignees:'Follow-up assignees'})[key] || key.replaceAll('_',' ').replace(/^./,c=>c.toUpperCase())}
function changeValue(value,key){if(value===null || value===undefined || value==='') return '—'; if(Array.isArray(value)) return value.length ? value.join(', ') : '—'; if(typeof value==='object') return JSON.stringify(value); if(key==='next_action_date') return formatSiteTime(value); return String(value)}
function changes(event){try{const data=JSON.parse(event.changes||'{}');return Object.entries(data).map(([key,value])=>({label:fieldLabel(key),text:`${changeValue(value?.from,key)} → ${changeValue(value?.to,key)}`,raw:JSON.stringify(value)}))}catch{return event.changes ? [{label:'Changes',text:event.changes,raw:event.changes}] : []}}

onMounted(async()=>{fetch('/api/method/frappe.auth.get_logged_user',{credentials:'same-origin'}).then(r=>r.ok?r.json():null).then(r=>{currentUser.value=r?.message||''}).catch(()=>{});await run(async()=>{people.value=await api('users'); const name=decodeURIComponent(location.pathname.replace(/^\/unicom\/?/,'')); if(name) await open(name,false); else await load()});window.onpopstate=()=>{const name=decodeURIComponent(location.pathname.replace(/^\/unicom\/?/,''));if(name)open(name,false);else{issue.value=null;load()}}})
</script>
<template>
<div class="h-screen overflow-hidden flex flex-col md:flex-row">
  <aside class="bg-gray-50 border-b md:border-b-0 md:border-r border-gray-200 shrink-0 flex flex-col min-w-0" :class="sidebarCollapsed?'md:w-16':'md:w-[248px]'">
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
      <Button v-for="item in [{view:'mine',label:'My Issues',icon:'user'},{view:'overdue',label:'Overdue',icon:'clock'},{view:'all',label:'All Accessible Issues',icon:'list'}]" :key="item.view" :variant="view===item.view?'outline':'ghost'" :icon-left="item.icon" class="!justify-start shrink-0 md:w-full" :class="sidebarCollapsed?'md:!justify-center':''" :aria-label="item.label" :aria-current="view===item.view?'page':undefined" :title="item.label" @click="goList(item.view)"><span :class="sidebarCollapsed?'md:sr-only':''">{{item.label}}</span></Button>
    </nav>
    <div class="hidden md:flex mt-auto p-2 flex-col gap-1">
      <Button variant="ghost" icon-left="help-circle" class="w-full !justify-start" :class="sidebarCollapsed?'!justify-center':''" aria-label="Frappe help" title="Frappe help" @click="openHelp"><span :class="sidebarCollapsed?'sr-only':''">Help</span></Button>
      <Button variant="ghost" :icon-left="sidebarCollapsed?'chevrons-right':'chevrons-left'" class="w-full !justify-start" :class="sidebarCollapsed?'!justify-center':''" :aria-label="sidebarCollapsed?'Expand sidebar':'Collapse sidebar'" :title="sidebarCollapsed?'Expand sidebar':'Collapse sidebar'" @click="sidebarCollapsed=!sidebarCollapsed"><span :class="sidebarCollapsed?'sr-only':''">{{sidebarCollapsed?'Expand sidebar':'Collapse sidebar'}}</span></Button>
    </div>
  </aside>
  <main class="min-w-0 min-h-0 flex-1 flex flex-col">
    <header class="border-b border-gray-200 h-12 shrink-0 px-4 sm:px-6 flex items-center justify-between gap-2"><div class="min-w-0 flex-1 overflow-hidden"><Breadcrumbs :items="issue ? [{label:'Issues',onClick:()=>goList(view)},{label:issue.title}] : [{label:'Issues'},{label:'List'}]"/></div><Button variant="solid" icon-left="plus" class="shrink-0 whitespace-nowrap" @click="showNew=true">Create</Button></header>
    <ErrorMessage v-if="error" class="mx-6 mt-4" :message="safeError"/>
    <template v-if="!issue">
      <div class="min-h-0 flex-1 flex flex-col">
        <div class="flex gap-2 px-4 sm:px-6 py-4 flex-wrap shrink-0"><FormControl v-model="search" placeholder="Search title" aria-label="Search title" @keydown.enter="page=0;load()"/><FormControl type="select" v-model="filter" aria-label="Filter by status" :options="[{label:'All statuses',value:''},...statuses.map(x=>({label:x,value:x}))]" @change="page=0;load()"/><Button @click="page=0;load()">Search</Button></div>
        <div class="min-h-0 flex-1 overflow-auto px-4 sm:px-6"><ListView :columns="columns" :rows="rows" row-key="name" :options="{selectable:false,onRowClick:row=>open(row.name),emptyState:{title:'No issues found'}}"><template #cell="{column,row,item}"><Badge v-if="column.key==='status'" :theme="row.overdue?'red':'gray'">{{row.overdue?'Overdue · ':''}}{{item}}</Badge><span v-else-if="column.key==='accountable_owner'" class="flex items-center gap-2 min-w-0"><Avatar size="sm" :label="authorName(item)"/><span class="text-sm truncate">{{authorName(item)}}</span></span><span v-else class="text-sm truncate">{{item||'—'}}</span></template></ListView></div>
        <ListFooter class="px-4 sm:px-6 py-3 border-t border-gray-200 shrink-0"><template #left><span class="text-sm text-gray-500">Page {{page+1}} · {{rows.length}} {{rows.length===1?'issue':'issues'}} shown</span></template><template #right><div class="flex gap-2"><Button :disabled="page===0" @click="page--;load()">Previous</Button><Button :disabled="rows.length<20" @click="page++;load()">Next</Button></div></template></ListFooter>
      </div>
    </template>
    <div v-else class="min-h-0 flex-1 overflow-y-auto">
      <div class="grid min-w-0 lg:grid-cols-[minmax(0,1fr)_320px] lg:grid-rows-[auto_1fr]">
        <div class="order-1 w-full min-w-0 max-w-4xl mx-auto p-6 flex flex-wrap justify-between gap-4 items-start"><div class="min-w-0 flex-1 basis-64"><Button variant="ghost" @click="goList(view)">← Back to issues</Button><h1 class="text-2xl font-semibold mt-3 break-words">{{issue.title}}</h1><p class="text-sm text-gray-500 mt-2">{{issue.name}} · Created by {{issue.owner}}</p></div><div class="flex flex-wrap shrink-0 gap-2 whitespace-nowrap"><Button @click="editIssue">Edit / resolve</Button><Button variant="solid" :disabled="issue.status==='Resolved'" @click="logIssue">Log communication</Button></div></div>
        <section class="order-3 lg:order-2 w-full min-w-0 max-w-4xl mx-auto px-6 pb-6 space-y-6 break-words"><div><h2 class="font-semibold mb-2">Description</h2><div class="text-sm text-gray-700" v-html="issue.description || '—'"></div></div><div>
          <h2 class="font-semibold mb-4">Timeline</h2>
          <div class="mb-8 rounded-lg border border-gray-200 p-3 space-y-2">
            <div id="comment-editor-label" class="text-xs font-medium text-gray-600">Add a comment</div><TextEditor :ref="setCommentEditor" :key="commentEditorKey" class="timeline-editor" :content="commentBody" :mentions="mentionOptions" placeholder="Write a comment; type @ to mention someone" @change="value=>commentBody=value"/>
            <ErrorMessage :message="safeCommentError"/><div class="flex justify-end"><Button variant="solid" :loading="busy" :disabled="busy" @click="saveComment">Post comment</Button></div>
          </div>
          <div class="space-y-5">
            <div v-for="thread in timelineThreads" :key="thread.event.name">
              <article v-if="['Comment','Communication'].includes(thread.event.kind)" class="flex gap-3">
                <Avatar size="xl" :label="authorName(thread.event.actor)"/>
                <div class="min-w-0 flex-1">
                  <div class="flex flex-wrap items-center gap-x-2 gap-y-1"><span class="text-sm font-semibold">{{authorName(thread.event.actor)}}</span><Badge theme="gray">{{thread.event.channel || thread.event.kind}}</Badge><span class="text-xs text-gray-500" :title="'Recorded: '+thread.event.recorded_at">{{formatSiteTime(thread.event.recorded_at)}}</span></div>
                  <div v-if="thread.event.happened_at" class="mt-1 text-xs text-gray-500" :title="'Happened: '+thread.event.happened_at">Happened {{formatSiteTime(thread.event.happened_at)}}</div>
                  <p v-if="thread.event.contact" class="text-xs text-gray-500 mt-1">Contact: {{thread.event.contact}}</p>
                  <div v-if="thread.event.body" class="text-sm text-gray-800 mt-2" v-html="thread.event.body"></div>
                  <p v-for="change in changes(thread.event)" :key="change.label" class="text-xs text-gray-600 mt-1" :title="change.raw">{{change.label}}: {{change.text}}</p>
                  <div class="flex items-center gap-2 mt-2">
                    <Button variant="ghost" size="sm" :disabled="busy || (replyRoot && replyRoot!==thread.event.name)" :aria-label="'Reply to '+authorName(thread.event.actor)" @click="startReply(thread.event.name)">Reply</Button>
                    <Button v-if="thread.replies.length" variant="ghost" size="sm" :disabled="replyRoot===thread.event.name" :aria-expanded="expandedThreads.has(thread.event.name)" :aria-controls="'thread-'+thread.event.name" :aria-label="(expandedThreads.has(thread.event.name)?'Hide ':'Show ')+thread.replies.length+' replies to '+authorName(thread.event.actor)" @click="toggleThread(thread.event.name)">{{expandedThreads.has(thread.event.name)?'Hide':'Show'}} {{thread.replies.length}} {{thread.replies.length===1?'reply':'replies'}}</Button>
                  </div>
                  <div v-if="expandedThreads.has(thread.event.name)" :id="'thread-'+thread.event.name" class="mt-3 border-l-2 border-gray-200 bg-gray-50 rounded-r-lg px-4 py-3 space-y-4">
                    <div v-for="reply in thread.replies" :key="reply.name" class="flex gap-2"><Avatar size="md" :label="authorName(reply.actor)"/><div class="min-w-0 flex-1"><div class="flex flex-wrap items-center gap-x-2"><span class="text-sm font-medium">{{authorName(reply.actor)}}</span><span class="text-xs text-gray-500" :title="'Recorded: '+reply.recorded_at">{{formatSiteTime(reply.recorded_at)}}</span></div><div class="text-sm text-gray-800 mt-1" v-html="reply.body"></div></div></div>
                    <div v-if="replyRoot===thread.event.name" class="space-y-2"><div :id="'reply-editor-label-'+thread.event.name" class="text-xs font-medium text-gray-600">Reply to {{authorName(thread.event.actor)}}</div><TextEditor :ref="component=>setReplyEditor(component,thread.event.name)" :key="replyEditorKey" class="timeline-editor" :content="replyBody" :mentions="mentionOptions" placeholder="Write a reply; type @ to mention someone" @change="value=>replyBody=value"/><ErrorMessage :message="safeReplyError"/><div class="flex justify-end gap-2"><Button :disabled="busy" @click="cancelReply">Cancel</Button><Button variant="solid" :loading="busy" :disabled="busy" @click="saveReply(thread.event.name)">Post reply</Button></div></div>
                  </div>
                </div>
              </article>
              <div v-else class="flex gap-3 rounded-md bg-gray-50 px-3 py-2 text-xs text-gray-600">
                <FeatherIcon name="activity" class="h-4 w-4 mt-0.5"/><div class="min-w-0"><div><span class="font-medium text-gray-700">{{authorName(thread.event.actor)}}</span> · {{thread.event.kind}} · <span :title="'Recorded: '+thread.event.recorded_at">{{formatSiteTime(thread.event.recorded_at)}}</span></div><div v-if="thread.event.happened_at" :title="'Happened: '+thread.event.happened_at">Happened {{formatSiteTime(thread.event.happened_at)}}</div><div v-if="thread.event.channel">{{thread.event.channel}}</div><div v-if="thread.event.contact">Contact: {{thread.event.contact}}</div><div v-if="thread.event.body" v-html="thread.event.body"></div><p v-for="change in changes(thread.event)" :key="change.label" class="mt-1" :title="change.raw">{{change.label}}: {{change.text}}</p></div>
              </div>
            </div>
          </div>
        </div></section>
        <aside class="order-2 lg:order-3 min-w-0 space-y-4 border-t lg:border-t-0 lg:border-l p-6 text-sm break-words lg:col-start-2 lg:row-start-1 lg:row-span-2 lg:sticky lg:top-0 lg:self-start lg:min-h-[calc(100vh-4rem)] lg:max-h-screen lg:overflow-y-auto"><div><div class="text-gray-500">Status</div><div>{{issue.status}} <Badge v-if="issue.overdue" theme="red">Overdue</Badge></div></div><div><div class="text-gray-500">Accountable owner</div>{{issue.accountable_owner}}</div><div><div class="text-gray-500">Next action</div>{{issue.next_action||'—'}} · {{issue.next_action_date||'—'}}</div><div v-if="issue.resolution_note"><div class="text-gray-500">Resolution</div>{{issue.resolution_note}}</div><div><div class="text-gray-500">Participants</div>{{issue.access.filter(x=>x.reason==='Participant').map(x=>x.user).join(', ')||'—'}}</div><div><div class="text-gray-500">Follow-up assignees</div>{{issue.access.filter(x=>x.reason==='Follow-up').map(x=>x.user).join(', ')||'—'}}</div><div><div class="text-gray-500 mb-2">Attachments</div><a v-for="f in issue.attachments" :key="f.name" :href="f.file_url" target="_blank" class="block text-blue-600 underline">{{f.file_name}}</a><FileUploader :upload-args="{upload_endpoint:'/api/method/unicom.api.upload_attachment',docname:issue.name,private:true}" :validate-file="f=>f.size>10*1024*1024?'Maximum attachment size is 10 MB':null" @success="uploadDone"><template #default="{openFileSelector,uploading,error:uploadError}"><Button class="mt-2" :loading="uploading" @click="openFileSelector">Add private file</Button><ErrorMessage :message="uploadError"/></template></FileUploader></div></aside>
      </div>
    </div>
  </main>
</div>
<Dialog v-model="showNew" :options="{title:'New issue',size:'2xl'}"><template #body-content><ErrorMessage v-if="error" class="mb-3" :message="safeError"/><div class="space-y-3"><FormControl v-model="form.title" label="Title"/><FormControl v-model="form.description" type="textarea" label="Description"/><FormControl v-model="form.accountable_owner" type="select" label="Accountable owner" :options="userOptions"/><FormControl v-model="form.next_action" label="Next action"/><FormControl v-model="form.next_action_date" type="date" label="Next action date"/><div><label class="text-sm">Participants</label><div class="flex gap-2"><FormControl v-model="participants" type="select" :options="userOptions"/><Button @click="add(form.participants,participants);participants=''">Add</Button></div><div v-for="u in form.participants" :key="u" class="text-sm">{{u}} <Button variant="ghost" @click="form.participants=form.participants.filter(x=>x!==u)">Remove</Button></div></div><div><label class="text-sm">Follow-up assignees</label><div class="flex gap-2"><FormControl v-model="followup" type="select" :options="userOptions"/><Button @click="add(form.follow_up_assignees,followup);followup=''">Add</Button></div><div v-for="u in form.follow_up_assignees" :key="u" class="text-sm">{{u}} <Button variant="ghost" @click="form.follow_up_assignees=form.follow_up_assignees.filter(x=>x!==u)">Remove</Button></div></div></div></template><template #actions><Button variant="solid" :loading="busy" @click="create">Create issue</Button></template></Dialog>
<Dialog v-model="showEdit" :options="{title:'Edit issue',size:'2xl'}"><template #body-content><ErrorMessage v-if="error" class="mb-3" :message="safeError"/><div class="space-y-3"><FormControl v-model="edit.title" label="Title"/><FormControl v-model="edit.description" type="textarea" label="Description"/><FormControl v-model="edit.accountable_owner" type="select" label="Accountable owner" :options="userOptions"/><FormControl v-model="edit.status" type="select" label="Status" :options="statuses"/><FormControl v-model="edit.next_action" label="Next action"/><FormControl v-model="edit.next_action_date" type="date" label="Next action date"/><FormControl v-model="edit.resolution_note" type="textarea" label="Resolution note (required to resolve)"/><div><div class="text-sm">Participants</div><FormControl v-model="editParticipant" type="select" :options="userOptions"/><Button @click="add(edit.participants,editParticipant);editParticipant=''">Add</Button><div v-for="u in edit.participants" :key="u" class="text-sm">{{u}} <Button variant="ghost" @click="edit.participants=edit.participants.filter(x=>x!==u)">Remove</Button></div></div><div><div class="text-sm">Follow-up assignees</div><FormControl v-model="editFollowup" type="select" :options="userOptions"/><Button @click="add(edit.follow_up_assignees,editFollowup);editFollowup=''">Add</Button><div v-for="u in edit.follow_up_assignees" :key="u" class="text-sm">{{u}} <Button variant="ghost" @click="edit.follow_up_assignees=edit.follow_up_assignees.filter(x=>x!==u)">Remove</Button></div></div></div></template><template #actions><Button variant="solid" :loading="busy" @click="saveEdit">Save</Button></template></Dialog>
<Dialog v-model="showLog" :options="{title:'Log communication',size:'2xl'}"><template #body-content><ErrorMessage v-if="error" class="mb-3" :message="safeError"/><div class="space-y-3"><FormControl v-model="log.channel" type="select" label="Channel" :options="channels"/><FormControl v-model="log.happened_at" type="datetime-local" label="Happened at"/><FormControl v-model="log.contact" label="Contact / person"/><div><label class="text-sm">Outcome / body (type @ to mention a user)</label><TextEditor :content="log.body" :mentions="mentionOptions" @change="value=>log.body=value"/></div><FormControl v-model="log.next_action" label="Next action"/><FormControl v-model="log.next_action_date" type="date" label="Next action date"/><FormControl v-model="log.resolution_note" type="textarea" label="Resolution note (optional; resolves issue)"/></div></template><template #actions><Button variant="solid" :loading="busy" @click="saveLog">Save communication</Button></template></Dialog>
</template>
