const $ = (id) => document.getElementById(id);
const state = {
  theme: localStorage.getItem('kc-agency-theme') || 'light',
  autoCheck: localStorage.getItem('kc-agency-auto-check') !== '0',
  haptics: localStorage.getItem('kc-agency-haptics') !== '0',
  server: false,
  latency: null,
  pendingJob: null,
  currentChat: localStorage.getItem('kc-agency-chat') || null,
  selectedAgent: null,
  messages: [],
  agents: [
    {id:'chief',name:'Главный агент',role:'Стратегия и распределение',icon:'◆',status:'online'},
    {id:'dev',name:'Программист',role:'Код и интеграции',icon:'</>',status:'online'},
    {id:'critic',name:'Критик',role:'Анализ и проверка',icon:'◎',status:'online'},
    {id:'qa',name:'Тестировщик',role:'Тесты и качество',icon:'△',status:'online'}
  ]
};

function safe(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function tap(){ if(state.haptics && navigator.vibrate) navigator.vibrate(8); }
document.addEventListener('click',e=>{ if(e.target.closest('button')) tap(); });

function applyTheme(theme){
  state.theme=theme; localStorage.setItem('kc-agency-theme',theme);
  const resolved=theme==='system'?(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'):theme;
  document.documentElement.dataset.theme=resolved;
  document.querySelector('meta[name="theme-color"]').content=resolved==='dark'?'#0b1420':'#d7d8d8';
  document.querySelectorAll('[data-theme]').forEach(b=>b.classList.toggle('active',b.dataset.theme===theme));
}
$('themeButton').onclick=()=>applyTheme(document.documentElement.dataset.theme==='dark'?'light':'dark');

function greeting(){
  const h=new Date().getHours();
  if(h>=5&&h<12)return 'Доброе утро';
  if(h>=12&&h<17)return 'Добрый день';
  if(h>=17&&h<24)return 'Добрый вечер';
  return 'Доброй ночи';
}
function userName(){ return (localStorage.getItem('kc-agency-name')||'').trim(); }
function renderGreeting(){
  const h=document.querySelector('.hero-copy h1');
  if(h) h.textContent=`${greeting()}${userName()?', '+userName():''}.`;
}
setInterval(renderGreeting,60000);
window.addEventListener('pageshow',renderGreeting);
window.addEventListener('focus',renderGreeting);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)renderGreeting();});

function openSheet(title,html){
  $('sheetTitle').textContent=title; $('sheetBody').innerHTML=html;
  $('sheetBackdrop').hidden=false; $('sheet').hidden=false;
}
function closeSheet(){ $('sheetBackdrop').hidden=true; $('sheet').hidden=true; }
$('sheetClose').onclick=closeSheet; $('sheetBackdrop').onclick=closeSheet;

function requestProfile(force=false){
  if(userName()&&!force) return;
  openSheet('Профиль K&C',`<div class="profile-form"><p>Как к вам обращаться?</p><input id="profileNameInput" maxlength="40" placeholder="Имя" value="${safe(userName())}"><button class="primary3d" id="saveProfileName">Сохранить</button></div>`);
  $('saveProfileName').onclick=()=>{
    const name=$('profileNameInput').value.trim();
    if(!name){$('profileNameInput').focus();return;}
    localStorage.setItem('kc-agency-name',name); renderGreeting(); closeSheet();
  };
}
$('profileButton').onclick=()=>requestProfile(true);

function showPage(page){
  document.querySelectorAll('[data-page]').forEach(p=>p.classList.toggle('active',p.dataset.page===page));
  window.scrollTo({top:0,behavior:'smooth'});
  if(page==='memory') loadMemory();
}
document.querySelectorAll('[data-go]').forEach(b=>b.addEventListener('click',()=>showPage(b.dataset.go)));

function store(key,value){ localStorage.setItem(key,JSON.stringify(value)); }
function load(key,fallback){ try{return JSON.parse(localStorage.getItem(key))??fallback;}catch{return fallback;} }

