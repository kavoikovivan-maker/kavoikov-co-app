const $ = id => document.getElementById(id);
const input=$('ideaInput'), statusBox=$('statusBox'), output=$('discussionOutput');
let session=localStorage.getItem('kc-session'), pending=localStorage.getItem('kc-job'), polling=false;
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function busy(on){ $('discussButton').disabled=on; $('newDiscussionButton').disabled=on; $('starterOne').disabled=on; $('starterTwo').disabled=on; }
async function api(url, options={}) {
 const controller=new AbortController(), timer=setTimeout(()=>controller.abort(),20000);
 try {
  const r=await fetch(url,{...options,cache:'no-store',signal:controller.signal});
  if(!r.headers.get('content-type')?.includes('application/json')) throw new Error('Нужно открыть приложение в Safari и войти в GitHub.');
  const data=await r.json();
  if(!r.ok) {const e=new Error(data.error||'Сервер недоступен.');e.status=r.status;throw e;}
  return data;
 } catch(e) {
  if(e instanceof TypeError || e.name==='AbortError') throw new Error('Связь с сервером прервалась. Проверьте, работает ли Codespace. Запрос повторно не отправлялся.');
  throw e;
 } finally {clearTimeout(timer);}
}
function render(data){output.innerHTML=['author','critic'].map(role=>`<div class="response-card"><h4>${role==='author'?'Автор':'Критик'}</h4><p>${escapeHTML(data[role]?.content || 'Ожидание ответа…')}</p>${data[role]?`<span class="response-meta">${escapeHTML(data[role].time_sec)} сек</span>`:''}</div>`).join('');}
async function history(){
 const data=await api('/api/discussions');
 $('historyList').innerHTML=(data.items||[]).map(item=>`<div class="history-item"><h5>${escapeHTML(new Date(item.created_at).toLocaleString('ru-RU'))}</h5><p><strong>Идея:</strong> ${escapeHTML(item.idea)}</p>${item.messages.map(m=>`<p><strong>${{author:'Автор',critic:'Критик',user:'Вы'}[m.role]||'Запись'}:</strong> ${escapeHTML(m.content)}</p>`).join('')}<button class="mini-button" data-session="${escapeHTML(item.id)}">Продолжить</button></div>`).join('') || '<p>Пока нет обсуждений.</p>';
 $('historyList').querySelectorAll('[data-session]').forEach(b=>b.onclick=()=>{if(pending)return;session=b.dataset.session;localStorage.setItem('kc-session',session);input.value='';statusBox.textContent='Продолжаем выбранное обсуждение';input.focus();window.scrollTo(0,0);});
}
async function poll(){
 if(polling||!pending)return; polling=true;busy(true);
 try{
  while(pending){
   const data=await api('/api/jobs/'+pending);render(data);
   statusBox.textContent=({queued:'В очереди…',author:'Отвечает Автор…',critic:'Отвечает Критик…',done:'Готово. Обсуждение сохранено.',error:data.error})[data.state]||data.state;
   if(['done','error'].includes(data.state)){
    if(data.session_id){session=data.session_id;localStorage.setItem('kc-session',session);}
    pending=null;localStorage.removeItem('kc-job');busy(false);await history();break;
   }
   await new Promise(r=>setTimeout(r,2000));
  }
 }catch(e){statusBox.textContent=e.message+' Нажмите «Проверить ответ».';}
 finally{polling=false; $('checkButton').hidden=!pending;}
}
$('discussButton').onclick=async()=>{
 if(pending||polling)return;
 const idea=input.value.trim();if(!idea){input.focus();return;}
 pending=crypto.randomUUID();localStorage.setItem('kc-job',pending);busy(true);render({});statusBox.textContent='Отправляем идею…';
 try{await api('/api/discussions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({idea,session_id:session,request_id:pending})});input.value='';await poll();}
 catch(e){statusBox.textContent=e.message;if(e.status){pending=null;localStorage.removeItem('kc-job');busy(false);} $('checkButton').hidden=!pending;}
};
$('checkButton').onclick=async()=>{
 try{await api('/api/jobs/'+pending);await poll();}
 catch(e){if(e.status===404){pending=null;localStorage.removeItem('kc-job');busy(false);$('checkButton').hidden=true;statusBox.textContent='Сервер не принял запрос. Теперь можно отправить идею вручную.';}else statusBox.textContent=e.message;}
};
$('newDiscussionButton').onclick=()=>{if(pending)return;session=null;localStorage.removeItem('kc-session');input.value='';statusBox.textContent='Новое обсуждение';render({});};
$('starterOne').onclick=()=>{if(pending)return;$('newDiscussionButton').click();input.value='Сначала делаем помощника только для меня без Telegram';input.focus();};
$('starterTwo').onclick=()=>{input.value='Какой первый шаг?';input.focus();};
$('fabButton').onclick=()=>{input.focus();window.scrollTo({top:0,behavior:'smooth'});};
window.addEventListener('online',()=>{if(pending)poll();else history().catch(e=>statusBox.textContent=e.message);});
if('serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js',{updateViaCache:'none'}).then(r=>r.update()).catch(()=>{});
busy(!!pending);history().catch(e=>statusBox.textContent=e.message);if(pending)poll();
