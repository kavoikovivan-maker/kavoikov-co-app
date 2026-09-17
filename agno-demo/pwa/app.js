const $ = id => document.getElementById(id);
const startedAt = Date.now();
const state = {
  mode: localStorage.getItem('kc-network-mode') || 'wifi',
  theme: localStorage.getItem('kc-theme') || 'dark',
  internet: navigator.onLine,
  server: false,
  assistantConfigured: null,
  latency: null,
  tx: 0,
  rx: 0,
  reconnects: 0,
  logs: [],
  dragging: false,
};

const input = $('ideaInput');
const statusBox = $('statusBox');
const output = $('discussionOutput');
let currentChat = localStorage.getItem('kc-chat');
let pending = localStorage.getItem('kc-job');
let pendingPrompt = localStorage.getItem('kc-pending-message') || '';
let currentMessages = [];
let polling = false;
let clientId = localStorage.getItem('kc-client-id');
if (!clientId) {
  clientId = crypto.randomUUID();
  localStorage.setItem('kc-client-id', clientId);
}

const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
}[c]));

function addLog(message) {
  state.logs.unshift({ time: new Date(), message });
  state.logs = state.logs.slice(0, 24);
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} Б`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(bytes < 10240 ? 1 : 0)} КБ`;
  return `${(bytes / 1024 / 1024).toFixed(1)} МБ`;
}

function updateTraffic() {
  $('txValue').textContent = formatBytes(state.tx);
  $('rxValue').textContent = formatBytes(state.rx);
}

function setLed(element, status) {
  if (!element) return;
  element.classList.remove('online', 'offline', 'checking', 'standby');
  element.classList.add(status);
}