function renderAgents(){
  const cards=state.agents.map(a=>`<button class="agent-card" data-agent="${a.id}"><b>${safe(a.icon)}</b><span><strong>${safe(a.name)}</strong><small><i class="led green"></i> Онлайн</small><em>${safe(a.role)}</em></span></button>`).join('');
  $('homeAgents').innerHTML=state.agents.slice(0,4).map(a=>`<button class="agent-card" data-agent="${a.id}"><b>${safe(a.icon)}</b><span><strong>${safe(a.name)}</strong><small><i class="led green"></i> Онлайн</small><em>${safe(a.role)}</em></span></button>`).join('');
  $('agentList').innerHTML=state.agents.map(a=>`<section class="glass agent-wide"><div class="agent-icon">${safe(a.icon)}</div><div><h3>${safe(a.name)}</h3><p>${safe(a.role)}</p><small><i class="led green"></i> Готов к работе</small></div><button class="mini3d" data-agent-open="${a.id}">›</button></section>`).join('');
  document.querySelectorAll('[data-agent],[data-agent-open]').forEach(b=>b.onclick=()=>openAgent(b.dataset.agent||b.dataset.agentOpen));
}
function openAgent(id){
  const a=state.agents.find(x=>x.id===id); if(!a)return;
  state.selectedAgent=id;
  openSheet(a.name,`<div class="sheet-card"><p>${safe(a.role)}</p><p>Статус: <b>готов к работе</b>.</p><button class="primary3d" id="agentToChat">Поставить задачу этому агенту</button></div>`);
  $('agentToChat').onclick=()=>{closeSheet();showPage('chat');$('statusBox').textContent=`Агент: ${a.name}`;$('ideaInput').focus();};
}
renderAgents();

async function loadAgents(){
  try{
    const d=await json('/api/agents');
    if(Array.isArray(d.items)&&d.items.length){
      state.agents=d.items.map(x=>({...x,status:'online'}));
      renderAgents();
      $('agentStatus').textContent=`${d.count||d.items.length} доступны`;
    }
  }catch(e){
    $('agentStatus').textContent='Каталог недоступен';
  }
}
loadAgents();

function renderTasks(){
  const tasks=load('kc-agency-tasks',[]);
  $('taskList').innerHTML=tasks.length?tasks.map((t,i)=>`<section class="glass list-item"><button class="check ${t.done?'done':''}" data-task-toggle="${i}">${t.done?'✓':''}</button><div><h3>${safe(t.text)}</h3><small>${safe(t.created)}</small></div><button class="mini3d" data-task-del="${i}">×</button></section>`).join(''):'<section class="glass empty">Задач пока нет.</section>';
  document.querySelectorAll('[data-task-toggle]').forEach(b=>b.onclick=()=>{const a=load('kc-agency-tasks',[]);a[+b.dataset.taskToggle].done=!a[+b.dataset.taskToggle].done;store('kc-agency-tasks',a);renderTasks();});
  document.querySelectorAll('[data-task-del]').forEach(b=>b.onclick=()=>{const a=load('kc-agency-tasks',[]);a.splice(+b.dataset.taskDel,1);store('kc-agency-tasks',a);renderTasks();});
  $('notifyBadge').textContent=tasks.filter(t=>!t.done).length;
}
$('saveTask').onclick=()=>{
  const v=$('taskInput').value.trim();if(!v)return;
  const a=load('kc-agency-tasks',[]);a.unshift({text:v,done:false,created:new Date().toLocaleString('ru-RU')});store('kc-agency-tasks',a);$('taskInput').value='';renderTasks();
};
$('addTaskButton').onclick=()=>$('taskInput').focus();
renderTasks();

function renderProjects(){
  const projects=load('kc-agency-projects',[]);
  $('projectList').innerHTML=projects.length?projects.map((p,i)=>`<section class="glass list-item"><div class="project-dot"></div><div><h3>${safe(p.name)}</h3><small>Создан: ${safe(p.created)}</small></div><button class="mini3d" data-project-del="${i}">×</button></section>`).join(''):'<section class="glass empty">Проектов пока нет.</section>';
  document.querySelectorAll('[data-project-del]').forEach(b=>b.onclick=()=>{const a=load('kc-agency-projects',[]);a.splice(+b.dataset.projectDel,1);store('kc-agency-projects',a);renderProjects();});
}
$('saveProject').onclick=()=>{
  const v=$('projectInput').value.trim();if(!v)return;
  const a=load('kc-agency-projects',[]);a.unshift({name:v,created:new Date().toLocaleDateString('ru-RU')});store('kc-agency-projects',a);$('projectInput').value='';renderProjects();
};
$('addProjectButton').onclick=()=>$('projectInput').focus();
renderProjects();

const quick=$('quickInput');
function updateQuick(){ $('quickCount').textContent=`${quick.value.length} / 2000`; }
quick.addEventListener('input',updateQuick); updateQuick();
$('clearQuickButton').onclick=()=>{quick.value='';updateQuick();quick.focus();};
$('templateButton').onclick=()=>{
  openSheet('Шаблоны задач',`<div class="template-list">
    <button data-template="Проанализируй проект, найди слабые места и предложи конкретный план улучшения.">Анализ проекта</button>
    <button data-template="Разработай технический план реализации функции, затем проверь риски и тесты.">Разработка</button>
    <button data-template="Собери факты по теме, структурируй выводы и подготовь краткий отчёт.">Исследование</button>
  </div>`);
  $('sheetBody').querySelectorAll('[data-template]').forEach(b=>b.onclick=()=>{quick.value=b.dataset.template;updateQuick();closeSheet();quick.focus();});
};
$('quickSend').onclick=()=>{
  const text=quick.value.trim(); if(!text){quick.focus();return;}
  showPage('chat'); $('ideaInput').value=text; quick.value=''; updateQuick(); sendChat();
};

function renderMessages(waiting=false,partial=''){
  const base=state.messages.length?state.messages:[{role:'assistant',content:'Здравствуйте! Я K&C. Поставьте задачу, и я помогу организовать работу.'}];
  $('discussionOutput').innerHTML=base.map(m=>`<div class="message ${m.role}"><div>${m.role==='assistant'?'<b>K&C</b>':''}<p>${safe(m.content)}</p></div></div>`).join('')+(waiting?`<div class="message assistant"><div><b>K&C</b><p>${safe(partial||'Думаю…')}</p></div></div>`:'');
  requestAnimationFrame(()=>$('discussionOutput').lastElementChild?.scrollIntoView({behavior:'smooth'}));
}
async function json(url,options={}){
  const c=new AbortController(); const timer=setTimeout(()=>c.abort(),30000);
  try{
    const r=await fetch(url,{...options,cache:'no-store',signal:c.signal});
    const t=await r.text(); let d={}; try{d=JSON.parse(t)}catch{}
    if(!r.ok) throw new Error(d.error||'Ошибка сервера');
    return d;
  }finally{clearTimeout(timer);}
}
async function sendChat(){
  if(state.pendingJob)return;
  const box=$('ideaInput'); const message=box.value.trim(); if(!message){box.focus();return;}
  state.messages.push({role:'user',content:message}); box.value=''; renderMessages(true);
  $('statusBox').textContent='Отправляем…'; $('discussButton').disabled=true;
  const requestId=crypto.randomUUID(); state.pendingJob=requestId;
  let clientId=localStorage.getItem('kc-client-id'); if(!clientId){clientId=crypto.randomUUID();localStorage.setItem('kc-client-id',clientId);}
  try{
    await json('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message,chat_id:state.currentChat,client_id:clientId,request_id:requestId,agent_id:state.selectedAgent})});
    while(state.pendingJob){
      const d=await json('/api/jobs/'+requestId);
      $('statusBox').textContent=d.state==='generating'?'K&C отвечает…':'В очереди…';
      renderMessages(true,d.assistant?.content||'');
      if(d.state==='done'){
        if(d.assistant?.content)state.messages.push({role:'assistant',content:d.assistant.content});
        if(d.chat_id){state.currentChat=d.chat_id;localStorage.setItem('kc-agency-chat',d.chat_id);}
        state.pendingJob=null; $('statusBox').textContent='Готово'; renderMessages(); break;
      }
      if(d.state==='error')throw new Error(d.error||'Ошибка генерации');
      await new Promise(r=>setTimeout(r,500));
    }
  }catch(e){
    state.pendingJob=null; $('statusBox').textContent=e.message; renderMessages();
  }finally{$('discussButton').disabled=false;}
}
$('discussButton').onclick=sendChat;
$('ideaInput').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();sendChat();}});
$('newChat').onclick=()=>{state.currentChat=null;state.selectedAgent=null;state.messages=[];localStorage.removeItem('kc-agency-chat');renderMessages();$('statusBox').textContent='Новый чат';};
renderMessages();