function applyTheme(theme) {
  state.theme = theme;
  localStorage.setItem('kc-theme', theme);
  const resolved = theme === 'system'
    ? (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark')
    : theme;
  document.documentElement.dataset.theme = resolved;
  document.querySelector('meta[name="theme-color"]').content = resolved === 'light' ? '#edf0f3' : '#07090c';
  document.querySelectorAll('[data-theme]').forEach(button => button.classList.toggle('active', button.dataset.theme === theme));
}

function showPage(page) {
  document.querySelectorAll('[data-page]').forEach(section => section.classList.toggle('active', section.dataset.page === page));
  document.querySelectorAll('[data-page-target]').forEach(button => button.classList.toggle('active', button.dataset.pageTarget === page));
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function renderMode() {
  document.querySelectorAll('[data-mode]').forEach(button => button.classList.toggle('active', button.dataset.mode === state.mode));
  const labels = { wifi: 'Интернет', vpn: 'VPN', proxy: 'VK Proxy' };
  $('connectionLabel').textContent = labels[state.mode];
  if (state.mode === 'wifi') {
    $('connectionButton').textContent = 'Проверить соединение';
  } else {
    $('connectionButton').textContent = 'Открыть настройки';
    $('connectionState').textContent = 'Ожидает подключения';
    $('connectionOrb').className = 'status-orb checking';
    $('signalBars').classList.remove('online');
  }
}

function renderNetwork() {
  const internetStatus = state.internet ? 'online' : 'offline';
  const serverStatus = !state.server ? 'offline' : state.assistantConfigured ? 'online' : 'checking';
  setLed($('internetLed'), internetStatus);
  setLed($('serverLed'), serverStatus);
  setLed($('edgeInternetLed'), internetStatus);
  setLed($('edgeServerLed'), serverStatus);
  $('internetModuleState').textContent = state.internet ? 'Работает' : 'Нет сети';
  $('serverModuleState').textContent = !state.server ? 'Недоступен' : state.assistantConfigured ? 'Готов' : 'Нужен ключ';
  $('edgeInternetText').textContent = state.internet ? 'работает' : 'нет сети';
  $('edgeServerText').textContent = !state.server ? 'недоступен' : state.assistantConfigured ? 'готов' : 'нужен ключ';
  $('serverLatency').textContent = state.latency === null ? '—' : `${state.latency} мс`;
  $('reconnectValue').textContent = state.reconnects;

  const allGood = state.internet && state.server && state.assistantConfigured;
  $('topStatus').textContent = !state.internet
    ? 'Нет интернета'
    : !state.server
      ? 'Интернет есть · сервер недоступен'
      : state.assistantConfigured
        ? `K&C GPT готов · ${state.latency} мс`
        : 'Сервер доступен · нужен API-ключ';
  if (state.mode === 'wifi') {
    $('connectionState').textContent = allGood ? 'Подключено' : !state.internet ? 'Нет соединения' : state.server && !state.assistantConfigured ? 'Нужен API-ключ' : 'Сервер недоступен';
    $('connectionOrb').className = `status-orb ${allGood ? 'online' : 'offline'}`;
    $('connectionOrb').setAttribute('aria-label', allGood ? 'Соединение работает' : 'Соединение недоступно');
    $('signalBars').classList.toggle('online', state.internet);
  }
}

async function rawJSON(url, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 20000);
  const bodySize = typeof options.body === 'string' ? new Blob([options.body]).size : 0;
  state.tx += bodySize;
  try {
    const response = await fetch(url, { ...options, cache: 'no-store', signal: controller.signal });
    const text = await response.text();
    state.rx += new Blob([text]).size;
    updateTraffic();
    let data;
    try { data = JSON.parse(text); }
    catch { throw new Error('Нужно открыть приложение в Safari и войти в GitHub.'); }
    if (!response.ok) {
      const error = new Error(data.error || 'Сервер недоступен.');
      error.status = response.status;
      error.code = data.code;
      throw error;
    }
    return data;
  } catch (error) {
    if (error instanceof TypeError || error.name === 'AbortError') {
      throw new Error('Связь с сервером прервалась. Запрос повторно не отправлялся.');
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

async function checkConnection(manual = false) {
  state.internet = navigator.onLine;
  if (manual) state.reconnects += 1;
  $('connectionButton').disabled = true;
  if (state.mode === 'wifi') {
    $('connectionState').textContent = 'Проверяем…';
    $('connectionOrb').className = 'status-orb checking';
  }
  const begin = performance.now();
  try {
    const health = await rawJSON('/api/health');
    state.latency = Math.max(1, Math.round(performance.now() - begin));
    state.server = true;
    state.assistantConfigured = health.assistant === 'configured';
    addLog(`Сервер ответил за ${state.latency} мс`);
  } catch (error) {
    state.latency = null;
    state.server = false;
    state.assistantConfigured = null;
    addLog(error.message);
  } finally {
    state.internet = navigator.onLine;
    $('connectionButton').disabled = false;
    renderNetwork();
  }
}

function openSheet(title, html) {
  $('sheetTitle').textContent = title;
  $('sheetContent').innerHTML = html;
  $('sheetBackdrop').hidden = false;
  $('bottomSheet').hidden = false;
}

function closeSheet() {
  $('sheetBackdrop').hidden = true;
  $('bottomSheet').hidden = true;
}

function openLogs() {
  const items = state.logs.length ? state.logs.map(item => `
    <div class="log-entry"><time>${item.time.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</time><span>${escapeHTML(item.message)}</span></div>
  `).join('') : '<div class="sheet-result"><p>Записей пока нет.</p></div>';
  openSheet('Журнал соединения', `<div class="log-list">${items}</div>`);
}

async function runSpeedCheck() {
  openSheet('Проверка скорости', '<div class="sheet-result"><strong>…</strong><p>Измеряем отклик вашего сервера</p></div>');
  const samples = [];
  for (let i = 0; i < 3; i += 1) {
    const begin = performance.now();
    try { await rawJSON(`/api/health?t=${Date.now()}-${i}`); samples.push(performance.now() - begin); }
    catch { break; }
  }
  const average = samples.length ? Math.round(samples.reduce((sum, value) => sum + value, 0) / samples.length) : null;
  $('sheetContent').innerHTML = average === null
    ? '<div class="sheet-result"><strong>Нет связи</strong><p>Сервер не ответил. Проверьте подключение.</p></div>'
    : `<div class="sheet-result"><strong>${average} мс</strong><p>Средний отклик сервера по трём запросам. Скорость канала в Мбит/с требует отдельного тестового сервера.</p></div>`;
  addLog(average === null ? 'Проверка отклика не выполнена' : `Средний отклик: ${average} мс`);
}

function openMedia() {
  openSheet('Медиапанель', '<div class="sheet-result"><div class="media-art"><span>K&amp;C</span></div><strong>Готова</strong><p>Здесь появятся обложка, название, полоса времени и управление, когда будет подключён источник музыки или видео.</p></div>');
}

function renderUsage(usage) {
  const isPro = usage.plan === 'pro';
  $('usagePlan').textContent = isPro ? 'План Pro' : 'Бесплатный план';
  $('usageLabel').textContent = `${usage.remaining} из ${usage.limit} сообщений осталось сегодня`;
  $('usageBar').style.width = `${Math.min(100, Math.round((usage.used / Math.max(1, usage.limit)) * 100))}%`;
  $('upgradeButton').textContent = isPro ? 'Pro ✓' : 'Pro';
}

async function refreshUsage() {
  try {
    const usage = await rawJSON(`/api/usage?client_id=${encodeURIComponent(clientId)}`);
    renderUsage(usage);
  } catch {
    $('usageLabel').textContent = 'Не удалось проверить лимит';
  }
}

function openUpgrade() {
  openSheet('Тарифы K&C GPT', `
    <div class="sheet-result">
      <strong>Free → Pro</strong>
      <p><b>Free</b> — 10 сообщений в день и быстрые ответы для обычных задач.</p>
      <p><b>Pro</b> — до 200 сообщений в день, более мощная модель и длинные диалоги.</p>
      <p>Сейчас идёт тестирование. Оплата пока не списывается, а условия могут быть скорректированы перед запуском.</p>
    </div>
  `);
}

function busy(on) {
  $('discussButton').disabled = on;
  $('newDiscussionButton').disabled = on;
  $('starterOne').disabled = on;
  $('starterTwo').disabled = on;
}

function renderConversation(waiting = false, partial = '') {
  const messages = currentMessages.length
    ? currentMessages
    : [{ role: 'assistant', content: 'Здравствуйте! Я K&C GPT. Помогу с программированием, рабочими задачами и разработкой напитков. С чего начнём?' }];
  output.innerHTML = messages.map(message => `
    <article class="message-row ${message.role === 'user' ? 'user' : 'assistant'}">
      ${message.role === 'assistant' ? '<div class="message-avatar">K&amp;C</div>' : ''}
      <div class="message-bubble">
        <p>${escapeHTML(message.content)}</p>
        ${message.time_sec ? `<span class="message-meta">${escapeHTML(message.time_sec)} сек</span>` : ''}
      </div>
    </article>
  `).join('') + (waiting ? (partial ? `
    <article class="message-row assistant"><div class="message-avatar">K&amp;C</div><div class="message-bubble streaming"><p>${escapeHTML(partial)}</p><span class="stream-cursor" aria-hidden="true"></span></div></article>
  ` : `
    <article class="message-row assistant"><div class="message-avatar">K&amp;C</div><div class="message-bubble"><div class="typing-dots" aria-label="Помощник отвечает"><i></i><i></i><i></i></div></div></article>
  `) : '');
  requestAnimationFrame(() => output.lastElementChild?.scrollIntoView({ behavior: 'smooth', block: 'end' }));
}

async function history() {
  const data = await rawJSON('/api/chats');
  const selected = (data.items || []).find(item => item.id === currentChat);
  if (selected && !currentMessages.length) {
    currentMessages = selected.messages.map(message => ({ role: message.role, content: message.content }));
  }
  if (pending && pendingPrompt && currentMessages.at(-1)?.content !== pendingPrompt) {
    currentMessages.push({ role: 'user', content: pendingPrompt });
  }
  renderConversation(Boolean(pending));
  $('historyList').innerHTML = (data.items || []).map(item => `
    <div class="history-item">
      <h3>${escapeHTML(item.title)}</h3>
      <time>${escapeHTML(new Date(item.updated_at).toLocaleString('ru-RU'))}</time>
      <p>${escapeHTML(item.messages.at(-1)?.content || '')}</p>
      <button class="small-button" data-chat="${escapeHTML(item.id)}">Открыть</button>
    </div>
  `).join('') || '<p>Пока нет сохранённых чатов.</p>';
  $('historyList').querySelectorAll('[data-chat]').forEach(button => {
    button.onclick = () => {
      if (pending) return;
      const chat = data.items.find(item => item.id === button.dataset.chat);
      if (!chat) return;
      currentChat = chat.id;
      currentMessages = chat.messages.map(message => ({ role: message.role, content: message.content }));
      localStorage.setItem('kc-chat', currentChat);
      input.value = '';
      statusBox.textContent = 'Чат открыт';
      renderConversation();
      input.focus();
      window.scrollTo(0, 0);
    };
  });
}

async function poll() {
  if (polling || !pending) return;
  polling = true;
  busy(true);
  try {
    while (pending) {
      const data = await rawJSON(`/api/jobs/${pending}`);
      renderConversation(!['done', 'error'].includes(data.state), data.assistant?.content || '');
      statusBox.textContent = ({ queued: 'В очереди…', generating: 'K&C GPT отвечает…', done: 'Готово', error: data.error })[data.state] || data.state;
      if (['done', 'error'].includes(data.state)) {
        if (data.state === 'done' && data.assistant) {
          const alreadyShown = currentMessages.at(-1)?.role === 'assistant' && currentMessages.at(-1)?.content === data.assistant.content;
          if (!alreadyShown) currentMessages.push({ role: 'assistant', content: data.assistant.content, time_sec: data.assistant.time_sec });
          if (data.chat_id) { currentChat = data.chat_id; localStorage.setItem('kc-chat', currentChat); }
        }
        pending = null;
        localStorage.removeItem('kc-job');
        localStorage.removeItem('kc-pending-message');
        pendingPrompt = '';
        busy(false);
        renderConversation();
        await refreshUsage();
        await history();
        break;
      }
      await new Promise(resolve => setTimeout(resolve, 450));
    }
  } catch (error) {
    statusBox.textContent = `${error.message} Нажмите «Проверить ответ».`;
  } finally {
    polling = false;
    $('checkButton').hidden = !pending;
  }
}

function setPanelState(next) {
  $('edgePanel').dataset.state = next;
  $('edgePanel').style.transform = '';
}

function initEdgePanel() {
  const panel = $('edgePanel');
  const grip = $('edgeGrip');
  let startX = 0;
  let startTranslate = 0;
  let moved = false;

  grip.addEventListener('pointerdown', event => {
    state.dragging = true;
    moved = false;
    startX = event.clientX;
    const width = panel.getBoundingClientRect().width;
    startTranslate = panel.dataset.state === 'open' ? 0 : panel.dataset.state === 'hidden' ? width - 5 : width - 54;
    panel.classList.add('dragging');
    grip.setPointerCapture(event.pointerId);
  });

  grip.addEventListener('pointermove', event => {
    if (!state.dragging) return;
    const width = panel.getBoundingClientRect().width;
    const delta = event.clientX - startX;
    if (Math.abs(delta) > 4) moved = true;
    const translate = Math.max(0, Math.min(width - 5, startTranslate + delta));
    panel.style.transform = `translateX(${translate}px)`;
  });

  const finish = event => {
    if (!state.dragging) return;
    state.dragging = false;
    panel.classList.remove('dragging');
    if (grip.hasPointerCapture(event.pointerId)) grip.releasePointerCapture(event.pointerId);
    const width = panel.getBoundingClientRect().width;
    const matrix = new DOMMatrixReadOnly(getComputedStyle(panel).transform);
    const translate = matrix.m41;
    if (!moved) setPanelState(panel.dataset.state === 'open' ? ($('railToggle').checked ? 'rail' : 'hidden') : 'open');
    else if (translate < width * .42) setPanelState('open');
    else setPanelState($('railToggle').checked ? 'rail' : 'hidden');
  };
  grip.addEventListener('pointerup', finish);
  grip.addEventListener('pointercancel', finish);
  grip.addEventListener('dblclick', () => setPanelState(panel.dataset.state === 'hidden' ? 'rail' : 'hidden'));
}

document.querySelectorAll('[data-page-target]').forEach(button => button.addEventListener('click', () => showPage(button.dataset.pageTarget)));
document.querySelectorAll('[data-open-page]').forEach(button => button.addEventListener('click', () => { showPage(button.dataset.openPage); setPanelState($('railToggle').checked ? 'rail' : 'hidden'); }));
document.querySelectorAll('[data-mode]').forEach(button => button.addEventListener('click', () => {
  state.mode = button.dataset.mode;
  localStorage.setItem('kc-network-mode', state.mode);
  renderMode();
  renderNetwork();
}));
document.querySelectorAll('[data-theme]').forEach(button => button.addEventListener('click', () => applyTheme(button.dataset.theme)));

$('themeButton').onclick = () => applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
$('connectionButton').onclick = () => state.mode === 'wifi' ? checkConnection(true) : showPage('settings');
$('logsButton').onclick = openLogs;
$('speedButton').onclick = runSpeedCheck;
$('mediaButton').onclick = openMedia;
$('edgeMedia').onclick = openMedia;
$('edgeReconnect').onclick = () => checkConnection(true);
$('upgradeButton').onclick = openUpgrade;
$('sheetClose').onclick = closeSheet;
$('sheetBackdrop').onclick = closeSheet;
$('edgeClose').onclick = () => setPanelState($('railToggle').checked ? 'rail' : 'hidden');
$('railToggle').onchange = event => {
  localStorage.setItem('kc-show-rail', event.target.checked ? '1' : '0');
  if ($('edgePanel').dataset.state !== 'open') setPanelState(event.target.checked ? 'rail' : 'hidden');
};
$('autoCheckToggle').onchange = event => localStorage.setItem('kc-auto-check', event.target.checked ? '1' : '0');

document.querySelectorAll('[data-edge-action]').forEach(button => button.addEventListener('click', () => {
  const action = button.dataset.edgeAction;
  if (action === 'connection') showPage('home');
  if (action === 'server') showPage('chat');
  if (action === 'vpn' || action === 'proxy') {
    state.mode = action;
    localStorage.setItem('kc-network-mode', state.mode);
    renderMode();
    showPage('home');
  }
  setPanelState($('railToggle').checked ? 'rail' : 'hidden');
}));

$('discussButton').onclick = async () => {
  if (pending || polling) return;
  const message = input.value.trim();
  if (!message) { input.focus(); return; }
  pending = crypto.randomUUID();
  pendingPrompt = message;
  localStorage.setItem('kc-job', pending);
  localStorage.setItem('kc-pending-message', pendingPrompt);
  currentMessages.push({ role: 'user', content: message });
  busy(true);
  renderConversation(true);
  statusBox.textContent = 'Отправляем сообщение…';
  try {
    await rawJSON('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message, chat_id: currentChat, client_id: clientId, request_id: pending }) });
    input.value = '';
    await poll();
  } catch (error) {
    statusBox.textContent = error.message;
    if (error.code === 'daily_limit') openUpgrade();
    if (error.status) {
      pending = null;
      pendingPrompt = '';
      localStorage.removeItem('kc-job');
      localStorage.removeItem('kc-pending-message');
      busy(false);
      renderConversation();
    }
    $('checkButton').hidden = !pending;
  }
};

$('checkButton').onclick = async () => {
  try { await rawJSON(`/api/jobs/${pending}`); await poll(); }
  catch (error) {
    if (error.status === 404) {
      pending = null;
      localStorage.removeItem('kc-job');
      localStorage.removeItem('kc-pending-message');
      busy(false);
      $('checkButton').hidden = true;
      statusBox.textContent = 'Сервер не принял сообщение. Его можно отправить ещё раз.';
    } else statusBox.textContent = error.message;
  }
};

$('newDiscussionButton').onclick = () => { if (!pending) { currentChat = null; currentMessages = []; localStorage.removeItem('kc-chat'); input.value = ''; statusBox.textContent = 'Новый чат'; renderConversation(); } };
$('starterOne').onclick = () => { if (!pending) { input.value = 'Помоги мне с программированием: '; input.focus(); } };
$('starterTwo').onclick = () => { if (!pending) { input.value = 'Помоги разработать новый вкус напитка: '; input.focus(); } };
input.addEventListener('keydown', event => {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    $('discussButton').click();
  }
});

window.addEventListener('online', () => { state.internet = true; addLog('Интернет появился'); checkConnection(); if (pending) poll(); });
window.addEventListener('offline', () => { state.internet = false; state.server = false; state.assistantConfigured = null; state.latency = null; addLog('Интернет отключён'); renderNetwork(); });
matchMedia('(prefers-color-scheme: light)').addEventListener('change', () => { if (state.theme === 'system') applyTheme('system'); });

setInterval(() => {
  const seconds = Math.floor((Date.now() - startedAt) / 1000);
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const rest = seconds % 60;
  $('uptimeValue').textContent = hours ? `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}` : `${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`;
}, 1000);

applyTheme(state.theme);
$('railToggle').checked = localStorage.getItem('kc-show-rail') !== '0';
$('autoCheckToggle').checked = localStorage.getItem('kc-auto-check') !== '0';
setPanelState($('railToggle').checked ? 'rail' : 'hidden');
renderMode();
renderNetwork();
initEdgePanel();
busy(Boolean(pending));
checkConnection();
renderConversation(Boolean(pending));
history().catch(error => { statusBox.textContent = error.message; }).finally(() => { if (pending) poll(); });
refreshUsage();
if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js', { updateViaCache: 'none' }).then(registration => registration.update()).catch(() => {});
setInterval(() => { if ($('autoCheckToggle').checked && !pending) checkConnection(); }, 30000);