async function loadMemory(){
  try{
    const d=await json('/api/chats');
    $('memoryList').innerHTML=(d.items||[]).slice(0,20).map(x=>`<button class="memory-item" data-memory="${safe(x.id)}"><strong>${safe(x.title)}</strong><small>${new Date(x.updated_at).toLocaleString('ru-RU')}</small></button>`).join('')||'<p class="muted">Сохранённых чатов пока нет.</p>';
    document.querySelectorAll('[data-memory]').forEach(b=>b.onclick=()=>{
      const chat=(d.items||[]).find(x=>x.id===b.dataset.memory); if(!chat)return;
      state.currentChat=chat.id; localStorage.setItem('kc-agency-chat',chat.id);
      state.messages=chat.messages.map(m=>({role:m.role,content:m.content})); showPage('chat');renderMessages();
    });
  }catch(e){$('memoryList').innerHTML=`<p class="muted">${safe(e.message)}</p>`;}
}
$('refreshMemory').onclick=loadMemory;

async function checkServer(){
  const started=performance.now();
  try{
    const h=await json('/api/health'); state.server=true;state.latency=Math.max(1,Math.round(performance.now()-started));
    $('infraLed').className='led green'; $('infraText').textContent=`Стабильно · ${state.latency} мс`;
    $('systemSummary').textContent=h.assistant==='configured'?`СТАБИЛЬНО • ${h.agents||0} АГЕНТОВ`:`СЕРВЕР ЕСТЬ • НУЖЕН КЛЮЧ • ${h.agents||0} АГЕНТОВ`;
  }catch{
    state.server=false;$('infraLed').className='led red';$('infraText').textContent='Недоступна';$('systemSummary').textContent='НЕТ СВЯЗИ С СЕРВЕРОМ';
  }
}
$('infraStatus').onclick=checkServer;
$('notifyButton').onclick=()=>{
  const tasks=load('kc-agency-tasks',[]).filter(t=>!t.done);
  openSheet('События',tasks.length?'<div class="stack compact">'+tasks.slice(0,8).map(t=>`<div class="sheet-card">${safe(t.text)}</div>`).join('')+'</div>':'<div class="sheet-card">Новых событий нет.</div>');
};

$('autoCheck').checked=state.autoCheck;
$('haptics').checked=state.haptics;
$('autoCheck').onchange=e=>{state.autoCheck=e.target.checked;localStorage.setItem('kc-agency-auto-check',e.target.checked?'1':'0');};
$('haptics').onchange=e=>{state.haptics=e.target.checked;localStorage.setItem('kc-agency-haptics',e.target.checked?'1':'0');};
matchMedia('(prefers-color-scheme: dark)').addEventListener('change',()=>{if(state.theme==='system')applyTheme('system');});

applyTheme(state.theme); renderGreeting(); checkServer(); requestProfile();
setInterval(()=>{if(state.autoCheck)checkServer();},30000);

if('serviceWorker'in navigator){navigator.serviceWorker.register('/sw.js',{updateViaCache:'none'}).then(r=>r.update()).catch(()=>{});}


// Premium K&C launch transition
const launchScreen=document.getElementById('launchScreen');
if(launchScreen){
  window.setTimeout(()=>{
    launchScreen.classList.add('is-hiding');
    window.setTimeout(()=>launchScreen.remove(),460);
  },1850);
}
