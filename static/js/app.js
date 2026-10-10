const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

const MONTHS = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];
const MONTHS_GEN = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
const WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];
const WEEKDAYS_FULL = ['понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье'];
const moneyFormatter = new Intl.NumberFormat('ru-RU', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
const MOOD_PROMPT_STORAGE_KEY = 'reform_mood_prompt_date';
const WELCOME_STORAGE_KEY = 'reform_welcome_seen';

let activeTaskMap = new Map();
let notificationTaskMap = new Map();
let availableSections = [];
let pageRefresh = () => {};
let toastTimer = null;
let dataChannel = null;
let pageReady = false;
let refreshPromise = null;
let activeDatePicker = null;
let datePickerRoot = null;
let taskSummaryTasks = [];
let taskSummaryMode = null;

function pad(value) { return String(value).padStart(2, '0'); }
function isoDate(value) { const d = new Date(value); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`; }
function parseIso(value) { const [y, m, d] = value.split('-').map(Number); return new Date(y, m - 1, d); }
function todayIso() { return isoDate(new Date()); }
function monthKey(value) { const d = value instanceof Date ? value : new Date(value); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}`; }
function firstOfMonth(value) { return new Date(value.getFullYear(), value.getMonth(), 1); }
function lastOfMonth(value) { return new Date(value.getFullYear(), value.getMonth() + 1, 0); }
function mondayOf(value) { const d = new Date(value); const day = d.getDay(); d.setDate(d.getDate() + (day === 0 ? -6 : 1 - day)); d.setHours(0, 0, 0, 0); return d; }
function addDays(value, amount) { const d = new Date(value); d.setDate(d.getDate() + amount); return d; }
function dateRange(start, end) { const result = []; for (let d = new Date(start); d <= end; d = addDays(d, 1)) result.push(new Date(d)); return result; }
function formatDate(value, withYear = false) { const d = typeof value === 'string' ? parseIso(value) : value; return `${d.getDate()} ${MONTHS_GEN[d.getMonth()]}${withYear ? ` ${d.getFullYear()}` : ''}`; }
function formatShortDate(value) { const d = typeof value === 'string' ? parseIso(value) : value; return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}`; }
function formatMoney(minor) { return `${moneyFormatter.format((Number(minor) || 0) / 100)} ₽`; }
function amountToMinor(value) { const normalized = String(value || '').replace(/\s/g, '').replace(',', '.'); const amount = Number(normalized); return Number.isFinite(amount) && amount > 0 ? Math.round(amount * 100) : 0; }
function escapeHtml(value) { return String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[char])); }

async function api(path, options = {}) {
  const response = await fetch(path, { headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }, ...options });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.ok === false) throw new Error(payload.error || `Ошибка запроса (${response.status})`);
  return payload;
}

function showToast(message, isError = false) {
  const toast = $('#toast');
  if (!toast) return;
  toast.textContent = message;
  toast.classList.toggle('error', isError);
  toast.classList.add('visible');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove('visible'), 3200);
}

function announceDataChange(type = 'data') {
  try { dataChannel?.postMessage({ type, at: Date.now() }); } catch { /* BroadcastChannel may be unavailable in an embedded webview. */ }
}

async function refreshCurrentPageSafely() {
  if (!pageReady || typeof pageRefresh !== 'function' || refreshPromise) return refreshPromise;
  refreshPromise = Promise.resolve().then(() => pageRefresh()).catch(error => showToast(error.message, true)).finally(() => { refreshPromise = null; });
  return refreshPromise;
}

function bindDataSync() {
  if ('BroadcastChannel' in window) {
    dataChannel = new BroadcastChannel('reform-life-data');
    dataChannel.addEventListener('message', event => {
       if (['tasks', 'sections', 'notes', 'mood', 'data'].includes(event.data?.type)) refreshCurrentPageSafely();
    });
  }
  window.addEventListener('pageshow', event => { if (event.persisted) refreshCurrentPageSafely(); });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refreshCurrentPageSafely(); });
}

function openModal(id) { const modal = $(`#${id}`); if (modal) { modal.classList.add('open'); modal.setAttribute('aria-hidden', 'false'); } }
function closeModal(id) { const modal = $(`#${id}`); if (modal) { modal.classList.remove('open'); modal.setAttribute('aria-hidden', 'true'); } }

function hideWelcome() {
  const welcome = $('#welcomeModal');
  if (!welcome) return;
  try { sessionStorage.setItem(WELCOME_STORAGE_KEY, '1'); } catch { /* storage may be unavailable in a restricted webview */ }
  welcome.classList.remove('open');
  welcome.setAttribute('aria-hidden', 'true');
  setTimeout(() => { if (!welcome.classList.contains('open')) welcome.hidden = true; }, 260);
}

function initWelcome() {
  const welcome = $('#welcomeModal');
  if (!welcome) return;
  let seen = false;
  try { seen = sessionStorage.getItem(WELCOME_STORAGE_KEY) === '1'; } catch { /* storage may be unavailable in a restricted webview */ }
  $('#welcomeClose')?.addEventListener('click', hideWelcome);
  $('#welcomeStart')?.addEventListener('click', hideWelcome);
  welcome.addEventListener('click', event => { if (event.target === welcome) hideWelcome(); });
  if (seen) return;
  welcome.hidden = false;
  welcome.setAttribute('aria-hidden', 'false');
  requestAnimationFrame(() => welcome.classList.add('open'));
  setTimeout(() => $('#welcomeStart')?.focus(), 280);
}

function datePickerViewDate(input) {
  const value = input?.value || '';
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return parseIso(value);
  if (/^\d{4}-\d{2}$/.test(value)) return new Date(Number(value.slice(0, 4)), Number(value.slice(5, 7)) - 1, 1);
  return new Date();
}

function datePickerYearOptions(year) {
  const first = Math.min(1950, year - 10); const last = Math.max(2100, year + 10);
  return Array.from({ length: last - first + 1 }, (_, index) => first + index).map(item => `<option value="${item}" ${item === year ? 'selected' : ''}>${item}</option>`).join('');
}

function ensureDatePicker() {
  if (datePickerRoot) return datePickerRoot;
  datePickerRoot = document.createElement('div');
  datePickerRoot.className = 'custom-date-picker';
  datePickerRoot.hidden = true;
  datePickerRoot.innerHTML = `<div class="date-picker-header"><button class="date-picker-arrow" type="button" data-date-picker-prev aria-label="Предыдущий месяц">‹</button><div class="date-picker-selects"><select class="date-picker-month" aria-label="Месяц"></select><select class="date-picker-year" aria-label="Год"></select></div><button class="date-picker-arrow" type="button" data-date-picker-next aria-label="Следующий месяц">›</button></div><div class="date-picker-weekdays">${WEEKDAYS.map(day => `<span>${day}</span>`).join('')}</div><div class="date-picker-grid"></div><div class="date-picker-month-grid"></div><div class="date-picker-footer"><button type="button" data-date-picker-clear>Очистить</button><button type="button" data-date-picker-today>Сегодня</button></div>`;
  document.body.appendChild(datePickerRoot);
  $('[data-date-picker-prev]', datePickerRoot).addEventListener('click', () => shiftDatePickerMonth(-1));
  $('[data-date-picker-next]', datePickerRoot).addEventListener('click', () => shiftDatePickerMonth(1));
  $('.date-picker-month', datePickerRoot).addEventListener('change', event => { if (!activeDatePicker) return; activeDatePicker.view.setMonth(Number(event.target.value)); renderDatePicker(); });
  $('.date-picker-year', datePickerRoot).addEventListener('change', event => { if (!activeDatePicker) return; activeDatePicker.view.setFullYear(Number(event.target.value)); renderDatePicker(); });
  $('[data-date-picker-clear]', datePickerRoot).addEventListener('click', () => selectDatePickerValue(''));
  $('[data-date-picker-today]', datePickerRoot).addEventListener('click', () => selectDatePickerValue(activeDatePicker?.mode === 'month' ? todayIso().slice(0, 7) : todayIso()));
  document.addEventListener('pointerdown', event => { if (!activeDatePicker || datePickerRoot.hidden) return; const anchor = activeDatePicker.anchor; if (!datePickerRoot.contains(event.target) && !anchor?.contains(event.target)) closeDatePicker(); });
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && activeDatePicker) closeDatePicker(); });
  window.addEventListener('resize', positionDatePicker);
  return datePickerRoot;
}

function positionDatePicker() {
  if (!activeDatePicker || !datePickerRoot || datePickerRoot.hidden) return;
  const anchor = activeDatePicker.anchor; if (!anchor) return;
  const rect = anchor.getBoundingClientRect(); const width = datePickerRoot.offsetWidth || 304; const height = datePickerRoot.offsetHeight || 360; const gap = 8;
  const left = Math.max(10, Math.min(window.innerWidth - width - 10, rect.left));
  const below = rect.bottom + gap; const top = below + height <= window.innerHeight - 10 ? below : Math.max(10, rect.top - height - gap);
  datePickerRoot.style.left = `${left}px`; datePickerRoot.style.top = `${top}px`;
}

function renderDatePicker() {
  if (!activeDatePicker || !datePickerRoot) return;
  const { input, view, mode } = activeDatePicker; const monthSelect = $('.date-picker-month', datePickerRoot); const yearSelect = $('.date-picker-year', datePickerRoot);
  monthSelect.innerHTML = MONTHS.map((month, index) => `<option value="${index}" ${index === view.getMonth() ? 'selected' : ''}>${month}</option>`).join(''); yearSelect.innerHTML = datePickerYearOptions(view.getFullYear());
  const weekdays = $('.date-picker-weekdays', datePickerRoot); const grid = $('.date-picker-grid', datePickerRoot); const monthGrid = $('.date-picker-month-grid', datePickerRoot);
  if (mode === 'month') {
    weekdays.hidden = true; grid.hidden = true; monthGrid.hidden = false;
    monthGrid.innerHTML = MONTHS.map((month, index) => { const value = `${view.getFullYear()}-${pad(index + 1)}`; return `<button type="button" class="date-picker-month-cell ${input.value === value ? 'selected' : ''}" data-date-picker-value="${value}">${month.slice(0, 3)}</button>`; }).join('');
    $$('[data-date-picker-value]', monthGrid).forEach(button => button.addEventListener('click', () => selectDatePickerValue(button.dataset.datePickerValue)));
  } else {
    weekdays.hidden = false; grid.hidden = false; monthGrid.hidden = true;
    const first = mondayOf(new Date(view.getFullYear(), view.getMonth(), 1)); const days = dateRange(first, addDays(first, 41)); const selected = input.value;
    grid.innerHTML = days.map(date => { const value = isoDate(date); const outside = date.getMonth() !== view.getMonth(); const classes = [outside ? 'outside' : '', value === selected ? 'selected' : '', value === todayIso() ? 'today' : ''].filter(Boolean).join(' '); return `<button type="button" class="date-picker-day ${classes}" data-date-picker-value="${value}">${date.getDate()}</button>`; }).join('');
    $$('[data-date-picker-value]', grid).forEach(button => button.addEventListener('click', () => selectDatePickerValue(button.dataset.datePickerValue)));
  }
  positionDatePicker();
}

function shiftDatePickerMonth(amount) { if (!activeDatePicker) return; activeDatePicker.view = new Date(activeDatePicker.view.getFullYear(), activeDatePicker.view.getMonth() + amount, 1); renderDatePicker(); }

function selectDatePickerValue(value) {
  if (!activeDatePicker) return;
  const { input } = activeDatePicker; input.value = value; input.dispatchEvent(new Event('input', { bubbles: true })); input.dispatchEvent(new Event('change', { bubbles: true })); closeDatePicker();
}

function openDatePicker(input, anchor = input?.closest('.date-picker-field') || input) {
  if (!input) return;
  const mode = input.type === 'month' ? 'month' : 'date'; const view = datePickerViewDate(input); activeDatePicker = { input, anchor, mode, view: new Date(view.getFullYear(), view.getMonth(), 1) }; const picker = ensureDatePicker(); picker.hidden = false; picker.classList.add('open'); renderDatePicker();
}

function closeDatePicker() { if (!datePickerRoot) return; datePickerRoot.hidden = true; datePickerRoot.classList.remove('open'); activeDatePicker = null; }

function initDatePickers() {
  ensureDatePicker();
  $$('input[type="date"], input[type="month"]').forEach(input => {
    if (input.dataset.customDatePicker === 'true') return;
    input.dataset.customDatePicker = 'true';
    if (input.classList.contains('legacy-week-picker')) {
      input.addEventListener('focus', event => { event.preventDefault(); openDatePicker(input, $('#week-card') || input); });
      return;
    }
    const wrapper = document.createElement('div'); wrapper.className = 'date-picker-field'; input.parentNode.insertBefore(wrapper, input); wrapper.appendChild(input); input.classList.add('date-picker-input'); input.setAttribute('readonly', 'readonly');
    const trigger = document.createElement('button'); trigger.type = 'button'; trigger.className = 'date-picker-trigger'; trigger.setAttribute('aria-label', 'Открыть календарь'); trigger.textContent = '▣'; wrapper.appendChild(trigger);
    wrapper.addEventListener('click', event => { event.preventDefault(); openDatePicker(input, wrapper); });
    input.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); openDatePicker(input, wrapper); } });
  });
}

function updateGlobalDate() {
  const chip = $('#globalToday');
  if (chip) chip.textContent = `${WEEKDAYS[(new Date().getDay() + 6) % 7]}, ${formatShortDate(todayIso())}`;
}

function bindCommon() {
  updateGlobalDate();
  $('#quickRefresh')?.addEventListener('click', async () => { await pageRefresh(); await loadNotifications(); });
  $('#notificationBell')?.addEventListener('click', event => { event.stopPropagation(); const panel = $('#notificationPanel'); if (!panel) return; const isOpen = panel.classList.toggle('open'); panel.setAttribute('aria-hidden', String(!isOpen)); $('#notificationBell').setAttribute('aria-expanded', String(isOpen)); });
  document.addEventListener('click', event => { if (!event.target.closest('.notification-wrap')) closeNotifications(); });
  $$('[data-close-modal]').forEach(button => button.addEventListener('click', () => closeModal(button.dataset.closeModal)));
  $$('[data-task-summary]').forEach(button => button.addEventListener('click', () => openTaskSummary(button.dataset.taskSummary)));
  $$('.modal-backdrop').forEach(modal => modal.addEventListener('click', event => { if (event.target === modal) closeModal(modal.id); }));
  document.addEventListener('keydown', event => { if (event.key === 'Escape') $$('.modal-backdrop.open').forEach(modal => closeModal(modal.id)); });
  $$('.nav-link').forEach(link => link.addEventListener('click', () => localStorage.setItem('reform_active_page', document.body.dataset.page)));
}

function taskTime(task) {
  if (!task.start_time && !task.end_time) return '';
  return `${task.start_time || '—'}${task.end_time ? ` - ${task.end_time}` : ''}`;
}

function taskSummaryMarkup(task, mode) {
  const meta = mode === 'done'
    ? `${formatDate(task.task_date, true)}${taskTime(task) ? ` · ${escapeHtml(taskTime(task))}` : ''}`
    : `Просрочено с ${formatShortDate(task.task_date)}${taskTime(task) ? ` · ${escapeHtml(taskTime(task))}` : ''}`;
  const toggleLabel = mode === 'done' ? 'Вернуть задачу в работу' : 'Отметить задачу выполненной';
  return `<article class="task-summary-item" data-summary-task="${task.id}">
    <button class="task-summary-toggle" type="button" data-summary-toggle="${task.id}" aria-label="${toggleLabel}">${mode === 'done' ? '✓' : '!'}</button>
    <button class="task-summary-main" type="button" data-summary-edit="${task.id}"><strong>${escapeHtml(task.text)}</strong><small>${escapeHtml(meta)} · ${escapeHtml(task.section || 'Личное')}</small></button>
    <span class="task-summary-status ${mode === 'overdue' ? 'overdue' : ''}">${mode === 'done' ? 'Выполнено' : 'Просрочено'}</span>
    <button class="task-summary-delete" type="button" data-summary-delete="${task.id}" title="Удалить">×</button>
  </article>`;
}

function renderTaskSummary() {
  const list = $('#taskSummaryList');
  if (!list || !taskSummaryMode) return;
  const today = todayIso();
  const items = taskSummaryTasks.filter(task => taskSummaryMode === 'done' ? task.done : !task.done && task.task_date < today);
  const isDoneArchive = taskSummaryMode === 'done';
  $('#taskSummaryKicker').textContent = isDoneArchive ? 'АРХИВ ЗАДАЧ' : 'ТРЕБУЮТ ВНИМАНИЯ';
  $('#taskSummaryTitle').textContent = isDoneArchive ? 'Выполненные задачи' : 'Просроченные задачи';
  $('#taskSummarySubtitle').textContent = items.length
    ? `${items.length} ${plural(items.length, isDoneArchive ? 'задача завершена' : 'задача просрочена', isDoneArchive ? 'задачи завершены' : 'задачи просрочены', isDoneArchive ? 'задач завершено' : 'задач просрочено')}`
    : (isDoneArchive ? 'Архив пока пуст — так держать.' : 'Просроченных задач нет. Можно выдохнуть.');
  list.innerHTML = items.length ? items.map(task => taskSummaryMarkup(task, taskSummaryMode)).join('') : `<div class="task-summary-empty">${isDoneArchive ? 'Здесь появятся задачи после выполнения.' : 'Все задачи идут по плану.'}</div>`;

  $$('[data-summary-toggle]', list).forEach(button => button.addEventListener('click', async event => {
    event.stopPropagation();
    const task = taskSummaryTasks.find(item => item.id === Number(button.dataset.summaryToggle));
    if (!task) return;
    try { await api(`/api/tasks/${task.id}`, { method: 'PATCH', body: JSON.stringify({ done: !task.done }) }); announceDataChange('tasks'); await pageRefresh(); await loadNotifications(); } catch (error) { showToast(error.message, true); }
  }));
  $$('[data-summary-edit]', list).forEach(button => button.addEventListener('click', () => {
    const task = taskSummaryTasks.find(item => item.id === Number(button.dataset.summaryEdit));
    if (!task) return;
    closeModal('taskSummaryModal');
    openTaskModal(task);
  }));
  $$('[data-summary-delete]', list).forEach(button => button.addEventListener('click', async event => {
    event.stopPropagation();
    if (!window.confirm('Удалить эту задачу?')) return;
    try { await api(`/api/tasks/${button.dataset.summaryDelete}`, { method: 'DELETE' }); announceDataChange('tasks'); await pageRefresh(); await loadNotifications(); } catch (error) { showToast(error.message, true); }
  }));
}

function openTaskSummary(mode) {
  if (!['done', 'overdue'].includes(mode)) return;
  taskSummaryMode = mode;
  renderTaskSummary();
  openModal('taskSummaryModal');
}

async function loadSections() {
  const result = await api('/api/sections');
  availableSections = result.sections || [];
  const select = $('#taskSection');
  if (select) select.innerHTML = availableSections.map(section => `<option value="${escapeHtml(section.name)}">${escapeHtml(section.name)}</option>`).join('');
}

function closeNotifications() {
  const panel = $('#notificationPanel'); const bell = $('#notificationBell');
  if (!panel) return;
  panel.classList.remove('open'); panel.setAttribute('aria-hidden', 'true'); bell?.setAttribute('aria-expanded', 'false');
}

function renderNotifications(notifications) {
  const count = $('#notificationCount'); const panelCount = $('#notificationPanelCount'); const list = $('#notificationList');
  if (!count || !panelCount || !list) return;
  notificationTaskMap = new Map(notifications.map(task => [task.id, task]));
  count.textContent = String(notifications.length); count.hidden = notifications.length === 0;
  panelCount.textContent = String(notifications.length);
  list.innerHTML = notifications.length ? notifications.map(task => `<button class="notification-item" type="button" data-notification-task="${task.id}"><span class="notification-item-dot"></span><span class="notification-item-copy"><strong>${escapeHtml(task.text)}</strong><small>Просрочено с ${escapeHtml(formatShortDate(task.task_date))}${taskTime(task) ? ` · ${escapeHtml(taskTime(task))}` : ''}</small></span><span class="notification-item-arrow">›</span></button>`).join('') : '<div class="notification-empty">Просроченных задач нет.<br>Так держать!</div>';
  $$('[data-notification-task]', list).forEach(button => button.addEventListener('click', () => { const task = notificationTaskMap.get(Number(button.dataset.notificationTask)); if (!task) return; activeTaskMap.set(task.id, task); closeNotifications(); openTaskModal(task); }));
}

async function loadNotifications() {
  if (!$('#notificationBell')) return;
  const result = await api('/api/notifications');
  renderNotifications(result.notifications || []);
}

function hideMoodPrompt(markSeen = false) {
  const prompt = $('#moodPrompt');
  if (!prompt) return;
  if (markSeen) localStorage.setItem(MOOD_PROMPT_STORAGE_KEY, todayIso());
  prompt.classList.remove('open');
  prompt.setAttribute('aria-hidden', 'true');
  setTimeout(() => { if (!prompt.classList.contains('open')) prompt.hidden = true; }, 180);
}

async function saveMoodFromPrompt(score) {
  try {
    await api(`/api/mood/${todayIso()}`, { method: 'PUT', body: JSON.stringify({ score }) });
    announceDataChange('mood');
    hideMoodPrompt(true);
    showToast('Настроение сохранено');
  } catch (error) {
    showToast(error.message, true);
  }
}

async function initMoodPrompt() {
  const prompt = $('#moodPrompt');
  if (!prompt || localStorage.getItem(MOOD_PROMPT_STORAGE_KEY) === todayIso()) return;
  try {
    const result = await api('/api/mood/today');
    if (result.entry) {
      localStorage.setItem(MOOD_PROMPT_STORAGE_KEY, todayIso());
      return;
    }
    $$('[data-mood-score]', prompt).forEach(button => {
      button.onclick = () => saveMoodFromPrompt(Number(button.dataset.moodScore));
    });
    $('#moodPromptLater')?.addEventListener('click', () => hideMoodPrompt(true), { once: true });
    $('#moodPromptClose')?.addEventListener('click', () => hideMoodPrompt(true), { once: true });
    localStorage.setItem(MOOD_PROMPT_STORAGE_KEY, todayIso());
    prompt.hidden = false;
    prompt.setAttribute('aria-hidden', 'false');
    requestAnimationFrame(() => prompt.classList.add('open'));
  } catch (error) {
    // Напоминание не должно мешать работе приложения, если база временно недоступна.
    console.warn('Не удалось показать напоминание о настроении', error);
  }
}

function taskMarkup(task, variant = '') {
  return `<div class="task-item ${task.done ? 'done' : ''} ${variant}" data-task-id="${task.id}">
    <button class="task-check" type="button" aria-label="Отметить задачу"></button>
    <div class="task-main"><span class="task-title">${escapeHtml(task.text)}</span>${taskTime(task) ? `<span class="task-time">${escapeHtml(taskTime(task))}</span>` : ''}</div>
    <button class="task-delete" type="button" title="Удалить">×</button>
  </div>`;
}

function bindTaskElements(root, refresh) {
  $$('.task-check', root).forEach(button => button.addEventListener('click', async event => {
    event.stopPropagation();
    const item = button.closest('[data-task-id]');
    const task = activeTaskMap.get(Number(item.dataset.taskId));
    if (!task) return;
    try { await api(`/api/tasks/${task.id}`, { method: 'PATCH', body: JSON.stringify({ done: !task.done }) }); announceDataChange('tasks'); await refresh(); await loadNotifications(); } catch (error) { showToast(error.message, true); }
  }));
  $$('.task-main', root).forEach(button => button.addEventListener('click', () => {
    const item = button.closest('[data-task-id]'); const task = activeTaskMap.get(Number(item.dataset.taskId)); if (task) openTaskModal(task);
  }));
  $$('.task-delete', root).forEach(button => button.addEventListener('click', async event => {
    event.stopPropagation(); const item = button.closest('[data-task-id]'); const task = activeTaskMap.get(Number(item.dataset.taskId)); if (!task) return;
    if (!window.confirm('Удалить эту задачу?')) return;
    try { await api(`/api/tasks/${task.id}`, { method: 'DELETE' }); announceDataChange('tasks'); await refresh(); await loadNotifications(); } catch (error) { showToast(error.message, true); }
  }));
}

function openTaskModal(task = null, date = todayIso(), scope = document.body.dataset.page === 'tasks' ? 'tasks' : 'planner', section = null) {
  $('#taskModalTitle').textContent = task ? 'Редактировать задачу' : 'Новая задача';
  $('#taskId').value = task?.id || '';
  $('#taskScope').value = task?.scope || scope;
  $('#taskText').value = task?.text || '';
  if ($('#taskSection')) $('#taskSection').value = task?.section || section || availableSections[0]?.name || 'Личное';
  $('#taskDate').value = task?.task_date || date;
  $('#taskStart').value = task?.start_time || '';
  $('#taskEnd').value = task?.end_time || '';
  openModal('taskModal');
  setTimeout(() => $('#taskText')?.focus(), 40);
}

async function saveTask(event) {
  event.preventDefault();
  const id = $('#taskId').value;
  const payload = { text: $('#taskText').value.trim(), section: $('#taskSection')?.value || 'Личное', scope: $('#taskScope')?.value || 'planner', task_date: $('#taskDate').value, start_time: $('#taskStart').value || null, end_time: $('#taskEnd').value || null };
  try {
    if (id) await api(`/api/tasks/${id}`, { method: 'PATCH', body: JSON.stringify(payload) });
    else await api('/api/tasks', { method: 'POST', body: JSON.stringify(payload) });
    announceDataChange('tasks');
    closeModal('taskModal'); showToast(id ? 'Задача обновлена' : 'Задача добавлена'); await pageRefresh(); await loadNotifications();
  } catch (error) { showToast(error.message, true); }
}

function openSectionModal() {
  $('#sectionName').value = '';
  $('#sectionColor').value = '#4D67FF';
  openModal('sectionModal');
  setTimeout(() => $('#sectionName')?.focus(), 40);
}

async function saveSection(event) {
  event.preventDefault();
  const payload = { name: $('#sectionName').value.trim(), color: $('#sectionColor').value };
  try {
    await api('/api/sections', { method: 'POST', body: JSON.stringify(payload) });
    announceDataChange('sections');
    closeModal('sectionModal');
    showToast('Раздел добавлен');
    await loadSections();
    await pageRefresh();
  } catch (error) { showToast(error.message, true); }
}

function parseLegacyTime(value) {
  const matches = String(value || '').match(/(\d{1,2}:\d{2})\s*[--]\s*(\d{1,2}:\d{2})/);
  return matches ? { start_time: matches[1], end_time: matches[2] } : { start_time: null, end_time: null };
}

function collectLegacyData() {
  const tasks = []; const goals = []; const notes = [];
  for (let index = 0; index < localStorage.length; index += 1) {
    const key = localStorage.key(index); if (!key) continue;
    let value = null; try { value = JSON.parse(localStorage.getItem(key)); } catch { continue; }
    if (key.startsWith('week_tasks_') && value && typeof value === 'object') {
      Object.entries(value).forEach(([taskDate, dayTasks]) => (Array.isArray(dayTasks) ? dayTasks : []).forEach(task => tasks.push({ task_date: taskDate, text: task.text, ...parseLegacyTime(task.time), done: Boolean(task.done) })));
    } else if (key.startsWith('week_goal_')) {
      goals.push({ week_monday: key.replace('week_goal_', ''), text: typeof value === 'string' ? value : '' });
    } else if (key === 'notes' && Array.isArray(value)) {
      value.forEach(note => {
        const match = String(note.date || '').match(/^(\d{2})\.(\d{2})$/);
        const now = new Date(); const noteDate = match ? `${now.getFullYear()}-${match[2]}-${match[1]}` : todayIso();
        notes.push({ text: note.text, note_date: noteDate });
      });
    }
  }
  return { tasks, goals, notes };
}

async function maybeMigrateLegacy() {
  if (localStorage.getItem('reform_migration_v1')) return;
  const legacy = collectLegacyData();
  const hasLegacy = legacy.tasks.length || legacy.goals.length || legacy.notes.length;
  if (!hasLegacy) { localStorage.setItem('reform_migration_v1', 'clean'); return; }
  openModal('migrationModal');
  return new Promise(resolve => {
    $('#migrationClean').onclick = () => { localStorage.setItem('reform_migration_v1', 'clean'); closeModal('migrationModal'); resolve(); };
    $('#migrationImport').onclick = async () => {
      try { const result = await api('/api/migrate', { method: 'POST', body: JSON.stringify(legacy) }); localStorage.setItem('reform_migration_v1', 'imported'); closeModal('migrationModal'); showToast(`Перенесено: ${result.imported.tasks} задач, ${result.imported.notes} заметок`); resolve(); }
      catch (error) { showToast(error.message, true); }
    };
  });
}

function openNoteModal(note = null) {
  $('#noteModalTitle').textContent = note ? 'Редактировать заметку' : 'Новая заметка';
  $('#noteId').value = note?.id || '';
  $('#noteDate').value = note?.note_date || todayIso();
  $('#noteText').value = note?.text || '';
  $('#notePinned').checked = Boolean(note?.pinned);
  openModal('noteModal');
  setTimeout(() => $('#noteText')?.focus(), 40);
}

function noteMarkup(note, variant = '') {
  return `<div class="note-item ${variant} ${note.pinned ? 'pinned' : ''}" data-note-id="${note.id}"><span class="note-pin-dot" aria-hidden="true"></span><span class="note-copy">${escapeHtml(note.text)}<small>${escapeHtml(formatShortDate(note.note_date))}</small></span><button class="note-pin-button" type="button" data-toggle-note-pin="${note.id}" title="${note.pinned ? 'Открепить' : 'Закрепить'}">${note.pinned ? '★' : '☆'}</button><button class="note-edit-button" type="button" data-edit-note="${note.id}" title="Редактировать">✎</button><button class="note-delete-button" type="button" data-note-id="${note.id}" title="Удалить">×</button></div>`;
}

function bindNoteActions(root, notes, refresh) {
  $$('[data-toggle-note-pin]', root).forEach(button => button.addEventListener('click', async event => {
    event.stopPropagation();
    const note = notes.find(item => item.id === Number(button.dataset.toggleNotePin));
    if (!note) return;
    try { await api(`/api/notes/${note.id}`, { method: 'PATCH', body: JSON.stringify({ pinned: !note.pinned }) }); await refresh(); } catch (error) { showToast(error.message, true); }
  }));
  $$('[data-edit-note]', root).forEach(button => button.addEventListener('click', event => { event.stopPropagation(); const note = notes.find(item => item.id === Number(button.dataset.editNote)); if (note) openNoteModal(note); }));
  $$('[data-note-id].note-delete-button, .note-delete-button[data-note-id]', root).forEach(button => button.addEventListener('click', async event => {
    event.stopPropagation();
    if (!window.confirm('Удалить эту заметку?')) return;
    try { await api(`/api/notes/${button.dataset.noteId}`, { method: 'DELETE' }); await refresh(); } catch (error) { showToast(error.message, true); }
  }));
}

async function loadNotes() {
  const result = await api('/api/notes'); const root = $('#notesList'); if (!root) return;
  const notes = result.notes || [];
  const cards = notes.map(note => noteMarkup(note)).join('');
  root.innerHTML = `${cards}<button class="new-note" type="button"><strong>＋</strong><span>Добавить заметку</span></button>`;
  bindNoteActions(root, notes, loadNotes);
  $('.new-note', root)?.addEventListener('click', () => openNoteModal());
}

async function saveNote(event) {
  event.preventDefault(); const id = $('#noteId').value; const text = $('#noteText').value.trim(); if (!text) return;
  const payload = { text, note_date: $('#noteDate').value || todayIso(), pinned: $('#notePinned').checked };
  try { await api(id ? `/api/notes/${id}` : '/api/notes', { method: id ? 'PATCH' : 'POST', body: JSON.stringify(payload) }); announceDataChange('notes'); closeModal('noteModal'); $('#noteText').value = ''; $('#noteId').value = ''; showToast(id ? 'Заметка обновлена' : 'Заметка добавлена'); await pageRefresh(); } catch (error) { showToast(error.message, true); }
}

function renderProgress(percent, ring) {
  const degree = Math.round(percent * 3.6); if (ring) ring.style.background = `conic-gradient(var(--pink) ${degree}deg, #1a2636 ${degree}deg)`;
}

async function initWeek() {
  const requestedDate = new URLSearchParams(window.location.search).get('date');
  const initialDate = /^\d{4}-\d{2}-\d{2}$/.test(requestedDate || '') ? parseIso(requestedDate) : new Date();
  const state = { monday: mondayOf(initialDate), tasks: [], notes: [], mood: { entries: [], average_score: null, label: 'Пока нет отметок' } };
  const load = async () => {
    const dates = dateRange(state.monday, addDays(state.monday, 6));
    const [result, mood] = await Promise.all([
      api(`/api/tasks?scope=planner&start=${isoDate(dates[0])}&end=${isoDate(dates[6])}`),
      api(`/api/mood?start=${isoDate(dates[0])}&end=${isoDate(dates[6])}`),
    ]);
    state.tasks = result.tasks; state.mood = mood;
    const goal = await api(`/api/goals/${isoDate(state.monday)}`); $('#weekGoal').value = goal.goal.text || '';
    await renderWeek();
  };
  const renderWeek = async () => {
    const dates = dateRange(state.monday, addDays(state.monday, 6)); const byDate = Object.groupBy ? Object.groupBy(state.tasks, task => task.task_date) : state.tasks.reduce((map, task) => { (map[task.task_date] ||= []).push(task); return map; }, {});
    activeTaskMap = new Map(state.tasks.map(task => [task.id, task]));
    $('#weekRange').textContent = `${dates[0].getDate()} - ${dates[6].getDate()} ${MONTHS_GEN[dates[6].getMonth()]}`;
    $('#weekYear').textContent = dates[6].getFullYear();
    $('#weekTitle').textContent = `${MONTHS[state.monday.getMonth()]} · ${dates[0].getDate()}-${dates[6].getDate()}`;
    $('#weekPicker').value = isoDate(state.monday);
    const root = $('#weekDays'); root.innerHTML = dates.map((date, index) => {
      const dateKey = isoDate(date); const tasks = byDate[dateKey] || []; const done = tasks.filter(task => task.done).length; const percent = tasks.length ? Math.round(done / tasks.length * 100) : 0;
      return `<div class="day-column legacy-day"><div class="day-head"><div class="day-name">${WEEKDAYS[index]}</div><div class="day-date ${dateKey === todayIso() ? 'current' : ''}">${formatShortDate(dateKey)}</div><div class="day-progress"><i style="width:${percent}%"></i></div></div><div class="task-list">${tasks.length ? tasks.map(task => taskMarkup(task)).join('') : '<div class="empty-day">Свободный день — отличный момент для паузы.</div>'}</div><button class="add-task-link" type="button" data-add-date="${dateKey}">＋ Добавить задачу</button></div>`;
    }).join('');
    $$('[data-add-date]', root).forEach(button => button.addEventListener('click', () => openTaskModal(null, button.dataset.addDate)));
    bindTaskElements(root, load);
    const total = state.tasks.length; const done = state.tasks.filter(task => task.done).length; const percent = total ? Math.round(done / total * 100) : 0;
    $('#weekCompleted').textContent = `${done} из ${total}`; $('#weekLeft').textContent = `Осталось ${total - done}`; $('#weekPercent').textContent = `${percent}%`; $('#largePercent').textContent = `${percent}%`; $('#ringDone').textContent = done; $('#ringRemaining').textContent = total - done; $('#ringAll').textContent = total; renderProgress(percent, $('#miniRing')); renderProgress(percent, $('#largeRing'));
    const moodScore = Number(state.mood?.average_score || 0);
    const moodSymbols = { 1: '☹', 2: '◔', 3: '•', 4: '⌣', 5: '☺' };
    $('#weekMoodIcon').textContent = moodSymbols[moodScore] || '⌣';
    $('#weekMoodLabel').textContent = state.mood?.label || 'Пока нет отметок';
    $('#weekMoodLine').classList.toggle('no-data', !(state.mood?.entries || []).length);
    const todayTasks = state.tasks.filter(task => task.task_date === todayIso()); const todayRoot = $('#todayList');
    $('#todayBadge').textContent = `${WEEKDAYS[(new Date().getDay() + 6) % 7]}, ${formatShortDate(todayIso())}`;
    todayRoot.innerHTML = todayTasks.length ? todayTasks.map(task => `<label class="today-item ${task.done ? 'done' : ''}"><input type="checkbox" data-today-task="${task.id}" ${task.done ? 'checked' : ''}><span>${escapeHtml(task.text)}</span><span class="today-time">${escapeHtml(taskTime(task))}</span></label>`).join('') : '<div class="empty-state">На сегодня задач нет — можно выдохнуть.</div>';
    $$('[data-today-task]', todayRoot).forEach(input => input.addEventListener('change', async () => { const task = activeTaskMap.get(Number(input.dataset.todayTask)); try { await api(`/api/tasks/${task.id}`, { method: 'PATCH', body: JSON.stringify({ done: input.checked }) }); announceDataChange('tasks'); await load(); } catch (error) { showToast(error.message, true); } }));
    await loadNotes();
  };
  pageRefresh = load; window.refreshCurrentPage = load;
  $('#weekPrev').onclick = () => { state.monday = addDays(state.monday, -7); load(); };
  $('#weekNext').onclick = () => { state.monday = addDays(state.monday, 7); load(); };
  $('#weekPicker').onchange = () => { state.monday = mondayOf(parseIso($('#weekPicker').value)); load(); };
  $('#week-card').onclick = () => openDatePicker($('#weekPicker'), $('#week-card'));
  if ($('#weekAddTask')) $('#weekAddTask').onclick = () => openTaskModal(null, isoDate(state.monday));
  $('#addNote').onclick = () => openNoteModal();
  $('#weekGoal').onblur = async () => { try { await api(`/api/goals/${isoDate(state.monday)}`, { method: 'PUT', body: JSON.stringify({ text: $('#weekGoal').value.trim() }) }); showToast('Цель сохранена'); } catch (error) { showToast(error.message, true); } };
  await load();
}

async function initMonth() {
  const state = { month: firstOfMonth(new Date()), selected: todayIso(), tasks: [], notes: [], priorities: [], sections: [] };
  const load = async () => {
    const gridStart = mondayOf(firstOfMonth(state.month));
    const gridEnd = addDays(mondayOf(lastOfMonth(state.month)), 6);
    const currentMonth = monthKey(state.month);
    const [tasks, notes, priorities, sections] = await Promise.all([
      api(`/api/tasks?scope=planner&start=${isoDate(gridStart)}&end=${isoDate(gridEnd)}`),
      api('/api/notes'),
      api(`/api/month/priorities?month=${currentMonth}`),
      api('/api/sections'),
    ]);
    state.tasks = tasks.tasks || [];
    state.notes = notes.notes || [];
    state.priorities = priorities.priorities || [];
    state.sections = sections.sections || [];
    availableSections = state.sections;
    if ($('#taskSection')) $('#taskSection').innerHTML = state.sections.map(section => `<option value="${escapeHtml(section.name)}">${escapeHtml(section.name)}</option>`).join('');
    render();
    await loadNotifications();
  };
  const render = () => {
    const first = firstOfMonth(state.month); const last = lastOfMonth(state.month); const gridStart = mondayOf(first); const gridEnd = addDays(mondayOf(last), 6); const dates = dateRange(gridStart, gridEnd);
    const byDate = state.tasks.reduce((map, task) => { (map[task.task_date] ||= []).push(task); return map; }, {});
    activeTaskMap = new Map(state.tasks.map(task => [task.id, task]));
    const sectionMap = new Map(state.sections.map(section => [section.name.toLowerCase(), section]));
    const total = state.tasks.length; const done = state.tasks.filter(task => task.done).length; const open = total - done; const overdue = state.tasks.filter(task => !task.done && task.task_date < todayIso()).length;
    const percent = value => total ? Math.round(value / total * 100) : 0;
    const setBar = (id, value) => { const bar = $(`#${id}`); if (bar) bar.style.width = `${Math.min(100, Math.max(0, value))}%`; };
    $('#monthTitle').textContent = `${MONTHS[state.month.getMonth()]} ${state.month.getFullYear()}`;
    if ($('#monthNavigatorLabel')) $('#monthNavigatorLabel').textContent = `${MONTHS[state.month.getMonth()]} ${state.month.getFullYear()}`;
    $('#monthTaskCount').textContent = total; $('#monthTaskTrend').textContent = `${state.sections.length} ${plural(state.sections.length, 'раздел', 'раздела', 'разделов')}`; setBar('monthTaskProgress', total ? 100 : 0);
    $('#monthDoneCount').textContent = done; $('#monthDonePercent').textContent = `${percent(done)}%`; setBar('monthDoneProgress', percent(done));
    $('#monthProgressCount').textContent = open; $('#monthProgressPercent').textContent = `${percent(open)}%`; setBar('monthOpenProgress', percent(open));
    $('#monthOverdueCount').textContent = overdue; $('#monthOverduePercent').textContent = `${percent(overdue)}%`; setBar('monthOverdueProgress', percent(overdue));

    const sectionFilter = $('#monthSectionFilter'); const previousSection = sectionFilter.value || 'all'; sectionFilter.innerHTML = `<option value="all">Все разделы</option>${state.sections.map(section => `<option value="${escapeHtml(section.name)}">${escapeHtml(section.name)}</option>`).join('')}`; sectionFilter.value = state.sections.some(section => section.name === previousSection) ? previousSection : 'all';
    $('#sectionLegend').innerHTML = state.sections.map(section => `<span class="legend-item"><i style="background:${escapeHtml(section.color)}"></i>${escapeHtml(section.name)}</span>`).join('');
    const filter = $('#monthFilter').value; const search = ($('#monthSearch')?.value || '').trim().toLocaleLowerCase('ru-RU'); const activeSection = sectionFilter.value;
    const shownTasks = state.tasks.filter(task => { if (filter === 'open' && task.done) return false; if (filter === 'done' && !task.done) return false; if (activeSection !== 'all' && task.section !== activeSection) return false; if (search && !String(task.text).toLocaleLowerCase('ru-RU').includes(search)) return false; return true; });
    const shownByDate = shownTasks.reduce((map, task) => { (map[task.task_date] ||= []).push(task); return map; }, {});
    const calendar = $('#monthCalendar');
    calendar.innerHTML = dates.map(date => {
      const key = isoDate(date); const tasks = shownByDate[key] || [];
      const chips = tasks.map(task => { const section = sectionMap.get(String(task.section || '').toLowerCase()); const color = section?.color || '#4D67FF'; return `<button class="calendar-task ${task.done ? 'done' : ''}" type="button" data-calendar-task-id="${task.id}" style="--task-color:${escapeHtml(color)}" title="Открыть задачу"><span>${escapeHtml(task.text)}</span>${taskTime(task) ? `<small>${escapeHtml(taskTime(task))}</small>` : ''}</button>`; }).join('');
      return `<div class="calendar-cell ${date.getMonth() !== state.month.getMonth() ? 'outside' : ''} ${key === state.selected ? 'selected' : ''} ${key === todayIso() ? 'today' : ''}" data-calendar-date="${key}"><div class="calendar-cell-head"><span class="calendar-day-number">${date.getDate()}</span><button class="calendar-add" type="button" data-add-calendar-date="${key}" aria-label="Добавить задачу на ${formatShortDate(key)}">＋</button></div><div class="calendar-task-list">${chips}</div></div>`;
    }).join('');
    $$('[data-calendar-date]', calendar).forEach(cell => cell.addEventListener('click', () => { state.selected = cell.dataset.calendarDate; render(); }));
    $$('[data-add-calendar-date]', calendar).forEach(button => button.addEventListener('click', event => { event.stopPropagation(); openTaskModal(null, button.dataset.addCalendarDate); }));
    $$('[data-calendar-task-id]', calendar).forEach(button => button.addEventListener('click', event => { event.stopPropagation(); const task = activeTaskMap.get(Number(button.dataset.calendarTaskId)); if (task) openTaskModal(task); }));

    const selected = parseIso(state.selected); $('#selectedDateLabel').textContent = formatShortDate(state.selected); $('#selectedDayTitle').textContent = `${selected.getDate()} ${MONTHS_GEN[selected.getMonth()]}`; const selectedTasks = shownByDate[state.selected] || []; $('#selectedTaskCount').textContent = `${selectedTasks.length} ${plural(selectedTasks.length, 'задача', 'задачи', 'задач')}`; const list = $('#selectedDayList'); list.innerHTML = selectedTasks.length ? selectedTasks.map(task => taskMarkup(task, 'selected-task')).join('') : '<div class="empty-state">На этот день задач нет.</div>'; bindTaskElements(list, load);

    $('#priorityProgressLabel').textContent = 'Все'; const priorityRoot = $('#priorityList'); priorityRoot.innerHTML = state.priorities.length ? state.priorities.map(priority => { const progress = Number(priority.progress || 0); return `<article class="priority-item" data-priority-id="${priority.id}"><div class="priority-item-top"><button class="priority-complete ${progress === 100 ? 'done' : ''}" type="button" data-toggle-priority="${priority.id}" aria-label="${progress === 100 ? 'Снять выполнение' : 'Отметить выполненным'}"><span>✓</span></button><button class="priority-title" type="button" data-edit-priority="${priority.id}">${escapeHtml(priority.text)}</button><strong>${progress}%</strong></div><div class="priority-track"><i style="width:${progress}%"></i></div><div class="priority-item-actions"><button class="row-action" type="button" data-edit-priority="${priority.id}" title="Редактировать">✎</button><button class="row-action" type="button" data-delete-priority="${priority.id}" title="Удалить">×</button></div></article>`; }).join('') : '<div class="empty-state">Добавьте первый приоритет месяца.</div>';
    $$('[data-edit-priority]', priorityRoot).forEach(button => button.addEventListener('click', () => openPriorityModal(state.priorities.find(item => item.id === Number(button.dataset.editPriority)))));
    $$('[data-delete-priority]', priorityRoot).forEach(button => button.addEventListener('click', async () => { if (!window.confirm('Удалить этот приоритет?')) return; try { await api(`/api/month/priorities/${button.dataset.deletePriority}`, { method: 'DELETE' }); await load(); } catch (error) { showToast(error.message, true); } }));
    $$('[data-toggle-priority]', priorityRoot).forEach(button => button.addEventListener('click', async () => { const priority = state.priorities.find(item => item.id === Number(button.dataset.togglePriority)); if (!priority) return; try { await api(`/api/month/priorities/${priority.id}`, { method: 'PATCH', body: JSON.stringify({ progress: Number(priority.progress) === 100 ? 0 : 100 }) }); await load(); } catch (error) { showToast(error.message, true); } }));

    const notes = search ? state.notes.filter(note => String(note.text).toLocaleLowerCase('ru-RU').includes(search)) : state.notes; const notesRoot = $('#monthNotesList'); notesRoot.innerHTML = notes.length ? notes.slice(0, 6).map(note => noteMarkup(note, 'month-note')).join('') : '<div class="empty-state">Заметок пока нет.</div>'; bindNoteActions(notesRoot, notes, load);
  };
  function shiftMonth(amount) { state.month = new Date(state.month.getFullYear(), state.month.getMonth() + amount, 1); state.selected = isoDate(state.month); load(); }
  function openPriorityModal(priority = null) { $('#priorityModalTitle').textContent = priority ? 'Редактировать приоритет' : 'Новый приоритет'; $('#priorityId').value = priority?.id || ''; $('#priorityText').value = priority?.text || ''; $('#priorityProgress').value = priority?.progress || 0; openModal('priorityModal'); setTimeout(() => $('#priorityText')?.focus(), 40); }
  pageRefresh = load; window.refreshCurrentPage = load; $('#monthPrev').onclick = () => shiftMonth(-1); $('#monthNext').onclick = () => shiftMonth(1); $('#monthToday').onclick = () => { state.month = firstOfMonth(new Date()); state.selected = todayIso(); load(); }; $('#monthFilter').onchange = render; $('#monthSectionFilter').onchange = render; $('#monthSearch').oninput = render; $('#monthAddTask').onclick = () => openTaskModal(null, state.selected); $('#selectedAddTask').onclick = () => openTaskModal(null, state.selected); $('#monthAddSection').onclick = openSectionModal; $('#addPriority').onclick = () => openPriorityModal(); $('#monthAddNote').onclick = () => openNoteModal();
  $('#priorityForm').onsubmit = async event => { event.preventDefault(); const id = $('#priorityId').value; const payload = { month: monthKey(state.month), text: $('#priorityText').value.trim(), progress: Number($('#priorityProgress').value) }; try { await api(id ? `/api/month/priorities/${id}` : '/api/month/priorities', { method: id ? 'PATCH' : 'POST', body: JSON.stringify(payload) }); closeModal('priorityModal'); showToast(id ? 'Приоритет обновлён' : 'Приоритет добавлен'); await load(); } catch (error) { showToast(error.message, true); } };
  await load();
}

async function initTasks() {
  const state = { tasks: [], sections: [] };
  const load = async () => {
    const [tasks, sections] = await Promise.all([api('/api/tasks?scope=tasks'), api('/api/sections')]);
    state.tasks = tasks.tasks || [];
    taskSummaryTasks = state.tasks;
    state.sections = sections.sections || [];
    availableSections = state.sections;
    if ($('#taskSection')) $('#taskSection').innerHTML = state.sections.map(section => `<option value="${escapeHtml(section.name)}">${escapeHtml(section.name)}</option>`).join('');
    render();
    await loadNotifications();
  };
  const render = () => {
    const today = todayIso();
    const overdue = state.tasks.filter(task => !task.done && task.task_date < today);
    const open = state.tasks.filter(task => !task.done);
    const done = state.tasks.filter(task => task.done);
    const sectionMap = new Map(state.sections.map(section => [section.name.toLowerCase(), section]));
    $('#tasksTotal').textContent = state.tasks.length;
    $('#tasksOpen').textContent = open.length;
    $('#tasksOpenCaption').textContent = `${open.length} ${plural(open.length, 'активная задача', 'активные задачи', 'активных задач')}`;
    $('#tasksDone').textContent = done.length;
    $('#tasksDoneCaption').textContent = `${done.length} ${plural(done.length, 'выполненная задача', 'выполненные задачи', 'выполненных задач')}`;
    $('#tasksOverdue').textContent = overdue.length;
    if ($('#taskSummaryModal')?.classList.contains('open')) renderTaskSummary();

    const filter = $('#tasksFilter').value;
    const search = ($('#tasksSearch').value || '').trim().toLocaleLowerCase('ru-RU');
    const shown = state.tasks.filter(task => {
      const isOverdue = !task.done && task.task_date < today;
      if (filter === 'all' && task.done) return false;
      if (filter === 'open' && task.done) return false;
      if (filter === 'done' && !task.done) return false;
      if (filter === 'overdue' && !isOverdue) return false;
      if (search && !`${task.text} ${task.section}`.toLocaleLowerCase('ru-RU').includes(search)) return false;
      return true;
    });
    $('#tasksListTitle').textContent = `${shown.length} ${plural(shown.length, 'задача', 'задачи', 'задач')}`;
    activeTaskMap = new Map(state.tasks.map(task => [task.id, task]));

    const columns = state.sections.map(section => ({
      section,
      tasks: shown.filter(task => String(task.section || '').toLocaleLowerCase('ru-RU') === String(section.name).toLocaleLowerCase('ru-RU')),
    }));
    const cardMarkup = task => {
      const isOverdue = !task.done && task.task_date < today;
      const section = sectionMap.get(String(task.section || '').toLowerCase());
      const color = section?.color || '#4D67FF';
      const time = taskTime(task);
      const status = task.done ? 'Выполнено' : isOverdue ? 'Просрочено' : 'В процессе';
      return `<article class="kanban-card ${task.done ? 'done' : ''} ${isOverdue ? 'overdue' : ''}" draggable="true" data-kanban-card="${task.id}">
        <div class="kanban-card-top">
          <button class="kanban-check ${task.done ? 'done' : ''}" type="button" data-kanban-toggle="${task.id}" aria-label="${task.done ? 'Вернуть задачу в работу' : 'Отметить задачу выполненной'}"><span>✓</span></button>
          <button class="kanban-card-title" type="button" data-kanban-edit="${task.id}">${escapeHtml(task.text)}</button>
          <div class="kanban-card-actions"><button class="row-action" type="button" data-kanban-edit="${task.id}" title="Редактировать">✎</button><button class="row-action" type="button" data-kanban-delete="${task.id}" title="Удалить">×</button></div>
        </div>
        <div class="kanban-card-section"><i style="background:${escapeHtml(color)}"></i><span>${escapeHtml(task.section || 'Личное')}</span></div>
        <div class="kanban-card-meta"><time>${escapeHtml(formatDate(task.task_date, true))}</time>${time ? `<span>${escapeHtml(time)}</span>` : '<span>Без времени</span>'}</div>
        <span class="kanban-card-status ${task.done ? 'done' : isOverdue ? 'overdue' : ''}">${status}</span>
      </article>`;
    };
    const board = $('#tasksKanban');
    board.style.setProperty('--kanban-columns', String(Math.max(columns.length, 1)));
    board.innerHTML = columns.map(({ section, tasks }) => `<section class="kanban-column" data-kanban-column="${section.id}" style="--section-color:${escapeHtml(section.color)}">
      <div class="kanban-column-heading"><div><span class="kanban-column-dot" style="background:${escapeHtml(section.color)}"></span><h3>${escapeHtml(section.name)}</h3></div><strong>${tasks.length}</strong></div>
      <div class="kanban-card-list" data-kanban-list="${section.id}">${tasks.length ? tasks.map(cardMarkup).join('') : `<div class="kanban-empty">${filter === 'all' && !search ? 'Здесь пока пусто' : 'По этому фильтру задач нет'}</div>`}</div>
      <button class="kanban-add" type="button" data-kanban-add-section="${escapeHtml(section.name)}">＋ Добавить задачу</button>
    </section>`).join('');

    $$('[data-kanban-toggle]', board).forEach(button => button.addEventListener('click', async event => {
      event.stopPropagation();
      const task = activeTaskMap.get(Number(button.dataset.kanbanToggle));
      if (!task) return;
      try { await api(`/api/tasks/${task.id}`, { method: 'PATCH', body: JSON.stringify({ done: !task.done }) }); announceDataChange('tasks'); await load(); } catch (error) { showToast(error.message, true); }
    }));
    $$('[data-kanban-edit]', board).forEach(button => button.addEventListener('click', event => {
      event.stopPropagation();
      const task = activeTaskMap.get(Number(button.dataset.kanbanEdit));
      if (task) openTaskModal(task);
    }));
    $$('[data-kanban-delete]', board).forEach(button => button.addEventListener('click', async event => {
      event.stopPropagation();
      if (!window.confirm('Удалить эту задачу?')) return;
      try { await api(`/api/tasks/${button.dataset.kanbanDelete}`, { method: 'DELETE' }); announceDataChange('tasks'); await load(); } catch (error) { showToast(error.message, true); }
    }));

    let draggedTaskId = null;
    $$('[data-kanban-card]', board).forEach(card => {
      card.addEventListener('dragstart', event => {
        draggedTaskId = Number(card.dataset.kanbanCard);
        card.classList.add('dragging');
        event.dataTransfer.effectAllowed = 'move';
        event.dataTransfer.setData('text/plain', String(draggedTaskId));
      });
      card.addEventListener('dragend', () => { draggedTaskId = null; card.classList.remove('dragging'); $$('[data-kanban-list]', board).forEach(list => list.classList.remove('drop-target')); });
    });
    $$('[data-kanban-list]', board).forEach(list => {
      list.addEventListener('dragover', event => { event.preventDefault(); list.classList.add('drop-target'); event.dataTransfer.dropEffect = 'move'; });
      list.addEventListener('dragleave', event => { if (!list.contains(event.relatedTarget)) list.classList.remove('drop-target'); });
      list.addEventListener('drop', async event => {
        event.preventDefault();
        list.classList.remove('drop-target');
        const taskId = draggedTaskId || Number(event.dataTransfer.getData('text/plain'));
        const task = activeTaskMap.get(taskId);
        const targetSection = state.sections.find(section => String(section.id) === String(list.dataset.kanbanList));
        if (!task || !targetSection || String(task.section).toLocaleLowerCase('ru-RU') === String(targetSection.name).toLocaleLowerCase('ru-RU')) return;
        try { await api(`/api/tasks/${task.id}`, { method: 'PATCH', body: JSON.stringify({ section: targetSection.name }) }); announceDataChange('tasks'); await load(); } catch (error) { showToast(error.message, true); }
      });
    });
    $$('[data-kanban-add-section]', board).forEach(button => button.addEventListener('click', () => openTaskModal(null, todayIso(), 'tasks', button.dataset.kanbanAddSection)));
  };
  pageRefresh = load; window.refreshCurrentPage = load; $('#tasksSearch').oninput = render; $('#tasksFilter').onchange = render; $('#tasksAddTask').onclick = () => openTaskModal(null, todayIso()); $('#tasksAddSection').onclick = openSectionModal;
  await load();
}

const ASSISTANT_WEEKDAYS = {
  понедельник: 0,
  вторник: 1,
  среда: 2,
  среду: 2,
  четверг: 3,
  пятница: 4,
  суббота: 5,
  воскресенье: 6,
};

const ASSISTANT_MONTHS = {
  января: 0,
  февраля: 1,
  марта: 2,
  апреля: 3,
  мая: 4,
  июня: 5,
  июля: 6,
  августа: 7,
  сентября: 8,
  октября: 9,
  ноября: 10,
  декабря: 11,
};

function assistantNormalize(value) {
  return String(value || '').toLocaleLowerCase('ru-RU').replace(/[«».,!?;]/g, ' ').replace(/\s+/g, ' ').trim();
}

function assistantDateFromText(value) {
  const text = assistantNormalize(value);
  const today = new Date();
  const relative = text.match(/(?:на|в)?\s*(послезавтра|завтра|сегодня)\b/);
  if (relative) return addDays(today, relative[1] === 'завтра' ? 1 : relative[1] === 'послезавтра' ? 2 : 0);
  const weekday = text.match(/(?:на|в)?\s*(понедельник|вторник|среда|среду|четверг|пятница|суббота|воскресенье)\b/);
  if (weekday) {
    const current = (today.getDay() + 6) % 7;
    let shift = (ASSISTANT_WEEKDAYS[weekday[1]] - current + 7) % 7;
    if (shift === 0) shift = 7;
    return addDays(today, shift);
  }
  const namedDate = text.match(/\b(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\b/);
  if (namedDate) {
    let year = today.getFullYear();
    let result = new Date(year, ASSISTANT_MONTHS[namedDate[2]], Number(namedDate[1]));
    if (result < new Date(today.getFullYear(), today.getMonth(), today.getDate())) result = new Date(year + 1, ASSISTANT_MONTHS[namedDate[2]], Number(namedDate[1]));
    return result;
  }
  const numericDate = text.match(/\b(\d{1,2})[./](\d{1,2})(?:[./](\d{4}))?\b/);
  if (numericDate) {
    const year = Number(numericDate[3] || today.getFullYear());
    return new Date(year, Number(numericDate[2]) - 1, Number(numericDate[1]));
  }
  return null;
}

function assistantScheduleFromText(value) {
  let text = String(value || '').trim();
  const scheduledDate = assistantDateFromText(text) || new Date();
  const timeMatch = text.match(/(?:\s+(?:в|на)\s+)(\d{1,2})(?::(\d{2}))?(?!:)\s*(?:час(?:а|ов)?\s*)?(утра|дня|вечера|ночи)?\b/i);
  let startTime = null;
  if (timeMatch) {
    let hour = Number(timeMatch[1]);
    const minute = Number(timeMatch[2] || 0);
    const part = String(timeMatch[3] || '').toLocaleLowerCase('ru-RU');
    if (part === 'вечера' && hour < 12) hour += 12;
    if (part === 'ночи' && hour === 12) hour = 0;
    if (part === 'утра' && hour === 12) hour = 0;
    if (hour <= 23 && minute <= 59) startTime = `${pad(hour)}:${pad(minute)}`;
    text = text.replace(timeMatch[0], ' ');
  }
  const datePattern = /(?:\s+(?:на|в)\s+)?(?:послезавтра|завтра|сегодня|понедельник|вторник|среда|среду|четверг|пятница|суббота|воскресенье)\b/gi;
  text = text.replace(datePattern, ' ');
  text = text.replace(/\s+(?:на|в)\s*$/i, '').replace(/\s+/g, ' ').replace(/[,.!?]+$/, '').trim();
  return { text, task_date: isoDate(scheduledDate), start_time: startTime };
}

function assistantDayLabel(dateKey) {
  const date = parseIso(dateKey);
  return `${WEEKDAYS_FULL[(date.getDay() + 6) % 7]}, ${formatShortDate(dateKey)}`;
}

async function initAssistant() {
  const state = { tasks: [], date: todayIso(), log: [] };
  const status = $('#assistantStatus');
  const interim = $('#assistantInterim');
  const dialogHero = document.querySelector('.assistant-dialog-hero');
  const commandInput = $('#assistantCommand');
  const micButton = $('#assistantMicButton');
  const enabledToggle = $('#assistantEnabledToggle');
  const autoStartToggle = $('#assistantAutoStartToggle');
  const wakeWordSelect = $('#assistantWakeWord');
  const voiceLangSelect = $('#assistantVoiceLang');
  const nativeStatus = $('#assistantNativeStatus');
  const recognitionType = window.SpeechRecognition || window.webkitSpeechRecognition;
  let recognition = null;
  let listening = false;
  let pendingTranscript = '';
  let nativeReady = false;

  const renderLog = () => {
    const root = $('#assistantLog');
    if (!root) return;
    root.innerHTML = state.log.length ? state.log.map(item => `<div class="assistant-log-item ${item.role}"><span class="assistant-log-avatar">${item.role === 'user' ? 'Я' : '✦'}</span><div><small>${item.role === 'user' ? 'Ты' : 'Ассистент'}</small><p>${escapeHtml(item.text)}</p></div></div>`).join('') : '<div class="assistant-log-empty">Команды появятся здесь после первого обращения.</div>';
    root.scrollTop = root.scrollHeight;
  };

  const pushLog = (role, text) => { state.log.push({ role, text }); state.log = state.log.slice(-12); renderLog(); };

  const speak = text => {
    if (!$('#assistantSpeakToggle')?.checked || !('speechSynthesis' in window) || !window.SpeechSynthesisUtterance) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'ru-RU'; utterance.rate = .96; utterance.pitch = 1;
    const russianVoice = window.speechSynthesis.getVoices().find(voice => voice.lang?.toLocaleLowerCase().startsWith('ru'));
    if (russianVoice) utterance.voice = russianVoice;
    window.speechSynthesis.speak(utterance);
  };

  const answer = text => { pushLog('assistant', text); if (status) status.textContent = text; speak(text); };

  const renderAssistantSupport = settings => {
    const browserReady = Boolean(recognitionType);
    if (!enabledToggle?.checked) {
      $('#assistantSupportBadge').textContent = 'EVE выключена';
      return;
    }
    if (nativeReady && browserReady) $('#assistantSupportBadge').textContent = 'Голос доступен · EVE в фоне';
    else if (nativeReady) $('#assistantSupportBadge').textContent = 'EVE готова слушать в фоне';
    else if (browserReady) $('#assistantSupportBadge').textContent = 'Голосовой ввод доступен в окне';
    else $('#assistantSupportBadge').textContent = 'Нужен голосовой модуль или браузерный ввод';
    if (settings?.voice_lang && recognition) recognition.lang = settings.voice_lang;
  };

  const loadAssistantSettings = async () => {
    try {
      const [statusResult, settingsResult] = await Promise.all([
        api('/api/assistant/status'),
        api('/api/assistant/settings'),
      ]);
      const settings = settingsResult.settings || {};
      const native = statusResult.assistant?.native || {};
      nativeReady = Boolean(native.ready);
      if (enabledToggle) enabledToggle.checked = Boolean(settings.enabled);
      if (autoStartToggle) autoStartToggle.checked = Boolean(settings.auto_start);
      if (wakeWordSelect) wakeWordSelect.value = settings.wake_word || 'эва';
      if (voiceLangSelect) voiceLangSelect.value = settings.voice_lang || 'ru-RU';
      if (nativeStatus) nativeStatus.textContent = nativeReady
        ? 'Локальный модуль EVE готов. Микрофон не записывается на диск.'
        : `${native.message || 'Локальный модуль пока не готов.'} Браузерный ввод остаётся доступен.`;
      renderAssistantSupport(settings);
      return settings;
    } catch (error) {
      if (nativeStatus) nativeStatus.textContent = 'Не удалось проверить локальный голосовой модуль. Ручной ввод доступен.';
      renderAssistantSupport();
      return null;
    }
  };

  const saveAssistantSetting = async (key, value) => {
    try {
      const result = await api('/api/assistant/settings', { method: 'PATCH', body: JSON.stringify({ [key]: value }) });
      if (key === 'auto_start' && result.autostart && !result.autostart.supported) showToast(result.autostart.message || 'Автозапуск для этой системы недоступен', true);
      else showToast(key === 'auto_start' ? 'Автозапуск EVE сохранён' : 'Настройка EVE сохранена');
      renderAssistantSupport(result.settings);
    } catch (error) {
      showToast(error.message, true);
      await loadAssistantSettings();
    }
  };

  const renderPlan = () => {
    const list = $('#assistantPlanList');
    const done = state.tasks.filter(task => task.done).length;
    $('#assistantTodayLabel').textContent = assistantDayLabel(state.date);
    $('#assistantTotalCount').textContent = state.tasks.length;
    $('#assistantOpenCount').textContent = state.tasks.length - done;
    $('#assistantDoneCount').textContent = done;
    if (!list) return;
    list.innerHTML = state.tasks.length ? state.tasks.map(task => `<article class="assistant-plan-item ${task.done ? 'done' : ''}"><button type="button" class="assistant-plan-check" data-assistant-toggle="${task.id}" aria-label="${task.done ? 'Вернуть задачу в работу' : 'Отметить выполненной'}">${task.done ? '✓' : ''}</button><div><strong>${escapeHtml(task.text)}</strong><small>${taskTime(task) ? escapeHtml(taskTime(task)) : 'Без времени'} · ${escapeHtml(task.section || 'Личное')}</small></div></article>`).join('') : '<div class="assistant-plan-empty">На этот день задач нет. Можно добавить первую голосом.</div>';
    $$('[data-assistant-toggle]', list).forEach(button => button.addEventListener('click', async () => {
      const task = state.tasks.find(item => item.id === Number(button.dataset.assistantToggle));
      if (!task) return;
      try { await api(`/api/tasks/${task.id}`, { method: 'PATCH', body: JSON.stringify({ done: !task.done }) }); announceDataChange('tasks'); await load(); } catch (error) { answer(error.message); }
    }));
  };

  const load = async (dateKey = state.date) => {
    state.date = dateKey;
    const result = await api(`/api/tasks?scope=planner&start=${dateKey}&end=${dateKey}`);
    state.tasks = result.tasks || [];
    renderPlan();
  };

  const listDay = async dateKey => {
    await load(dateKey);
    const open = state.tasks.filter(task => !task.done);
    const done = state.tasks.length - open.length;
    if (!state.tasks.length) return `${assistantDayLabel(dateKey)} свободен. Задач нет.`;
    const preview = state.tasks.slice(0, 5).map((task, index) => `${index + 1}. ${task.text}${task.done ? ' — выполнено' : ''}`).join('. ');
    return `${assistantDayLabel(dateKey)}: ${state.tasks.length} задач. ${preview}${open.length ? ` Выполнено ${done}, осталось ${open.length}.` : ' Всё выполнено.'}`;
  };

  const findPlannerTask = async query => {
    const result = await api('/api/tasks?scope=planner');
    const normalizedQuery = assistantNormalize(query).replace(/\s+(?:как\s+)?(?:выполненной|выполненным|выполнено|сделанной|готовой)$/i, '').trim();
    if (!normalizedQuery) return null;
    return (result.tasks || []).filter(task => !task.done).find(task => {
      const taskText = assistantNormalize(task.text);
      return taskText.includes(normalizedQuery) || normalizedQuery.includes(taskText);
    }) || null;
  };

  const execute = async (rawCommand, source = 'web') => {
    const raw = String(rawCommand || '').trim();
    if (!raw) return;
    if (listening && recognition) {
      pendingTranscript = '';
      recognition.stop();
    }
    pushLog('user', raw);
    commandInput.value = '';
    interim.textContent = raw;
    if (status) status.textContent = 'Обрабатываю команду…';
    try {
      const result = await api('/api/assistant/command', { method: 'POST', body: JSON.stringify({ text: raw, source }) });
      if (result.action === 'open_planner') {
        answer(result.reply || 'Открываю недельный планер.');
        window.setTimeout(() => { window.location.href = result.target || '/week'; }, 420);
        return;
      }
      if (result.date) await load(result.date);
      else if (result.task?.task_date) await load(result.task.task_date);
      else await load(state.date);
      announceDataChange('tasks');
      answer(result.reply || 'Команда выполнена.');
    } catch (error) {
      answer(error.message || 'Не получилось выполнить команду.');
    }
  };

  if (recognitionType) {
    recognition = new recognitionType();
    recognition.lang = 'ru-RU'; recognition.interimResults = true; recognition.continuous = false; recognition.maxAlternatives = 1;
    recognition.onstart = () => { listening = true; pendingTranscript = ''; micButton?.classList.add('listening'); micButton?.setAttribute('aria-pressed', 'true'); status.textContent = 'Слушаю…'; interim.textContent = 'Говори, я записываю команду.'; };
    recognition.onresult = event => {
      let finalText = ''; let interimText = '';
      for (let index = event.resultIndex; index < event.results.length; index += 1) { const phrase = event.results[index][0]?.transcript || ''; if (event.results[index].isFinal) finalText += phrase; else interimText += phrase; }
      if (interimText) interim.textContent = interimText;
      if (finalText.trim()) { pendingTranscript = finalText.trim(); interim.textContent = pendingTranscript; }
    };
    recognition.onerror = event => { listening = false; micButton?.classList.remove('listening'); micButton?.setAttribute('aria-pressed', 'false'); status.textContent = event.error === 'not-allowed' ? 'Микрофон заблокирован. Разреши доступ к микрофону в настройках приложения.' : 'Не удалось распознать голос. Попробуй ещё раз.'; };
    recognition.onend = () => { listening = false; micButton?.classList.remove('listening'); micButton?.setAttribute('aria-pressed', 'false'); if (pendingTranscript) { const transcript = pendingTranscript; pendingTranscript = ''; execute(transcript); } else if (status.textContent === 'Слушаю…') status.textContent = 'Команда не услышана. Попробуй ещё раз.'; };
    $('#assistantSupportBadge').textContent = 'Проверяю голосовой ввод…';
  } else {
    $('#assistantSupportBadge').textContent = 'Проверяю голосовой модуль…';
    status.textContent = 'В этом окне голосовой ввод недоступен, но команды можно написать вручную.';
    micButton?.setAttribute('disabled', 'disabled');
  }

  micButton?.addEventListener('click', () => { if (!recognition) return; if (listening) recognition.stop(); else { pendingTranscript = ''; try { recognition.start(); } catch (error) { status.textContent = 'Микрофон уже включён. Скажи команду.'; } } });
  $('#assistantSend')?.addEventListener('click', () => execute(commandInput.value));
  commandInput?.addEventListener('keydown', event => { if (event.key === 'Enter') { event.preventDefault(); execute(commandInput.value); } });
  $('#assistantStopSpeech')?.addEventListener('click', () => window.speechSynthesis?.cancel());
  $('#assistantClearLog')?.addEventListener('click', () => { state.log = []; renderLog(); });
  $('#assistantOpenPlanner')?.addEventListener('click', () => { window.location.href = '/week'; });
  enabledToggle?.addEventListener('change', () => { renderAssistantSupport(); saveAssistantSetting('enabled', enabledToggle.checked); });
  autoStartToggle?.addEventListener('change', () => saveAssistantSetting('auto_start', autoStartToggle.checked));
  wakeWordSelect?.addEventListener('change', () => saveAssistantSetting('wake_word', wakeWordSelect.value));
  voiceLangSelect?.addEventListener('change', () => { if (recognition) recognition.lang = voiceLangSelect.value; saveAssistantSetting('voice_lang', voiceLangSelect.value); });
  window.speechSynthesis?.addEventListener('voiceschanged', () => window.speechSynthesis.getVoices());
  window.addEventListener('beforeunload', () => { if (listening) recognition?.stop(); window.speechSynthesis?.cancel(); }, { once: true });

  pageRefresh = load; window.refreshCurrentPage = load;
  await loadAssistantSettings();
  await load();
}

async function initAssistantChat() {
  const historyKey = 'reform-life.eve-chat.v1';
  const maxHistoryMessages = 2000;
  const state = { log: [], pendingConfirmation: null };
  const status = $('#assistantStatus');
  const interim = $('#assistantInterim');
  const voiceVisualizer = $('#assistantVoiceVisualizer');
  const voiceStatus = $('#assistantVoiceStatus');
  const voiceTitle = $('#assistantVoiceTitle');
  let voiceProcessing = 0;
  let microphoneLevel = 0;
  const settingsBackdrop = $('#assistantSettingsBackdrop');
  const settingsToggle = $('#assistantSettingsToggle');
  const settingsClose = $('#assistantSettingsClose');
  const commandInput = $('#assistantCommand');
  const micButton = $('#assistantMicButton');
  const enabledToggle = $('#assistantEnabledToggle');
  const autoStartToggle = $('#assistantAutoStartToggle');
  const wakeWordSelect = $('#assistantWakeWord');
  const voiceLangSelect = $('#assistantVoiceLang');
  const microphoneSelect = $('#assistantMicrophone');
  const geminiToggle = $('#assistantGeminiToggle');
  const localTtsToggle = $('#assistantLocalTtsToggle');
  const continuousDialogToggle = $('#assistantContinuousDialogToggle');
  const interruptToggle = $('#assistantInterruptToggle');
  const personalizationToggle = $('#assistantPersonalizationToggle');
  const speechProviderSelect = $('#assistantSpeechProvider');
  const speechKitStatus = $('#assistantSpeechKitStatus');
  const voiceSelect = $('#assistantVoiceName');
  const nativeStatus = $('#assistantNativeStatus');
  const geminiStatus = $('#assistantGeminiStatus');
  const recognitionType = window.SpeechRecognition || window.webkitSpeechRecognition;
  const localCaptureSupported = Boolean(navigator.mediaDevices?.getUserMedia && (window.AudioContext || window.webkitAudioContext));
  let recognition = null;
  let listening = false;
  let pendingTranscript = '';
  let nativeReady = false;
  let localTtsReady = false;
  let localTtsAudio = null;
  let localTtsUrl = null;
  let speechRequestId = 0;
  let speechResolve = null;
  let conversationActive = false;
  let conversationStartTimer = null;
  let conversationExpiryTimer = null;
  let conversationDeadline = 0;
  let continuousDialogEnabled = true;
  let interruptResponsesEnabled = false;
  let pendingAlternatives = [];
  let localCaptureStop = null;
  let lastVoiceCommand = '';
  let lastVoiceCommandAt = 0;
  let lastSubmittedText = '';
  let lastSubmittedAt = 0;
  let lastReplyText = '';
  let lastReplyAt = 0;

  const voiceWakePattern = /^\s*(?:эва|ева|eve)(?=\s|$|[,.:;!?—-])\s*(?:[,.:;!?—-]\s*)?/iu;
  const normalizeCommandKey = value => String(value || '')
    .toLocaleLowerCase('ru-RU')
    .replace(/ё/g, 'е')
    .replace(/[^\p{L}\p{N}]+/gu, ' ')
    .trim();
  const cleanAssistantText = value => {
    const original = String(value || '').trim();
    if (!original) return '';
    const cleaned = original.replace(/^(?:(?:эва|ева|eve)\s*[,.:;!?—-]?\s*)+/iu, '').trim();
    return cleaned || original;
  };
  const extractVoiceCommand = (primary, alternatives = []) => {
    const candidates = [primary, ...(Array.isArray(alternatives) ? alternatives : [])]
      .map(item => String(item || '').trim())
      .filter(Boolean);
    let wakeOnly = null;
    for (const candidate of candidates) {
      const match = candidate.match(voiceWakePattern);
      if (!match) continue;
      const command = candidate.slice(match[0].length).trim();
      if (command) return { accepted: true, command, sourceText: candidate };
      wakeOnly = { accepted: true, command: '', sourceText: candidate };
    }
    return wakeOnly || { accepted: false, command: '', sourceText: '' };
  };

  try {
    const stored = JSON.parse(window.localStorage.getItem(historyKey) || '[]');
    if (Array.isArray(stored)) state.log = stored
      .filter(item => item && ['user', 'assistant'].includes(item.role) && item.text)
      .map(item => ({ role: item.role, text: item.role === 'assistant' ? cleanAssistantText(item.text) : String(item.text).trim() }))
      .filter(item => item.text)
      .slice(-maxHistoryMessages);
  } catch (_error) {
    state.log = [];
  }

  const saveLog = () => {
    try { window.localStorage.setItem(historyKey, JSON.stringify(state.log.slice(-maxHistoryMessages))); } catch (_error) { /* storage is optional */ }
  };

  const setSettingsOpen = open => {
    if (!settingsBackdrop) return;
    settingsBackdrop.hidden = !open;
    settingsBackdrop.classList.toggle('open', open);
    settingsBackdrop.setAttribute('aria-hidden', String(!open));
    settingsToggle?.setAttribute('aria-expanded', String(open));
    if (open) settingsClose?.focus();
    else settingsToggle?.focus();
  };

  const wavePath = $('#assistantWavePath');
  const waveReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  let waveMode = 'idle';
  let waveFrame = 0;
  let waveLastPaint = 0;
  const paintVoiceWave = time => {
    if (!wavePath) return;
    const moving = !waveReducedMotion.matches;
    const phase = moving ? time / 1000 : 0;
    const amplitude = waveMode === 'off' ? .025
      : waveMode === 'listening' ? .25 + microphoneLevel * .75
      : waveMode === 'speaking' ? .72 + Math.sin(phase * 4) * .18
      : waveMode === 'processing' ? .45 + Math.sin(phase * 1.8) * .08
      : waveMode === 'confirmation' ? .65 : .6;
    const points = Array.from({ length: 51 }, (_, index) => {
      const x = index / 50;
      const envelope = Math.sin(Math.PI * x);
      const peaks = .55 + .27 * Math.sin(x * Math.PI * 6 + (['speaking', 'processing'].includes(waveMode) ? phase * 1.3 : 0));
      return [x * 1000, 119 - envelope * (26 + peaks * 85) * amplitude];
    });
    let path = `M0 ${points[0][1].toFixed(2)}`;
    for (let index = 1; index < points.length - 1; index += 1) {
      const [x, y] = points[index];
      const next = points[index + 1];
      path += ` Q${x.toFixed(2)} ${y.toFixed(2)} ${((x + next[0]) / 2).toFixed(2)} ${((y + next[1]) / 2).toFixed(2)}`;
    }
    path += ' L1000 119 L1000 120 L0 120 Z';
    wavePath.setAttribute('d', path);
  };
  const animateVoiceWave = time => {
    waveFrame = 0;
    if (time - waveLastPaint >= 32) { paintVoiceWave(time); waveLastPaint = time; }
    if (!waveReducedMotion.matches && ['listening', 'speaking', 'processing'].includes(waveMode)) waveFrame = window.requestAnimationFrame(animateVoiceWave);
  };
  const updateWaveState = mode => {
    waveMode = mode;
    window.cancelAnimationFrame(waveFrame);
    waveFrame = 0;
    paintVoiceWave(performance.now());
    if (!waveReducedMotion.matches && ['listening', 'speaking', 'processing'].includes(mode)) waveFrame = window.requestAnimationFrame(animateVoiceWave);
  };
  waveReducedMotion.addEventListener('change', () => updateWaveState(waveMode));
  window.addEventListener('pagehide', () => window.cancelAnimationFrame(waveFrame), { once: true });

  const renderVoiceState = () => {
    const mode = !enabledToggle?.checked ? 'off'
      : voiceVisualizer?.classList.contains('is-speaking') ? 'speaking'
      : voiceProcessing ? 'processing'
      : state.pendingConfirmation ? 'confirmation'
      : listening ? 'listening' : 'idle';
    const labels = {
      off: ['EVE выключена', 'Включи EVE в настройках'],
      speaking: ['Отвечаю', 'Эва отвечает голосом'],
      processing: ['Думаю', 'Разбираюсь с твоим запросом…'],
      confirmation: ['Твоё решение', 'Проверь изменения в чате и подтверди действие'],
      listening: ['Слушаю тебя', 'Скажи «Эва» и команду'],
      idle: ['Я рядом', conversationActive ? 'Готова продолжить разговор' : 'Скажи «Эва» и команду'],
    };
    if (voiceVisualizer) voiceVisualizer.dataset.voiceState = mode;
    updateWaveState(mode);
    if (voiceTitle) voiceTitle.textContent = labels[mode][0];
    if (voiceStatus) voiceStatus.textContent = labels[mode][1];
  };

  const withVoiceProcessing = async operation => {
    voiceProcessing += 1;
    renderVoiceState();
    try { return await operation(); }
    finally { voiceProcessing -= 1; renderVoiceState(); }
  };

  const setSpeakingState = active => {
    voiceVisualizer?.classList.toggle('is-speaking', active);
    renderVoiceState();
  };

  const renderLog = () => {
    const root = $('#assistantLog');
    if (!root) return;
    const historyMarkup = state.log.length
      ? state.log.map(item => `<div class="assistant-log-item ${item.role}"><span class="assistant-log-avatar">${item.role === 'user' ? 'Я' : '✦'}</span><div><small>${item.role === 'user' ? 'Ты' : 'Эва'}</small><p>${escapeHtml(item.role === 'assistant' ? cleanAssistantText(item.text) : item.text)}</p></div></div>`).join('')
      : '<div class="assistant-log-empty">Здесь появится история ваших сообщений и ответов Эвы.</div>';
    const confirmationMarkup = state.pendingConfirmation
      ? `<div class="assistant-confirm-card" role="alert"><div><small>ТРЕБУЕТСЯ ПОДТВЕРЖДЕНИЕ</small><p>${escapeHtml(state.pendingConfirmation.label || 'Действие').replace(/\n/g, '<br>')}</p></div><div class="assistant-confirm-actions"><button class="button primary small" data-assistant-confirm="approve" type="button">Подтвердить</button><button class="button ghost small" data-assistant-confirm="cancel" type="button">Отмена</button></div><span>Можно также сказать: «Эва, подтверждаю».</span></div>`
      : '';
    root.innerHTML = historyMarkup + confirmationMarkup;
    root.querySelector('[data-assistant-confirm="approve"]')?.addEventListener('click', () => confirmPending(true));
    root.querySelector('[data-assistant-confirm="cancel"]')?.addEventListener('click', () => confirmPending(false));
    root.scrollTop = root.scrollHeight;
    renderVoiceState();
  };

  const pushLog = (role, text) => {
    const safeText = role === 'assistant' ? cleanAssistantText(text) : String(text || '').trim();
    if (!safeText) return;
    state.log.push({ role, text: safeText });
    state.log = state.log.slice(-maxHistoryMessages);
    saveLog();
    renderLog();
  };

  const resizeComposer = () => {
    if (!commandInput) return;
    commandInput.style.height = 'auto';
    commandInput.style.height = `${Math.min(Math.max(commandInput.scrollHeight, 44), 132)}px`;
  };

  const stopSpeech = () => {
    speechRequestId += 1;
    setSpeakingState(false);
    if (speechResolve) {
      const resolve = speechResolve;
      speechResolve = null;
      resolve(false);
    }
    window.speechSynthesis?.cancel();
    if (localTtsAudio) {
      localTtsAudio.pause();
      localTtsAudio.currentTime = 0;
      localTtsAudio = null;
    }
    if (localTtsUrl) {
      URL.revokeObjectURL(localTtsUrl);
      localTtsUrl = null;
    }
  };

  const speakWithBrowserVoice = text => {
    if (!('speechSynthesis' in window) || !window.SpeechSynthesisUtterance) return false;
    try {
      window.speechSynthesis.cancel();
      const requestId = speechRequestId;
      const utterance = new SpeechSynthesisUtterance(String(text || ''));
      utterance.lang = voiceLangSelect?.value || 'ru-RU';
      utterance.rate = .96;
      utterance.pitch = 1;
      const preferredPrefix = utterance.lang.toLocaleLowerCase().split('-')[0];
      const systemVoice = window.speechSynthesis.getVoices().find(voice => voice.lang?.toLocaleLowerCase().startsWith(preferredPrefix));
      if (systemVoice) utterance.voice = systemVoice;
      const finish = () => { if (requestId === speechRequestId) setSpeakingState(false); };
      utterance.onstart = () => { if (requestId === speechRequestId) setSpeakingState(true); };
      utterance.onend = finish;
      utterance.onerror = finish;
      window.speechSynthesis.resume?.();
      setSpeakingState(true);
      window.speechSynthesis.speak(utterance);
      return true;
    } catch (_error) {
      return false;
    }
  };

  const speak = async text => {
    const speechText = cleanAssistantText(text);
    if (!speechText) return false;
    if (!$('#assistantSpeakToggle')?.checked) {
      stopSpeech();
      return false;
    }
    stopSpeech();
    const requestId = speechRequestId;
    if (localTtsReady) {
      try {
        const response = await fetch('/api/assistant/tts', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: speechText }),
        });
        if (!response.ok) throw new Error('Локальный голос недоступен');
        const blob = await response.blob();
        if (requestId !== speechRequestId) return;
        localTtsUrl = URL.createObjectURL(blob);
        localTtsAudio = new Audio(localTtsUrl);
        const playback = new Promise(resolve => {
          speechResolve = resolve;
          const finish = success => {
            speechResolve = null;
            if (localTtsUrl) URL.revokeObjectURL(localTtsUrl);
            localTtsUrl = null;
            localTtsAudio = null;
            setSpeakingState(false);
            resolve(success);
          };
          localTtsAudio.onended = () => finish(true);
          localTtsAudio.onerror = () => finish(false);
        });
        setSpeakingState(true);
        await localTtsAudio.play();
        if (await playback) return true;
        localTtsReady = false;
      } catch (_error) {
        if (requestId !== speechRequestId) return;
        localTtsReady = false;
        if (speechResolve) {
          const resolve = speechResolve;
          speechResolve = null;
          resolve(false);
        }
        if (localTtsAudio) {
          localTtsAudio.pause();
          localTtsAudio = null;
        }
        if (localTtsUrl) {
          URL.revokeObjectURL(localTtsUrl);
          localTtsUrl = null;
        }
        setSpeakingState(false);
      }
    }
    // Keep answers audible when a portable build is missing its optional
    // local model or the local audio endpoint cannot play in the webview.
    return speakWithBrowserVoice(speechText);
  };

  const answer = text => {
    const reply = cleanAssistantText(text);
    if (!reply) return false;
    const replyKey = normalizeCommandKey(reply);
    const now = Date.now();
    if (replyKey && replyKey === lastReplyText && now - lastReplyAt < 1500) return false;
    lastReplyText = replyKey;
    lastReplyAt = now;
    pushLog('assistant', reply);
    if (status) status.textContent = reply;
    const playback = speak(reply);
    if (conversationActive && interruptResponsesEnabled) startConversationListening(120);
    return playback;
  };

  const updateConversationUi = () => {
    const badge = $('#assistantSupportBadge');
    if (!badge) return;
    voiceVisualizer?.classList.toggle('is-listening', listening);
    renderVoiceState();
    if (conversationActive) {
      badge.textContent = listening ? 'EVE слушает · разговор активен' : 'Разговор активен · EVE отвечает';
      micButton?.classList.add('listening');
      micButton?.setAttribute('aria-pressed', 'true');
      micButton?.setAttribute('aria-label', 'Завершить разговор с EVE');
    } else {
      micButton?.classList.remove('listening');
      micButton?.setAttribute('aria-pressed', 'false');
      micButton?.setAttribute('aria-label', 'Начать разговор с EVE');
    }
  };

  const finishConversation = message => {
    conversationActive = false;
    conversationDeadline = 0;
    window.clearTimeout(conversationStartTimer);
    window.clearTimeout(conversationExpiryTimer);
    if (listening) recognition?.stop();
    if (listening && localCaptureStop) localCaptureStop(false);
    if (message && status) status.textContent = message;
    updateConversationUi();
  };

  const armConversationWindow = () => {
    conversationDeadline = Date.now() + 20000;
    window.clearTimeout(conversationExpiryTimer);
    conversationExpiryTimer = window.setTimeout(() => {
      if (conversationActive) finishConversation('Диалог завершён после паузы. Скажи «Эва» или нажми микрофон, чтобы продолжить.');
    }, 20000);
  };

  const startConversationListening = (delay = 500) => {
    window.clearTimeout(conversationStartTimer);
    if (!conversationActive || (!recognition && !localCaptureSupported) || !enabledToggle?.checked) return;
    if (conversationDeadline && Date.now() >= conversationDeadline) {
      finishConversation('Диалог завершён после паузы. Нажми на микрофон, чтобы продолжить.');
      return;
    }
    conversationStartTimer = window.setTimeout(() => {
      if (!conversationActive || listening) return;
      if (localCaptureSupported) {
        startLocalCapture();
        return;
      }
      pendingTranscript = '';
      try { recognition.start(); } catch (_error) { /* An active browser session will restart on its end. */ }
    }, delay);
  };

  const resumeConversation = () => {
    if (!conversationActive) return;
    if (!continuousDialogEnabled) {
      finishConversation('Ответ готов. Нажми на микрофон для следующего вопроса.');
      return;
    }
    armConversationWindow();
    startConversationListening();
  };

  const confirmPending = async approved => {
    const pending = state.pendingConfirmation;
    if (!pending) return;
    state.pendingConfirmation = null;
    renderLog();
    if (status) status.textContent = approved ? 'Проверяю подтверждение…' : 'Отменяю действие…';
    try {
      const result = await withVoiceProcessing(() => api('/api/assistant/confirm', {
        method: 'POST',
        body: JSON.stringify({ confirmation_id: pending.id, approved }),
      }));
      await answer(result.reply || (approved ? 'Действие выполнено.' : 'Команда отменена.'));
      if (['savings_operation', 'meter_reading', 'meter_submission'].includes(result.action)) announceDataChange('finance');
      if (result.action === 'task_changes') announceDataChange('tasks');
      if (result.action === 'create_folder') announceDataChange('assistant');
    } catch (error) {
      await answer(error.message || 'Не удалось обработать подтверждение.');
    }
  };

  const renderAssistantSupport = settings => {
    const browserReady = Boolean(recognitionType || localCaptureSupported);
    const enabled = Boolean(enabledToggle?.checked);
    renderVoiceState();
    if (micButton) micButton.disabled = !enabled || !browserReady;
    if (!enabled) {
      $('#assistantSupportBadge').textContent = 'EVE выключена';
      return;
    }
    if (nativeReady && browserReady) $('#assistantSupportBadge').textContent = 'Голос доступен · EVE в фоне';
    else if (nativeReady) $('#assistantSupportBadge').textContent = 'EVE готова слушать в фоне';
    else if (browserReady) $('#assistantSupportBadge').textContent = 'Голосовой ввод доступен в окне';
    else $('#assistantSupportBadge').textContent = 'Нужен голосовой модуль или браузерный ввод';
    if (settings?.voice_lang && recognition) recognition.lang = settings.voice_lang;
  };

  const loadAssistantSettings = async () => {
    try {
      const [statusResult, settingsResult] = await Promise.all([api('/api/assistant/status'), api('/api/assistant/settings')]);
      const settings = settingsResult.settings || {};
      const native = statusResult.assistant?.native || {};
      const gemini = statusResult.assistant?.gemini || {};
      const tts = statusResult.assistant?.tts || {};
      const speechkit = statusResult.assistant?.speechkit || {};
      const useSpeechKit = settings.speech_provider === 'yandex';
      const voices = useSpeechKit ? speechkit.voices : tts.voices;
      const availableVoices = Array.isArray(voices) ? voices : [];
      const microphones = Array.isArray(statusResult.assistant?.microphones) ? statusResult.assistant.microphones : [];
      nativeReady = Boolean(native.ready);
      localTtsReady = Boolean(settings.local_tts_enabled && (useSpeechKit ? speechkit.ready : tts.ready));
      if (enabledToggle) enabledToggle.checked = Boolean(settings.enabled);
      if (autoStartToggle) autoStartToggle.checked = Boolean(settings.auto_start);
      if (wakeWordSelect) wakeWordSelect.value = settings.wake_word || 'эва';
      if (voiceLangSelect) voiceLangSelect.value = settings.voice_lang || 'ru-RU';
      if (microphoneSelect) {
        microphoneSelect.replaceChildren(new Option('Системный по умолчанию', ''), ...microphones.map(item => {
          const option = new Option(item.name, item.id);
          option.dataset.deviceName = item.name;
          return option;
        }));
        microphoneSelect.value = settings.microphone_device || '';
      }
      if (geminiToggle) geminiToggle.checked = settings.gemini_enabled !== false;
      if (localTtsToggle) localTtsToggle.checked = Boolean(settings.local_tts_enabled);
      continuousDialogEnabled = settings.continuous_dialog !== false;
      interruptResponsesEnabled = Boolean(settings.interrupt_responses);
      if (continuousDialogToggle) continuousDialogToggle.checked = continuousDialogEnabled;
      if (interruptToggle) interruptToggle.checked = interruptResponsesEnabled;
      if (personalizationToggle) personalizationToggle.checked = settings.personalization_enabled !== false;
      if (speechProviderSelect) speechProviderSelect.value = settings.speech_provider || 'local';
      if (speechKitStatus) speechKitStatus.textContent = speechkit.message || 'SpeechKit недоступен.';
      if (voiceSelect && availableVoices.length) {
        voiceSelect.replaceChildren(...availableVoices.map(voice => {
          const option = document.createElement('option');
          option.value = voice.id;
          option.textContent = voice.name;
          return option;
        }));
        voiceSelect.value = useSpeechKit ? (settings.yandex_voice || availableVoices[0].id) : (statusResult.assistant?.voice_name || settings.voice_name || availableVoices[0].id);
        voiceSelect.disabled = availableVoices.length < 2;
      }
      if (nativeStatus) nativeStatus.textContent = nativeReady
        ? 'Локальный модуль EVE готов. Микрофон не записывается на диск.'
        : `${native.message || 'Локальный модуль пока не готов.'} Браузерный ввод остаётся доступен.`;
      if (geminiStatus) {
        const modelText = gemini.ready
          ? `Gemini ${gemini.model || settings.gemini_model || ''} готова.`
          : `Gemini: ${gemini.message || 'ключ не настроен'}`;
        const ttsText = tts.ready
          ? `${tts.engine || tts.backend} готов · ${tts.device || 'локально'} · лицензия ${tts.license || 'не указана'}.`
          : `${tts.engine || 'Локальный голос'}: ${tts.message || 'модель не найдена'}`;
        geminiStatus.textContent = `${modelText} ${useSpeechKit ? speechkit.message : ttsText}`;
      }
      renderAssistantSupport(settings);
    } catch (_error) {
      if (nativeStatus) nativeStatus.textContent = 'Не удалось проверить локальный голосовой модуль. Ручной ввод доступен.';
      if (geminiStatus) geminiStatus.textContent = 'Не удалось проверить Gemini. Проверь GEMINI_API_KEY.';
      renderAssistantSupport();
    }
  };

  const loadAssistantHistory = async () => {
    try {
      const result = await api(`/api/assistant/history?limit=${maxHistoryMessages}`);
      const pending = await api('/api/assistant/proposals/pending');
      state.pendingConfirmation = pending.proposal || null;
      const messages = Array.isArray(result.messages) ? result.messages : [];
      if (messages.length) {
        state.log = messages
          .filter(item => item && ['user', 'assistant'].includes(item.role) && item.text)
          .map(item => ({ role: item.role, text: item.role === 'assistant' ? cleanAssistantText(item.text) : String(item.text).trim() }))
          .filter(item => item.text)
          .slice(-maxHistoryMessages);
        saveLog();
        renderLog();
      }
    } catch (_error) {
      // Local storage remains a fallback when the database is unavailable.
    }
  };

  const saveAssistantSetting = async (key, value) => {
    try {
      const result = await api('/api/assistant/settings', { method: 'PATCH', body: JSON.stringify({ [key]: value }) });
      if (key === 'auto_start' && result.autostart && !result.autostart.supported) showToast(result.autostart.message || 'Автозапуск для этой системы недоступен', true);
      else showToast(key === 'auto_start' ? 'Автозапуск EVE сохранён' : 'Настройка EVE сохранена');
      if (key === 'local_tts_enabled') {
        localTtsReady = Boolean(result.settings.local_tts_enabled) && localTtsReady;
        if (!result.settings.local_tts_enabled) stopSpeech();
      }
      if (key === 'continuous_dialog') continuousDialogEnabled = Boolean(result.settings.continuous_dialog);
      if (key === 'interrupt_responses') interruptResponsesEnabled = Boolean(result.settings.interrupt_responses);
      if (key === 'speech_provider' || key === 'yandex_voice') await loadAssistantSettings();
      renderAssistantSupport(result.settings);
    } catch (error) {
      showToast(error.message, true);
      await loadAssistantSettings();
    }
  };

  const execute = async (rawCommand, source = 'web', alternatives = []) => {
    const input = String(rawCommand || '').trim();
    if (!input) return;
    const requiresWakeWord = source === 'local_voice' || source === 'browser_voice';
    const voiceInput = requiresWakeWord ? extractVoiceCommand(input, alternatives) : { accepted: true, command: input, sourceText: input };
    if (!voiceInput.accepted) {
      if (interim) interim.textContent = 'Фраза без имени «Эва» пропущена.';
      if (status) status.textContent = conversationActive ? 'Жду: «Эва» и команда…' : 'Фраза пропущена. Скажи «Эва» перед командой.';
      if (conversationActive) {
        armConversationWindow();
        startConversationListening(120);
      }
      return;
    }
    const raw = voiceInput.command.trim();
    if (!raw) {
      if (interim) interim.textContent = 'Я услышала имя. Теперь скажи команду.';
      if (status) status.textContent = 'Скажи «Эва» и затем команду.';
      if (conversationActive) {
        armConversationWindow();
        startConversationListening(120);
      }
      return;
    }
    const apiText = requiresWakeWord ? voiceInput.sourceText : raw;
    const apiAlternatives = requiresWakeWord && Array.isArray(alternatives)
      ? alternatives.filter(item => extractVoiceCommand(item).accepted)
      : alternatives;
    const now = Date.now();
    const normalized = normalizeCommandKey(raw);
    const duplicateWindow = requiresWakeWord ? 8000 : 2200;
    if (normalized === lastSubmittedText && now - lastSubmittedAt < duplicateWindow) return;
    lastSubmittedText = normalized;
    lastSubmittedAt = now;
    if (source !== 'web') {
      if (normalized === lastVoiceCommand && now - lastVoiceCommandAt < 8000) return;
      lastVoiceCommand = normalized;
      lastVoiceCommandAt = now;
    }
    if (listening && recognition) {
      pendingTranscript = '';
      recognition.stop();
    }
    pushLog('user', raw);
    if (commandInput) { commandInput.value = ''; resizeComposer(); }
    if (interim) interim.textContent = raw;
    if (conversationActive && /^(?:стоп разговор|заверши разговор|хватит слушать|останови разговор)[.! ]*$/i.test(raw)) {
      finishConversation('Хорошо. Нажми на микрофон, когда захочешь продолжить.');
      await answer('Хорошо. Я завершаю разговор.');
      return;
    }
    if (status) status.textContent = 'Обрабатываю команду…';
    if (state.pendingConfirmation) {
      const normalized = raw.toLocaleLowerCase().replace(/[«».,!?]/g, '').trim();
      if (/^(?:да|подтверждаю|подтвердить|подтверждаю действие)$/.test(normalized)) {
        await confirmPending(true);
        resumeConversation();
        return;
      }
      if (/^(?:нет|отмена|отменяю|не надо)$/.test(normalized)) {
        await confirmPending(false);
        resumeConversation();
        return;
      }
    }
    try {
      const result = await withVoiceProcessing(() => api('/api/assistant/command', { method: 'POST', body: JSON.stringify({ text: apiText, source, alternatives: apiAlternatives }) }));
      if (result.action === 'ignored') {
        resumeConversation();
        return;
      }
      if (result.action === 'open_planner') {
        await answer(result.reply || 'Открываю недельный планер.');
        window.setTimeout(() => { window.location.href = result.target || '/week'; }, 420);
        return;
      }
      if (['create_task', 'complete_task', 'reschedule_task', 'task_changes'].includes(result.action)) announceDataChange('tasks');
      if (result.action === 'needs_confirmation') {
        state.pendingConfirmation = { id: result.confirmation_id, label: result.confirmation_label || result.reply };
        await answer(result.reply || 'Подтверди действие.');
        renderLog();
        resumeConversation();
        return;
      }
      await answer(result.reply || 'Команда выполнена.');
      if (['remember_fact', 'forget_fact', 'list_memories'].includes(result.action)) await loadMemoryStatus();
    } catch (error) {
      await answer(error.message || 'Не получилось выполнить команду.');
    }
    resumeConversation();
  };

  const loadMemoryStatus = async () => {
    const memoryStatus = $('#assistantMemoryStatus');
    if (!memoryStatus) return;
    try {
      const result = await api('/api/assistant/memories');
      const count = Array.isArray(result.memories) ? result.memories.length : 0;
      memoryStatus.textContent = count
        ? `EVE хранит локально фактов: ${count}. Скажи «Что ты помнишь обо мне?».`
        : 'Память пока пуста. Скажи: «Запомни, что…».';
    } catch (_error) {
      memoryStatus.textContent = 'Не удалось проверить персональную память.';
    }
  };

  const pcmBlob = (chunks, inputRate) => {
    const length = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
    const merged = new Float32Array(length);
    let offset = 0;
    chunks.forEach(chunk => { merged.set(chunk, offset); offset += chunk.length; });
    const ratio = inputRate / 16000;
    const output = new Int16Array(Math.max(1, Math.floor(merged.length / ratio)));
    for (let index = 0; index < output.length; index += 1) {
      const start = Math.floor(index * ratio);
      const end = Math.min(merged.length, Math.floor((index + 1) * ratio));
      let sum = 0;
      for (let source = start; source < end; source += 1) sum += merged[source];
      const value = Math.max(-1, Math.min(1, sum / Math.max(1, end - start)));
      output[index] = value < 0 ? value * 32768 : value * 32767;
    }
    return new Blob([output.buffer], { type: 'application/octet-stream' });
  };

  const startLocalCapture = async () => {
    if (!localCaptureSupported || listening) return;
    stopSpeech();
    const audioOptions = { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true };
    try {
      let stream = await navigator.mediaDevices.getUserMedia({ audio: audioOptions });
      const selectedName = microphoneSelect?.selectedOptions?.[0]?.dataset?.deviceName || '';
      if (selectedName) {
        const devices = await navigator.mediaDevices.enumerateDevices();
        const normalizedName = selectedName.toLocaleLowerCase();
        const selected = devices.find(item => item.kind === 'audioinput' && (item.label.toLocaleLowerCase() === normalizedName || item.label.toLocaleLowerCase().includes(normalizedName) || normalizedName.includes(item.label.toLocaleLowerCase())));
        if (selected?.deviceId) {
          stream.getTracks().forEach(track => track.stop());
          stream = await navigator.mediaDevices.getUserMedia({ audio: { ...audioOptions, deviceId: { exact: selected.deviceId } } });
        }
      }
      const AudioContextType = window.AudioContext || window.webkitAudioContext;
      const context = new AudioContextType();
      const source = context.createMediaStreamSource(stream);
      const processor = context.createScriptProcessor(4096, 1, 1);
      const chunks = [];
      let heardSpeech = false;
      let lastVoiceAt = performance.now();
      const captureStartedAt = lastVoiceAt;
      let stopped = false;
      listening = true;
      updateConversationUi();
      if (status) status.textContent = 'Слушаю выбранный микрофон…';
      if (interim) interim.textContent = 'Скажи «Эва» и команду. Фразы без имени будут пропущены.';
      const finish = async transcribe => {
        if (stopped) return;
        stopped = true;
        localCaptureStop = null;
        processor.disconnect(); source.disconnect(); stream.getTracks().forEach(track => track.stop());
        await context.close();
        microphoneLevel = 0;
        listening = false; updateConversationUi();
        if (!transcribe || !chunks.length) {
          if (conversationActive) finishConversation('Не услышала команду. Нажми на микрофон, чтобы попробовать ещё раз.');
          return;
        }
        if (status) status.textContent = 'Распознаю голос локально…';
        try {
          const response = await withVoiceProcessing(() => fetch('/api/assistant/transcribe?sample_rate=16000', { method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: pcmBlob(chunks, context.sampleRate) }));
          const result = await response.json();
          if (!response.ok) throw new Error(result.error || 'Не удалось распознать голос.');
          if (result.text) await execute(result.text, 'local_voice');
          else {
            if (status) status.textContent = 'Речь не распознана. Проверь выбранный микрофон и попробуй ещё раз.';
            if (conversationActive) finishConversation('Речь не распознана. Нажми на микрофон, чтобы попробовать ещё раз.');
          }
        } catch (error) {
          if (status) status.textContent = error.message || 'Не удалось распознать голос.';
        }
      };
      localCaptureStop = finish;
      processor.onaudioprocess = event => {
        const data = new Float32Array(event.inputBuffer.getChannelData(0));
        chunks.push(data);
        let energy = 0;
        for (let index = 0; index < data.length; index += 1) energy += data[index] * data[index];
        const rms = Math.sqrt(energy / data.length);
        microphoneLevel = microphoneLevel * .35 + Math.min(1, rms * 12) * .65;
        if (waveReducedMotion.matches) paintVoiceWave(performance.now());
        if (rms > 0.018) { heardSpeech = true; lastVoiceAt = performance.now(); }
        if (heardSpeech && performance.now() - lastVoiceAt > 1300) finish(true);
        else if (!heardSpeech && performance.now() - captureStartedAt > 4500) finish(false);
      };
      source.connect(processor); processor.connect(context.destination);
      window.setTimeout(() => finish(heardSpeech), 12000);
    } catch (error) {
      listening = false; updateConversationUi();
      if (status) status.textContent = error.name === 'NotAllowedError' ? 'Доступ к микрофону запрещён в Windows или настройках приложения.' : `Не удалось открыть выбранный микрофон: ${error.message}`;
    }
  };

  if (!localCaptureSupported && recognitionType) {
    recognition = new recognitionType();
    recognition.lang = 'ru-RU'; recognition.interimResults = true; recognition.continuous = false; recognition.maxAlternatives = 5;
    recognition.onstart = () => { listening = true; pendingTranscript = ''; pendingAlternatives = []; updateConversationUi(); if (status) status.textContent = 'Слушаю…'; if (interim) interim.textContent = 'Скажи «Эва» и команду — фразы без имени будут пропущены.'; };
    recognition.onresult = event => {
      let finalText = ''; let interimText = '';
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const phrase = event.results[index][0]?.transcript || '';
        if (event.results[index].isFinal) {
          finalText += phrase;
          pendingAlternatives = Array.from(event.results[index]).slice(1, 5).map(item => item?.transcript?.trim()).filter(Boolean);
        } else interimText += phrase;
      }
      if (interimText && interim) interim.textContent = interimText;
      if (finalText.trim()) { pendingTranscript = finalText.trim(); if (interim) interim.textContent = pendingTranscript; }
    };
    recognition.onerror = event => {
      listening = false;
      updateConversationUi();
      if (status) status.textContent = event.error === 'not-allowed' ? 'Микрофон заблокирован. Разреши доступ к микрофону в настройках приложения.' : 'Не удалось распознать голос. Попробуй ещё раз.';
      if (event.error === 'not-allowed') conversationActive = false;
    };
    recognition.onend = () => {
      listening = false;
      updateConversationUi();
      const transcript = pendingTranscript;
      const alternatives = pendingAlternatives;
      pendingTranscript = '';
      pendingAlternatives = [];
      if (transcript) execute(transcript, 'browser_voice', alternatives);
      else if (conversationActive) startConversationListening();
      else if (!conversationActive && status?.textContent === 'Слушаю…') status.textContent = 'Команда не услышана. Нажми на микрофон, чтобы начать разговор.';
    };
  } else {
    if ($('#assistantSupportBadge')) $('#assistantSupportBadge').textContent = 'Проверяю голосовой модуль…';
    if (status) status.textContent = 'В этом окне голосовой ввод недоступен, но команды можно написать вручную.';
  }

  micButton?.addEventListener('click', () => {
    if ((!recognition && !localCaptureSupported) || !enabledToggle?.checked) return;
    if (localCaptureSupported && listening && localCaptureStop) {
      localCaptureStop(true);
      return;
    }
    if (conversationActive) {
      finishConversation('Разговор завершён. Нажми на микрофон, чтобы продолжить.');
      stopSpeech();
      if (interim) interim.textContent = 'Эва готова к новой беседе.';
      return;
    }
    conversationActive = true;
    armConversationWindow();
    updateConversationUi();
    if (status) status.textContent = 'Разговор начался. Скажи, что у тебя на уме.';
    startConversationListening(0);
  });
  $('#assistantOrbitSettings')?.addEventListener('click', () => setSettingsOpen(true));
  $('#assistantOrbitCommands')?.addEventListener('click', () => {
    const library = $('#assistantCommandLibrary');
    if (!library) return;
    library.open = true;
    library.querySelector('summary')?.focus();
  });
  settingsToggle?.addEventListener('click', () => setSettingsOpen(true));
  settingsClose?.addEventListener('click', () => setSettingsOpen(false));
  settingsBackdrop?.addEventListener('click', event => { if (event.target === settingsBackdrop) setSettingsOpen(false); });
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && settingsBackdrop && !settingsBackdrop.hidden) setSettingsOpen(false); });
  $('#assistantSend')?.addEventListener('click', () => execute(commandInput?.value));
  $('#assistantComposerHelp')?.addEventListener('click', () => {
    if (interim) interim.textContent = 'Попробуй: «Помоги спланировать завтра по моим задачам», «Какие привычки я отметила сегодня?» или «Предложи перенос незавершённых дел». Изменения от ИИ появятся для подтверждения.';
    commandInput?.focus();
  });
  commandInput?.addEventListener('input', resizeComposer);
  commandInput?.addEventListener('keydown', event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); execute(commandInput.value); } });
  $('#assistantStopSpeech')?.addEventListener('click', () => {
    if (conversationActive) {
      finishConversation('Разговор завершён.');
    }
    stopSpeech();
  });
  $('#assistantClearLog')?.addEventListener('click', async () => {
    try {
      await api('/api/assistant/history', { method: 'DELETE' });
      state.log = [];
      state.pendingConfirmation = null;
      saveLog();
      renderLog();
      if (status) status.textContent = 'История очищена. Я готова к новой команде.';
    } catch (error) {
      if (status) status.textContent = error.message || 'Не удалось очистить историю.';
    }
  });
  enabledToggle?.addEventListener('change', () => {
    if (!enabledToggle.checked && conversationActive) {
      finishConversation('EVE выключена.');
      stopSpeech();
    }
    renderAssistantSupport();
    saveAssistantSetting('enabled', enabledToggle.checked);
  });
  autoStartToggle?.addEventListener('change', () => saveAssistantSetting('auto_start', autoStartToggle.checked));
  wakeWordSelect?.addEventListener('change', () => saveAssistantSetting('wake_word', wakeWordSelect.value));
  voiceLangSelect?.addEventListener('change', () => { if (recognition) recognition.lang = voiceLangSelect.value; saveAssistantSetting('voice_lang', voiceLangSelect.value); });
  microphoneSelect?.addEventListener('change', () => saveAssistantSetting('microphone_device', microphoneSelect.value));
  $('#assistantRefreshMicrophones')?.addEventListener('click', loadAssistantSettings);
  geminiToggle?.addEventListener('change', () => saveAssistantSetting('gemini_enabled', geminiToggle.checked));
  localTtsToggle?.addEventListener('change', () => saveAssistantSetting('local_tts_enabled', localTtsToggle.checked));
  continuousDialogToggle?.addEventListener('change', () => saveAssistantSetting('continuous_dialog', continuousDialogToggle.checked));
  interruptToggle?.addEventListener('change', () => saveAssistantSetting('interrupt_responses', interruptToggle.checked));
  personalizationToggle?.addEventListener('change', () => saveAssistantSetting('personalization_enabled', personalizationToggle.checked));
  speechProviderSelect?.addEventListener('change', () => saveAssistantSetting('speech_provider', speechProviderSelect.value));
  voiceSelect?.addEventListener('change', () => saveAssistantSetting(speechProviderSelect?.value === 'yandex' ? 'yandex_voice' : 'voice_name', voiceSelect.value));
  $('#assistantPreviewVoice')?.addEventListener('click', async () => {
    const button = $('#assistantPreviewVoice');
    const previewText = 'Привет. Рада тебя слышать.';
    button.disabled = true;
    try {
      const voice = voiceSelect?.value || (speechProviderSelect?.value === 'yandex' ? 'alena' : 'eve-suit');
      const response = await fetch('/api/assistant/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: previewText, voice }),
      });
      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.error || 'Локальный голос пока не готов.');
      }
      stopSpeech();
      localTtsUrl = URL.createObjectURL(await response.blob());
      localTtsAudio = new Audio(localTtsUrl);
      localTtsAudio.onended = () => { setSpeakingState(false); if (localTtsUrl) URL.revokeObjectURL(localTtsUrl); localTtsUrl = null; localTtsAudio = null; };
      localTtsAudio.onerror = () => { setSpeakingState(false); if (localTtsUrl) URL.revokeObjectURL(localTtsUrl); localTtsUrl = null; localTtsAudio = null; };
      setSpeakingState(true);
      await localTtsAudio.play();
    } catch (error) {
      if (speakWithBrowserVoice(previewText)) return;
      showToast(error.message || 'Не удалось воспроизвести образец голоса.', true);
    } finally {
      button.disabled = false;
    }
  });
  $('#assistantClearMemory')?.addEventListener('click', async () => {
    try {
      await api('/api/assistant/memories', { method: 'DELETE' });
      await loadMemoryStatus();
      await answer('Я очистила персональную память. История диалога осталась на месте.');
    } catch (error) {
      if (status) status.textContent = error.message || 'Не удалось очистить персональную память.';
    }
  });
  window.speechSynthesis?.addEventListener('voiceschanged', () => window.speechSynthesis.getVoices());
  window.addEventListener('beforeunload', () => { if (listening) recognition?.stop(); if (localCaptureStop) localCaptureStop(false); stopSpeech(); }, { once: true });

  pageRefresh = () => {};
  window.refreshCurrentPage = () => {};
  renderLog();
  resizeComposer();
  await loadAssistantHistory();
  await loadAssistantSettings();
  await loadMemoryStatus();
}

function plural(value, one, few, many) { const n = Math.abs(value) % 100; const last = n % 10; if (n > 10 && n < 20) return many; if (last > 1 && last < 5) return few; if (last === 1) return one; return many; }

async function initFinanceLegacy() {
  const state = { month: firstOfMonth(new Date()), transactions: [] };
  const load = async () => { state.transactions = (await api(`/api/finance/transactions?month=${monthKey(state.month)}`)).transactions; render(); };
  const render = () => {
    const filter = $('#financeFilter').value; const shown = filter === 'all' ? state.transactions : state.transactions.filter(item => item.kind === filter); const income = state.transactions.filter(item => item.kind === 'income').reduce((sum, item) => sum + item.amount_minor, 0); const expense = state.transactions.filter(item => item.kind === 'expense').reduce((sum, item) => sum + item.amount_minor, 0); $('#financeMonthTitle').textContent = `${MONTHS[state.month.getMonth()]} ${state.month.getFullYear()}`; $('#incomeTotal').textContent = formatMoney(income); $('#expenseTotal').textContent = formatMoney(expense); $('#balanceTotal').textContent = formatMoney(income - expense); $('#balanceTotal').style.color = income - expense >= 0 ? 'var(--green)' : 'var(--red)'; $('#financeOperationCount').textContent = `${state.transactions.length} ${plural(state.transactions.length, 'операция', 'операции', 'операций')}`;
    const totals = {}; state.transactions.filter(item => item.kind === 'expense').forEach(item => { totals[item.category] = (totals[item.category] || 0) + item.amount_minor; }); const categories = Object.entries(totals).sort((a, b) => b[1] - a[1]); const max = categories[0]?.[1] || 1; $('#categoryChart').innerHTML = categories.length ? categories.slice(0, 7).map(([category, value]) => `<div class="chart-row"><label>${escapeHtml(category)}</label><div class="chart-bar"><i style="width:${Math.round(value / max * 100)}%"></i></div><strong>${formatMoney(value)}</strong></div>`).join('') : '<div class="empty-state">Добавьте расходы, и здесь появится аналитика.</div>'; $('#categoryLegend').innerHTML = categories.length ? categories.slice(0, 7).map(([category, value]) => `<div class="legend-item"><span>${escapeHtml(category)}</span><strong>${formatMoney(value)}</strong></div>`).join('') : '<div class="empty-state">Пока нет категорий.</div>';
    activeTaskMap = new Map(); const body = $('#transactionsBody'); body.innerHTML = shown.length ? shown.map(item => `<tr><td>${formatShortDate(item.transaction_date)}</td><td><strong>${escapeHtml(item.category)}</strong></td><td class="muted-cell">${escapeHtml(item.comment || '—')}</td><td><span class="type-pill ${item.kind}">${item.kind === 'income' ? 'Доход' : 'Расход'}</span></td><td class="align-right" style="color:${item.kind === 'income' ? 'var(--green)' : 'var(--red)'}">${item.kind === 'income' ? '+' : '−'}${formatMoney(item.amount_minor)}</td><td><div class="row-actions"><button class="row-action" data-edit-transaction="${item.id}" type="button">✎</button><button class="row-action" data-delete-transaction="${item.id}" type="button">×</button></div></td></tr>`).join('') : '<tr><td colspan="6"><div class="empty-state">За выбранный месяц операций нет.</div></td></tr>';
    $$('[data-edit-transaction]', body).forEach(button => button.onclick = () => openTransactionModal(state.transactions.find(item => item.id === Number(button.dataset.editTransaction)))); $$('[data-delete-transaction]', body).forEach(button => button.onclick = async () => { if (!window.confirm('Удалить операцию?')) return; try { await api(`/api/finance/transactions/${button.dataset.deleteTransaction}`, { method: 'DELETE' }); await load(); } catch (error) { showToast(error.message, true); } });
  };
  function shiftMonth(amount) { state.month = new Date(state.month.getFullYear(), state.month.getMonth() + amount, 1); load(); }
  pageRefresh = load; window.refreshCurrentPage = load; $('#financePrev').onclick = () => shiftMonth(-1); $('#financeNext').onclick = () => shiftMonth(1); $('#financeToday').onclick = () => { state.month = firstOfMonth(new Date()); load(); }; $('#financeFilter').onchange = render; $('#addTransaction').onclick = () => openTransactionModal();
  $('#transactionForm').onsubmit = async event => { event.preventDefault(); const id = $('#transactionId').value; const amount = amountToMinor($('#transactionAmount').value); if (!amount) { showToast('Введите сумму больше нуля', true); return; } const payload = { kind: $('#transactionKind').value, amount_minor: amount, category: $('#transactionCategory').value.trim(), transaction_date: $('#transactionDate').value, comment: $('#transactionComment').value.trim() }; try { await api(id ? `/api/finance/transactions/${id}` : '/api/finance/transactions', { method: id ? 'PATCH' : 'POST', body: JSON.stringify(payload) }); closeModal('transactionModal'); showToast(id ? 'Операция обновлена' : 'Операция добавлена'); await load(); } catch (error) { showToast(error.message, true); } };
  await load();
}

function openTransactionModal(item = null) { $('#transactionModalTitle').textContent = item ? 'Редактировать операцию' : 'Новая операция'; $('#transactionId').value = item?.id || ''; $('#transactionKind').value = item?.kind || 'expense'; $('#transactionAmount').value = item ? (item.amount_minor / 100).toFixed(2).replace('.', ',') : ''; $('#transactionCategory').value = item?.category || ''; $('#transactionDate').value = item?.transaction_date || todayIso(); $('#transactionComment').value = item?.comment || ''; openModal('transactionModal'); setTimeout(() => $('#transactionAmount')?.focus(), 40); }

async function initUtilitiesLegacy() {
  const state = { month: firstOfMonth(new Date()), accounts: [], payments: [], accountFilter: 'all' };
  const filterSelect = $('#utilityApartmentFilter');

  const load = async () => {
    const [accounts, payments] = await Promise.all([
      api('/api/utilities/accounts'),
      api(`/api/utilities/payments?month=${monthKey(state.month)}`),
    ]);
    state.accounts = accounts.accounts || [];
    state.payments = payments.payments || [];
    if (!state.accounts.some(account => String(account.id) === String(state.accountFilter))) state.accountFilter = 'all';
    if (filterSelect) {
      filterSelect.innerHTML = '<option value="all">Все квартиры</option>' + state.accounts.map(account => `<option value="${account.id}">${escapeHtml(account.name)}</option>`).join('');
      filterSelect.value = state.accountFilter;
    }
    render();
  };

  const render = () => {
    const selectedAccount = state.accounts.find(account => String(account.id) === String(state.accountFilter));
    const visiblePayments = state.accountFilter === 'all'
      ? state.payments
      : state.payments.filter(payment => String(payment.account_id) === String(state.accountFilter));
    const due = visiblePayments.filter(item => item.status !== 'paid').reduce((sum, item) => sum + item.amount_minor, 0);
    const paid = visiblePayments.filter(item => item.status === 'paid').reduce((sum, item) => sum + item.amount_minor, 0);
    const overdue = visiblePayments.filter(item => item.status === 'overdue');
    $('#utilitiesMonthTitle').textContent = `${MONTHS[state.month.getMonth()]} ${state.month.getFullYear()}`;
    $('#utilitiesDue').textContent = formatMoney(due);
    $('#utilitiesPaid').textContent = formatMoney(paid);
    $('#utilitiesOverdue').textContent = formatMoney(overdue.reduce((sum, item) => sum + item.amount_minor, 0));
    $('#utilitiesOverdueCount').textContent = `${overdue.length} ${plural(overdue.length, 'счёт', 'счёта', 'счетов')}`;
    $('#utilityPaymentsTitle').textContent = selectedAccount ? `${selectedAccount.name} · ${MONTHS[state.month.getMonth()]}` : 'Счета за месяц';

    const paymentByAccount = new Map(state.payments.map(payment => [String(payment.account_id), payment]));
    const accountGrid = $('#accountGrid');
    accountGrid.innerHTML = state.accounts.length ? state.accounts.map(account => {
      const payment = paymentByAccount.get(String(account.id));
      const isPaid = payment?.status === 'paid';
      const amountLabel = payment ? `${isPaid ? 'Оплачено' : 'К оплате'} ${formatMoney(payment.amount_minor)}` : 'Платёж за месяц не добавлен';
      const dateLabel = payment?.paid_date ? `Оплачено ${formatShortDate(payment.paid_date)}` : payment ? `До ${formatShortDate(payment.due_date)}` : 'Добавьте сумму и срок';
      return `<article class="account-card ${String(account.id) === String(state.accountFilter) ? 'selected' : ''}">
        <div class="row-actions"><button class="row-action" data-edit-account="${account.id}" type="button" title="Редактировать квартиру">✎</button><button class="row-action" data-delete-account="${account.id}" type="button" title="Архивировать квартиру">×</button></div>
        <button class="account-card-select" data-utility-select="${account.id}" type="button"><h3>${escapeHtml(account.name)}</h3><p>${escapeHtml(account.address || 'Адрес не указан')}</p></button>
        <p>${escapeHtml(account.provider || 'УК или поставщик не указан')}</p><p>${account.account_number ? `Лицевой счёт: ${escapeHtml(account.account_number)}` : 'Лицевой счёт не указан'}</p>
        <div class="account-card-total"><strong>${amountLabel}</strong><small>${dateLabel}</small></div>
      </article>`;
    }).join('') : '<div class="empty-state">Добавьте первую квартиру, чтобы вести коммунальные платежи.</div>';
    $$('[data-utility-select]', accountGrid).forEach(button => button.onclick = () => { state.accountFilter = button.dataset.utilitySelect; if (filterSelect) filterSelect.value = state.accountFilter; render(); });
    $$('[data-edit-account]', accountGrid).forEach(button => button.onclick = () => openAccountModal(state.accounts.find(item => item.id === Number(button.dataset.editAccount))));
    $$('[data-delete-account]', accountGrid).forEach(button => button.onclick = async () => {
      if (!window.confirm('Архивировать эту квартиру?')) return;
      try { await api(`/api/utilities/accounts/${button.dataset.deleteAccount}`, { method: 'DELETE' }); await load(); } catch (error) { showToast(error.message, true); }
    });

    const list = $('#paymentList');
    list.innerHTML = visiblePayments.length ? visiblePayments.map(payment => {
      const statusLabel = payment.status === 'paid' ? 'Оплачено' : payment.status === 'overdue' ? 'Просрочено' : 'Ожидает';
      const dateText = payment.status === 'paid' && payment.paid_date ? `Оплачено ${formatShortDate(payment.paid_date)}` : `Срок ${formatShortDate(payment.due_date)}`;
      return `<article class="payment-card"><div><h3>${escapeHtml(payment.account_name)}</h3><p>${escapeHtml(payment.address || 'Адрес не указан')} · ${dateText}${payment.note ? ` · ${escapeHtml(payment.note)}` : ''}</p></div><div><span class="status-pill ${payment.status}">${statusLabel}</span></div><strong class="payment-amount">${formatMoney(payment.amount_minor)}</strong><div class="row-actions"><button class="row-action" data-toggle-payment="${payment.id}" type="button" title="${payment.status === 'paid' ? 'Снять оплату' : 'Отметить оплаченным'}">${payment.status === 'paid' ? '↶' : '✓'}</button><button class="row-action" data-edit-payment="${payment.id}" type="button" title="Редактировать">✎</button><button class="row-action" data-delete-payment="${payment.id}" type="button" title="Удалить">×</button></div></article>`;
    }).join('') : '<div class="empty-state">Для выбранной квартиры платежей за этот месяц нет.</div>';
    $$('[data-toggle-payment]', list).forEach(button => button.onclick = async () => {
      const payment = state.payments.find(item => item.id === Number(button.dataset.togglePayment));
      if (!payment) return;
      const nextStatus = payment.status === 'paid' ? 'pending' : 'paid';
      try { await api(`/api/utilities/payments/${payment.id}`, { method: 'PATCH', body: JSON.stringify({ status: nextStatus, paid_date: nextStatus === 'paid' ? todayIso() : null }) }); await load(); } catch (error) { showToast(error.message, true); }
    });
    $$('[data-edit-payment]', list).forEach(button => button.onclick = () => openPaymentModal(state.payments.find(item => item.id === Number(button.dataset.editPayment))));
    $$('[data-delete-payment]', list).forEach(button => button.onclick = async () => { if (!window.confirm('Удалить платёж?')) return; try { await api(`/api/utilities/payments/${button.dataset.deletePayment}`, { method: 'DELETE' }); await load(); } catch (error) { showToast(error.message, true); } });
  };

  function shiftMonth(amount) { state.month = new Date(state.month.getFullYear(), state.month.getMonth() + amount, 1); load(); }
  pageRefresh = load; window.refreshCurrentPage = load;
  $('#utilitiesPrev').onclick = () => shiftMonth(-1);
  $('#utilitiesNext').onclick = () => shiftMonth(1);
  $('#utilitiesToday').onclick = () => { state.month = firstOfMonth(new Date()); load(); };
  filterSelect?.addEventListener('change', () => { state.accountFilter = filterSelect.value; render(); });
  $('#addUtilityAccount').onclick = () => openAccountModal();
  $('#addUtilityPayment').onclick = () => openPaymentModal();
  $('#utilityAccountForm').onsubmit = async event => {
    event.preventDefault();
    const id = $('#utilityAccountId').value;
    const payload = { name: $('#utilityName').value.trim(), address: $('#utilityAddress').value.trim(), provider: $('#utilityProvider').value.trim(), account_number: $('#utilityAccountNumber').value.trim() };
    try { await api(id ? `/api/utilities/accounts/${id}` : '/api/utilities/accounts', { method: id ? 'PATCH' : 'POST', body: JSON.stringify(payload) }); closeModal('utilityAccountModal'); showToast(id ? 'Квартира обновлена' : 'Квартира добавлена'); await load(); } catch (error) { showToast(error.message, true); }
  };
  const syncPaidDateField = () => {
    const paid = $('#utilityPaymentStatus').value === 'paid';
    const field = $('#utilityPaymentPaidDate');
    if (field) { field.disabled = !paid; field.closest('label')?.style.setProperty('opacity', paid ? '1' : '.45'); if (paid && !field.value) field.value = todayIso(); }
  };
  $('#utilityPaymentStatus').onchange = syncPaidDateField;
  $('#utilityPaymentForm').onsubmit = async event => {
    event.preventDefault();
    const id = $('#utilityPaymentId').value;
    const status = $('#utilityPaymentStatus').value;
    const payload = { account_id: Number($('#utilityPaymentAccount').value), billing_month: $('#utilityPaymentMonth').value, due_date: $('#utilityPaymentDue').value, amount_minor: amountToMinor($('#utilityPaymentAmount').value), status, paid_date: status === 'paid' ? ($('#utilityPaymentPaidDate').value || todayIso()) : null, note: $('#utilityPaymentNote').value.trim() };
    if (!payload.amount_minor) { showToast('Введите сумму больше нуля', true); return; }
    try { await api(id ? `/api/utilities/payments/${id}` : '/api/utilities/payments', { method: id ? 'PATCH' : 'POST', body: JSON.stringify(payload) }); closeModal('utilityPaymentModal'); showToast(id ? 'Платёж обновлён' : 'Платёж добавлен'); await load(); } catch (error) { showToast(error.message, true); }
  };
  window.utilityState = state;
  await load();
}

function openAccountModal(account = null) { $('#utilityAccountModalTitle').textContent = account ? 'Редактировать квартиру' : 'Новая квартира'; $('#utilityAccountId').value = account?.id || ''; $('#utilityName').value = account?.name || ''; $('#utilityAddress').value = account?.address || ''; $('#utilityProvider').value = account?.provider || ''; $('#utilityAccountNumber').value = account?.account_number || ''; openModal('utilityAccountModal'); }
function openPaymentModal(payment = null) { const state = window.utilityState; const accounts = state?.accounts || []; if (!accounts.length) { showToast('Сначала добавьте квартиру', true); return; } const defaultAccount = state.accountFilter !== 'all' ? state.accountFilter : accounts[0].id; $('#utilityPaymentModalTitle').textContent = payment ? 'Редактировать платёж' : 'Новый платёж'; $('#utilityPaymentId').value = payment?.id || ''; $('#utilityPaymentAccount').innerHTML = accounts.map(account => `<option value="${account.id}">${escapeHtml(account.name)}${account.address ? ` · ${escapeHtml(account.address)}` : ''}</option>`).join(''); $('#utilityPaymentAccount').value = payment?.account_id || defaultAccount; $('#utilityPaymentMonth').value = payment?.billing_month || monthKey(state.month); $('#utilityPaymentDue').value = payment?.due_date || todayIso(); $('#utilityPaymentAmount').value = payment ? (payment.amount_minor / 100).toFixed(2).replace('.', ',') : ''; $('#utilityPaymentStatus').value = payment?.status === 'paid' ? 'paid' : 'pending'; $('#utilityPaymentPaidDate').value = payment?.paid_date || ''; $('#utilityPaymentNote').value = payment?.note || ''; $('#utilityPaymentStatus').dispatchEvent(new Event('change')); openModal('utilityPaymentModal'); }

async function initHabits() {
  const state = { habits: [], entries: [], dates: [] };
  const load = async () => { state.dates = dateRange(addDays(new Date(), -13), new Date()); const [habits, entries] = await Promise.all([api('/api/habits'), api(`/api/habits/entries?start=${isoDate(state.dates[0])}&end=${isoDate(state.dates[state.dates.length - 1])}`)]); state.habits = habits.habits; state.entries = entries.entries; render(); };
  const isDone = (habitId, dateKey) => state.entries.some(entry => entry.habit_id === habitId && entry.entry_date === dateKey && entry.done);
  const isScheduled = (habit, value) => habit.frequency === 'daily' || habit.schedule_days.includes((value.getDay() + 6) % 7);
  const streak = habit => { let count = 0; for (let d = new Date(); count < 365; d = addDays(d, -1)) { if (!isScheduled(habit, d)) continue; if (!isDone(habit.id, isoDate(d))) break; count += 1; } return count; };
  const bestStreak = habit => { let best = 0; let run = 0; for (const d of state.dates) { if (isScheduled(habit, d) && isDone(habit.id, isoDate(d))) { run += 1; best = Math.max(best, run); } else if (isScheduled(habit, d)) run = 0; } return Math.max(best, streak(habit)); };
  const render = () => { const todayDone = state.habits.filter(habit => isDone(habit.id, todayIso())).length; $('#habitTodayCount').textContent = `${todayDone} из ${state.habits.length}`; $('#habitTodayPercent').textContent = `${state.habits.length ? Math.round(todayDone / state.habits.length * 100) : 0}% привычек`; $('#habitActiveCount').textContent = state.habits.length; $('#habitBestStreak').textContent = `${state.habits.reduce((max, habit) => Math.max(max, bestStreak(habit)), 0)} ${plural(state.habits.reduce((max, habit) => Math.max(max, bestStreak(habit)), 0), 'день', 'дня', 'дней')}`;
    const board = $('#habitBoard'); const header = `<div class="habit-row header"><div class="habit-name"><div class="section-kicker">ПРИВЫЧКА</div></div>${state.dates.map(date => `<div class="habit-date ${isoDate(date) === todayIso() ? 'today' : ''}">${WEEKDAYS[(date.getDay() + 6) % 7]}<br>${pad(date.getDate())}</div>`).join('')}<div class="habit-stats">РЕЗУЛЬТАТ</div></div>`; const rows = state.habits.map(habit => `<div class="habit-row"><div class="habit-name"><i class="habit-dot" style="background:${escapeHtml(habit.color)};color:${escapeHtml(habit.color)}"></i><strong>${escapeHtml(habit.name)}</strong></div>${state.dates.map(date => { const key = isoDate(date); return `<div class="habit-cell"><button class="habit-toggle ${isDone(habit.id, key) ? 'done' : ''}" type="button" data-habit-id="${habit.id}" data-habit-date="${key}" aria-label="${escapeHtml(habit.name)} ${key}"></button></div>`; }).join('')}<div class="habit-stats"><strong>${streak(habit)} дн.</strong><div class="habit-actions"><button class="row-action" type="button" data-edit-habit="${habit.id}">✎</button><button class="row-action" type="button" data-delete-habit="${habit.id}">×</button></div></div></div>`).join(''); board.innerHTML = header + (rows || '<div class="empty-state">Добавьте привычку, с которой хотите начать.</div>');
    $$('[data-habit-id]', board).forEach(button => button.onclick = async () => { const done = button.classList.contains('done'); try { if (done) await api(`/api/habits/${button.dataset.habitId}/entries/${button.dataset.habitDate}`, { method: 'DELETE' }); else await api(`/api/habits/${button.dataset.habitId}/entries/${button.dataset.habitDate}`, { method: 'PUT', body: JSON.stringify({ done: true }) }); await load(); } catch (error) { showToast(error.message, true); } }); $$('[data-edit-habit]', board).forEach(button => button.onclick = () => openHabitModal(state.habits.find(habit => habit.id === Number(button.dataset.editHabit)))); $$('[data-delete-habit]', board).forEach(button => button.onclick = async () => { if (!window.confirm('Архивировать привычку?')) return; try { await api(`/api/habits/${button.dataset.deleteHabit}`, { method: 'DELETE' }); await load(); } catch (error) { showToast(error.message, true); } });
  };
  pageRefresh = load; window.refreshCurrentPage = load; $('#addHabit').onclick = () => openHabitModal(); $('#habitsToday').onclick = () => load(); $('#habitFrequency').onchange = () => { $('#habitDaysField').style.opacity = $('#habitFrequency').value === 'daily' ? '.45' : '1'; };
  $('#habitForm').onsubmit = async event => { event.preventDefault(); const id = $('#habitId').value; const payload = { name: $('#habitName').value.trim(), frequency: $('#habitFrequency').value, color: $('#habitColor').value, schedule_days: $$('#habitDaysField input:checked').map(input => Number(input.value)) }; try { await api(id ? `/api/habits/${id}` : '/api/habits', { method: id ? 'PATCH' : 'POST', body: JSON.stringify(payload) }); closeModal('habitModal'); showToast(id ? 'Привычка обновлена' : 'Привычка добавлена'); await load(); } catch (error) { showToast(error.message, true); } };
  await load();
}

function openHabitModal(habit = null) { $('#habitModalTitle').textContent = habit ? 'Редактировать привычку' : 'Добавить привычку'; $('#habitId').value = habit?.id || ''; $('#habitName').value = habit?.name || ''; $('#habitFrequency').value = habit?.frequency || 'daily'; $('#habitColor').value = habit?.color || '#ff2290'; const selected = habit?.schedule_days || [0, 1, 2, 3, 4, 5, 6]; $$('#habitDaysField input').forEach(input => { input.checked = selected.includes(Number(input.value)); }); $('#habitDaysField').style.opacity = $('#habitFrequency').value === 'daily' ? '.45' : '1'; openModal('habitModal'); }

async function initFinance() {
  const state = { month: firstOfMonth(new Date()), transactions: [], categories: [], operations: [], tab: window.location.hash === '#savings' ? 'savings' : 'operations', savingsFilter: 'all' };
  const operationsView = $('#financeOperationsView');
  const savingsView = $('#financeSavingsView');

  const renderOperations = () => {
    const filter = $('#financeFilter')?.value || 'all';
    const shown = filter === 'all' ? state.transactions : state.transactions.filter(item => item.kind === filter);
    const income = state.transactions.filter(item => item.kind === 'income').reduce((sum, item) => sum + item.amount_minor, 0);
    const expense = state.transactions.filter(item => item.kind === 'expense').reduce((sum, item) => sum + item.amount_minor, 0);
    $('#financeMonthTitle').textContent = `${MONTHS[state.month.getMonth()]} ${state.month.getFullYear()}`;
    $('#incomeTotal').textContent = formatMoney(income); $('#expenseTotal').textContent = formatMoney(expense); $('#balanceTotal').textContent = formatMoney(income - expense);
    $('#balanceTotal').style.color = income - expense >= 0 ? 'var(--green)' : 'var(--red)';
    $('#financeOperationCount').textContent = `${state.transactions.length} ${plural(state.transactions.length, 'операция', 'операции', 'операций')}`;
    const totals = {}; state.transactions.filter(item => item.kind === 'expense').forEach(item => { totals[item.category] = (totals[item.category] || 0) + item.amount_minor; });
    const categories = Object.entries(totals).sort((a, b) => b[1] - a[1]); const max = categories[0]?.[1] || 1;
    $('#categoryChart').innerHTML = categories.length ? categories.slice(0, 7).map(([category, value]) => `<div class="chart-row"><label>${escapeHtml(category)}</label><div class="chart-bar"><i style="width:${Math.round(value / max * 100)}%"></i></div><strong>${formatMoney(value)}</strong></div>`).join('') : '<div class="empty-state">Добавьте расходы, и здесь появится аналитика.</div>';
    $('#categoryLegend').innerHTML = categories.length ? categories.slice(0, 7).map(([category, value]) => `<div class="legend-item"><span>${escapeHtml(category)}</span><strong>${formatMoney(value)}</strong></div>`).join('') : '<div class="empty-state">Пока нет категорий.</div>';
    const body = $('#transactionsBody');
    body.innerHTML = shown.length ? shown.map(item => `<tr><td>${formatShortDate(item.transaction_date)}</td><td><strong>${escapeHtml(item.category)}</strong></td><td class="muted-cell">${escapeHtml(item.comment || '—')}</td><td><span class="type-pill ${item.kind}">${item.kind === 'income' ? 'Доход' : 'Расход'}</span></td><td class="align-right" style="color:${item.kind === 'income' ? 'var(--green)' : 'var(--red)'}">${item.kind === 'income' ? '+' : '−'}${formatMoney(item.amount_minor)}</td><td><div class="row-actions"><button class="row-action" data-edit-transaction="${item.id}" type="button">✎</button><button class="row-action" data-delete-transaction="${item.id}" type="button">×</button></div></td></tr>`).join('') : '<tr><td colspan="6"><div class="empty-state">За выбранный месяц операций нет.</div></td></tr>';
    $$('[data-edit-transaction]', body).forEach(button => button.onclick = () => openTransactionModal(state.transactions.find(item => item.id === Number(button.dataset.editTransaction))));
    $$('[data-delete-transaction]', body).forEach(button => button.onclick = async () => { if (!window.confirm('Удалить операцию?')) return; try { await api(`/api/finance/transactions/${button.dataset.deleteTransaction}`, { method: 'DELETE' }); await loadOperations(); } catch (error) { showToast(error.message, true); } });
  };

  const loadOperations = async () => { state.transactions = (await api(`/api/finance/transactions?month=${monthKey(state.month)}`)).transactions || []; renderOperations(); };

  const openSavingsOperation = (categoryId = null, kind = 'deposit', operation = null) => {
    $('#savingsOperationModalTitle').textContent = operation ? 'Редактировать операцию' : kind === 'withdrawal' ? 'Снять из сейфа' : 'Пополнить сейф';
    $('#savingsOperationId').value = operation?.id || '';
    $('#savingsOperationCategory').innerHTML = state.categories.map(item => `<option value="${item.id}">${escapeHtml(item.name)} · ${formatMoney(item.balance_minor)}</option>`).join('');
    $('#savingsOperationCategory').value = String(operation?.category_id || categoryId || state.categories[0]?.id || '');
    $('#savingsOperationKind').value = operation?.kind || kind;
    $('#savingsOperationAmount').value = operation ? (operation.amount_minor / 100).toFixed(2).replace('.', ',') : '';
    $('#savingsOperationDate').value = operation?.operation_date || todayIso();
    $('#savingsOperationComment').value = operation?.comment || '';
    openModal('savingsOperationModal');
  };

  const renderSavings = () => {
    const total = state.categories.reduce((sum, item) => sum + item.balance_minor, 0);
    $('#savingsTotal').textContent = formatMoney(total); $('#savingsAvailable').textContent = formatMoney(state.savingsAvailable || 0); $('#savingsCategoryCount').textContent = state.categories.length;
    const filter = $('#savingsCategoryFilter');
    filter.innerHTML = '<option value="all">Все категории</option>' + state.categories.map(item => `<option value="${item.id}">${escapeHtml(item.name)}</option>`).join(''); filter.value = state.savingsFilter;
    const cards = $('#savingsCards');
    cards.innerHTML = state.categories.length ? state.categories.map(category => {
      const goal = Number(category.goal_minor || 0); const balance = Number(category.balance_minor || 0); const progress = goal ? Math.min(100, Math.round(balance / goal * 100)) : 0;
      const plan = category.plan_enabled ? `План: ${formatMoney(category.planned_amount_minor)} · ${category.plan_day || '—'} числа` : 'Плановое пополнение не задано';
      return `<article class="savings-card"><div class="savings-card-top"><div class="savings-vault-mark">◈</div><div class="row-actions"><button class="row-action" data-savings-edit="${category.id}" type="button" title="Редактировать">✎</button><button class="row-action" data-savings-archive="${category.id}" type="button" title="Архивировать">×</button></div></div><h3>${escapeHtml(category.name)}</h3><strong class="savings-balance">${formatMoney(balance)}</strong>${goal ? `<div class="savings-progress"><i style="width:${progress}%"></i></div><small>${progress}% от цели ${formatMoney(goal)}</small>` : '<small>Цель не задана</small>'}<p class="savings-plan">${escapeHtml(plan)}</p><div class="savings-card-actions"><button class="button primary small" data-savings-deposit="${category.id}" type="button">＋ Пополнить</button><button class="button ghost small" data-savings-withdraw="${category.id}" type="button">Снять</button><button class="button ghost small" data-savings-plan="${category.id}" type="button">План</button></div></article>`;
    }).join('') : '<div class="empty-state">Создай первую категорию сейфа.</div>';
    $$('[data-savings-deposit]', cards).forEach(button => button.onclick = () => openSavingsOperation(Number(button.dataset.savingsDeposit), 'deposit'));
    $$('[data-savings-withdraw]', cards).forEach(button => button.onclick = () => openSavingsOperation(Number(button.dataset.savingsWithdraw), 'withdrawal'));
    $$('[data-savings-edit]', cards).forEach(button => button.onclick = () => { const category = state.categories.find(item => item.id === Number(button.dataset.savingsEdit)); $('#savingsCategoryModalTitle').textContent = 'Редактировать категорию'; $('#savingsCategoryId').value = category.id; $('#savingsCategoryName').value = category.name; $('#savingsCategoryGoal').value = category.goal_minor ? (category.goal_minor / 100).toFixed(2).replace('.', ',') : ''; openModal('savingsCategoryModal'); });
    $$('[data-savings-archive]', cards).forEach(button => button.onclick = async () => { if (!window.confirm('Архивировать категорию и сохранить её историю?')) return; try { await api(`/api/finance/savings/categories/${button.dataset.savingsArchive}`, { method: 'DELETE' }); await loadSavings(); } catch (error) { showToast(error.message, true); } });
    $$('[data-savings-plan]', cards).forEach(button => button.onclick = () => { const category = state.categories.find(item => item.id === Number(button.dataset.savingsPlan)); $('#savingsPlanCategory').value = category.id; $('#savingsPlanAmount').value = category.planned_amount_minor ? (category.planned_amount_minor / 100).toFixed(2).replace('.', ',') : ''; $('#savingsPlanDay').value = category.plan_day || 1; $('#savingsPlanEnabled').checked = Boolean(category.plan_enabled); openModal('savingsPlanModal'); });
    const operationBody = $('#savingsOperationsBody'); const visible = state.savingsFilter === 'all' ? state.operations : state.operations.filter(item => String(item.category_id) === String(state.savingsFilter));
    const labels = { initial: 'Начальный баланс', deposit: 'Пополнение', withdrawal: 'Снятие' };
    operationBody.innerHTML = visible.length ? visible.map(item => `<tr><td>${formatShortDate(item.operation_date)}</td><td><strong>${escapeHtml(item.category_name)}</strong></td><td><span class="type-pill ${item.kind === 'withdrawal' ? 'expense' : 'income'}">${labels[item.kind] || item.kind}</span></td><td class="muted-cell">${escapeHtml(item.comment || '—')}</td><td class="align-right" style="color:${item.kind === 'withdrawal' ? 'var(--red)' : 'var(--green)'}">${item.kind === 'withdrawal' ? '−' : '+'}${formatMoney(item.amount_minor)}</td><td><div class="row-actions"><button class="row-action" data-edit-savings-operation="${item.id}" type="button">✎</button><button class="row-action" data-delete-savings-operation="${item.id}" type="button">×</button></div></td></tr>`).join('') : '<tr><td colspan="6"><div class="empty-state">История сейфа пока пуста.</div></td></tr>';
    $$('[data-edit-savings-operation]', operationBody).forEach(button => button.onclick = () => openSavingsOperation(null, 'deposit', state.operations.find(item => item.id === Number(button.dataset.editSavingsOperation))));
    $$('[data-delete-savings-operation]', operationBody).forEach(button => button.onclick = async () => { if (!window.confirm('Удалить операцию сейфа?')) return; try { await api(`/api/finance/savings/operations/${button.dataset.deleteSavingsOperation}`, { method: 'DELETE' }); await loadSavings(); } catch (error) { showToast(error.message, true); } });
  };

  const loadSavings = async () => { const [summary, operations] = await Promise.all([api('/api/finance/savings/summary'), api('/api/finance/savings/operations')]); state.categories = summary.categories || []; state.operations = operations.operations || []; state.savingsAvailable = summary.available_balance_minor || 0; renderSavings(); };
  const setTab = tab => { state.tab = tab; operationsView.hidden = tab !== 'operations'; savingsView.hidden = tab !== 'savings'; $('#financeOperationsTab').classList.toggle('active', tab === 'operations'); $('#financeSavingsTab').classList.toggle('active', tab === 'savings'); $('#addTransaction').hidden = tab !== 'operations'; $('#addSavingsOperation').hidden = tab !== 'savings'; if (tab === 'savings') loadSavings(); else loadOperations(); try { history.replaceState(null, '', tab === 'savings' ? '#savings' : '#operations'); } catch { /* embedded webview */ } };

  pageRefresh = () => state.tab === 'savings' ? loadSavings() : loadOperations(); window.refreshCurrentPage = pageRefresh;
  $('#financePrev').onclick = () => { state.month = new Date(state.month.getFullYear(), state.month.getMonth() - 1, 1); loadOperations(); };
  $('#financeNext').onclick = () => { state.month = new Date(state.month.getFullYear(), state.month.getMonth() + 1, 1); loadOperations(); };
  $('#financeToday').onclick = () => { state.month = firstOfMonth(new Date()); loadOperations(); };
  $('#financeFilter').onchange = renderOperations; $('#savingsCategoryFilter').onchange = event => { state.savingsFilter = event.target.value; renderSavings(); };
  $$('[data-finance-tab]').forEach(button => button.onclick = () => setTab(button.dataset.financeTab));
  $('#addTransaction').onclick = () => openTransactionModal(); $('#addSavingsOperation').onclick = () => openSavingsOperation(); $('#addSavingsCategory').onclick = () => { $('#savingsCategoryModalTitle').textContent = 'Новая категория'; $('#savingsCategoryId').value = ''; $('#savingsCategoryName').value = ''; $('#savingsCategoryGoal').value = ''; openModal('savingsCategoryModal'); };
  $('#transactionForm').onsubmit = async event => { event.preventDefault(); const id = $('#transactionId').value; const amount = amountToMinor($('#transactionAmount').value); if (!amount) { showToast('Введите сумму больше нуля', true); return; } const payload = { kind: $('#transactionKind').value, amount_minor: amount, category: $('#transactionCategory').value.trim(), transaction_date: $('#transactionDate').value, comment: $('#transactionComment').value.trim() }; try { await api(id ? `/api/finance/transactions/${id}` : '/api/finance/transactions', { method: id ? 'PATCH' : 'POST', body: JSON.stringify(payload) }); closeModal('transactionModal'); showToast(id ? 'Операция обновлена' : 'Операция добавлена'); await loadOperations(); } catch (error) { showToast(error.message, true); } };
  $('#savingsCategoryForm').onsubmit = async event => { event.preventDefault(); const id = $('#savingsCategoryId').value; const payload = { name: $('#savingsCategoryName').value.trim(), goal_minor: amountToMinor($('#savingsCategoryGoal').value) }; try { await api(id ? `/api/finance/savings/categories/${id}` : '/api/finance/savings/categories', { method: id ? 'PATCH' : 'POST', body: JSON.stringify(payload) }); closeModal('savingsCategoryModal'); showToast(id ? 'Категория обновлена' : 'Категория добавлена'); await loadSavings(); } catch (error) { showToast(error.message, true); } };
  $('#savingsOperationForm').onsubmit = async event => { event.preventDefault(); const id = $('#savingsOperationId').value; const kind = $('#savingsOperationKind').value; const amount = amountToMinor($('#savingsOperationAmount').value); if (!amount) { showToast('Введите сумму больше нуля', true); return; } if (kind === 'withdrawal' && !window.confirm('Подтвердить снятие денег из сейфа?')) return; const payload = { category_id: Number($('#savingsOperationCategory').value), kind, amount_minor: amount, operation_date: $('#savingsOperationDate').value, comment: $('#savingsOperationComment').value.trim() }; try { await api(id ? `/api/finance/savings/operations/${id}` : '/api/finance/savings/operations', { method: id ? 'PATCH' : 'POST', body: JSON.stringify(payload) }); closeModal('savingsOperationModal'); showToast(id ? 'Операция обновлена' : 'Сейф обновлён'); await loadSavings(); } catch (error) { showToast(error.message, true); } };
  $('#savingsPlanForm').onsubmit = async event => { event.preventDefault(); const categoryId = $('#savingsPlanCategory').value; const payload = { enabled: $('#savingsPlanEnabled').checked, amount_minor: amountToMinor($('#savingsPlanAmount').value), day_of_month: Number($('#savingsPlanDay').value) }; try { await api(`/api/finance/savings/categories/${categoryId}/plan`, { method: 'PATCH', body: JSON.stringify(payload) }); closeModal('savingsPlanModal'); showToast('План накопления сохранён'); await loadSavings(); } catch (error) { showToast(error.message, true); } };
  setTab(state.tab);
}

async function initUtilities() {
  const state = { month: firstOfMonth(new Date()), accounts: [], payments: [], allPayments: [], services: new Map(), readings: new Map(), reminders: [], reminderSettings: { reminder_time: '09:00', notifications_enabled: true }, accountFilter: 'all', expanded: new Set(), paymentItems: [] };
  const filterSelect = $('#utilityApartmentFilter');
  const loadDetails = async accounts => { const details = await Promise.all(accounts.map(async account => { const [services, readings] = await Promise.all([api(`/api/utilities/accounts/${account.id}/services`), api(`/api/utilities/accounts/${account.id}/readings`)]); return { account, services: services.services || [], readings: readings.readings || [] }; })); state.services = new Map(details.map(item => [item.account.id, item.services])); state.readings = new Map(details.map(item => [item.account.id, item.readings])); };
  const load = async () => { const month = monthKey(state.month); const [accounts, payments, allPayments, reminder] = await Promise.all([api('/api/utilities/accounts'), api(`/api/utilities/payments?month=${month}`), api('/api/utilities/payments'), api(`/api/utilities/reminders/status?month=${month}&notify=1`)]); state.accounts = accounts.accounts || []; state.payments = payments.payments || []; state.allPayments = allPayments.payments || []; state.reminders = reminder.reminders || []; state.reminderSettings = reminder.settings || state.reminderSettings; if (!reminder.system_notification_sent && state.reminders.length && state.reminderSettings.notifications_enabled && 'Notification' in window) { const notificationKey = `reform-life.meter-reminder.${month}.${todayIso()}`; if (window.localStorage.getItem(notificationKey) !== '1') { const show = () => { try { new Notification('RE:FORM LIFE · Показания', { body: `Пора передать показания: ${state.reminders.map(item => item.account_name).join(', ')}.` }); window.localStorage.setItem(notificationKey, '1'); } catch (_error) { /* native notification is optional */ } }; if (Notification.permission === 'granted') show(); else if (Notification.permission === 'default') Notification.requestPermission().then(permission => { if (permission === 'granted') show(); }).catch(() => {}); } } await loadDetails(state.accounts); if (!state.accounts.some(account => String(account.id) === String(state.accountFilter))) state.accountFilter = 'all'; filterSelect.innerHTML = '<option value="all">Все квартиры</option>' + state.accounts.map(account => `<option value="${account.id}">${escapeHtml(account.name)}</option>`).join(''); filterSelect.value = state.accountFilter || 'all'; render(state.reminderSettings); };
  const paymentText = payment => { const label = payment.status === 'paid' ? 'Оплачено' : payment.status === 'overdue' ? 'Просрочено' : 'Ожидает'; return `<article class="payment-card"><div><h3>${escapeHtml(payment.account_name || '')}</h3><p>${escapeHtml(payment.address || 'Адрес не указан')} · ${label} · ${payment.paid_date ? formatShortDate(payment.paid_date) : `до ${formatShortDate(payment.due_date)}`}</p></div><strong class="payment-amount">${formatMoney(payment.amount_minor)}</strong><div class="row-actions"><button class="row-action" data-toggle-payment="${payment.id}" type="button">${payment.status === 'paid' ? '↶' : '✓'}</button><button class="row-action" data-edit-payment="${payment.id}" type="button">✎</button><button class="row-action" data-delete-payment="${payment.id}" type="button">×</button></div></article>`; };
  const render = settings => {
    const visible = state.accountFilter === 'all' ? state.payments : state.payments.filter(item => String(item.account_id) === String(state.accountFilter)); const due = visible.filter(item => item.status !== 'paid').reduce((sum, item) => sum + item.amount_minor, 0); const paid = visible.filter(item => item.status === 'paid').reduce((sum, item) => sum + item.amount_minor, 0); const overdue = visible.filter(item => item.status === 'overdue');
    const accrued = visible.reduce((sum, item) => sum + item.amount_minor, 0); $('#utilitiesMonthTitle').textContent = `${MONTHS[state.month.getMonth()]} ${state.month.getFullYear()}`; $('#utilitiesAccrued').textContent = formatMoney(accrued); $('#utilitiesDue').textContent = formatMoney(due); $('#utilitiesPaid').textContent = formatMoney(paid); $('#utilitiesOverdue').textContent = formatMoney(overdue.reduce((sum, item) => sum + item.amount_minor, 0)); $('#utilitiesOverdueCount').textContent = `${overdue.length} ${plural(overdue.length, 'счёт', 'счёта', 'счетов')}`;
    const reminder = $('#utilityReminder'); reminder.hidden = !state.reminders.length; if (state.reminders.length) { $('#utilityReminderTitle').textContent = `Пора передать показания · ${state.reminders.length} ${plural(state.reminders.length, 'квартира', 'квартиры', 'квартир')}`; $('#utilityReminderText').textContent = `${state.reminders.map(item => item.account_name).join(', ')}. Напоминание действует с 15-го по 26-е число, время — ${settings.reminder_time || '09:00'}.`; }
    const accountGrid = $('#accountGrid'); accountGrid.innerHTML = state.accounts.length ? state.accounts.map(account => { const payment = state.payments.find(item => item.account_id === account.id); const history = state.allPayments.filter(item => item.account_id === account.id).slice(0, 6); const services = state.services.get(account.id) || []; const readings = state.readings.get(account.id) || []; const latest = new Map(); readings.forEach(item => { if (!latest.has(item.service_id)) latest.set(item.service_id, item); }); const expanded = state.expanded.has(account.id); const isPaid = payment?.status === 'paid'; const amountLabel = payment ? `${isPaid ? 'Оплачено' : 'К оплате'} ${formatMoney(payment.amount_minor)}` : 'Платёж за месяц не добавлен'; return `<article class="account-card ${expanded ? 'expanded' : ''}"><div class="account-card-head"><button class="account-card-select" data-utility-toggle="${account.id}" type="button"><span class="account-card-chevron">${expanded ? '⌄' : '›'}</span><span><h3>${escapeHtml(account.name)}</h3><p>${escapeHtml(account.address || 'Адрес не указан')}</p></span></button><div class="row-actions"><button class="row-action" data-edit-account="${account.id}" type="button" title="Редактировать">✎</button><button class="row-action" data-delete-account="${account.id}" type="button" title="Архивировать">×</button></div></div><p>${escapeHtml(account.provider || 'УК или поставщик не указан')}</p><p>${account.account_number ? `Лицевой счёт: ${escapeHtml(account.account_number)}` : 'Лицевой счёт не указан'}</p><div class="account-card-total"><strong>${amountLabel}</strong><small>${payment?.paid_date ? `Оплачено ${formatShortDate(payment.paid_date)}` : payment ? `До ${formatShortDate(payment.due_date)}` : 'Добавьте сумму и срок'}</small></div><div class="account-card-actions"><button class="button primary small" data-account-payment="${account.id}" type="button">＋ Платёж</button><button class="button ghost small" data-account-reading="${account.id}" type="button">＋ Показание</button><button class="button ghost small" data-account-submission="${account.id}" type="button">Подано</button></div>${expanded ? `<div class="account-card-details"><div class="service-chips">${services.map(service => { const reading = latest.get(service.id); return `<span class="service-chip">${escapeHtml(service.name)}${reading ? ` · ${reading.reading_value} ${escapeHtml(service.unit || '')}` : ''}</span>`; }).join('') || '<span class="muted-cell">Услуги ещё не добавлены</span>'}</div><div class="account-payment-history">${history.length ? history.map(item => paymentText(item)).join('') : '<div class="empty-state">История платежей пуста.</div>'}</div></div>` : ''}</article>`; }).join('') : '<div class="empty-state">Добавьте первую квартиру, чтобы вести коммунальные платежи.</div>';
    $('#paymentList').innerHTML = visible.length ? visible.map(paymentText).join('') : '<div class="empty-state">Для выбранной квартиры платежей за этот месяц нет.</div>';
    $$('.account-card.expanded .service-chips', accountGrid).forEach(chips => { const accountId = chips.closest('.account-card')?.querySelector('[data-utility-toggle]')?.dataset.utilityToggle; if (!accountId || chips.nextElementSibling?.classList.contains('service-manager-row')) return; const wrapper = document.createElement('div'); wrapper.className = 'service-manager-row'; wrapper.innerHTML = `<button class="button ghost small" data-account-service="${accountId}" type="button">＋ Услуга</button>`; chips.insertAdjacentElement('afterend', wrapper); });
    $$('[data-utility-toggle]', accountGrid).forEach(button => button.onclick = () => { const id = Number(button.dataset.utilityToggle); if (state.expanded.has(id)) state.expanded.delete(id); else state.expanded.add(id); render(settings); });
    $$('[data-account-payment]', accountGrid).forEach(button => button.onclick = () => openPaymentModalV2(null, Number(button.dataset.accountPayment)));
    $$('[data-account-reading]', accountGrid).forEach(button => button.onclick = () => openReadingModal(Number(button.dataset.accountReading)));
    $$('[data-account-service]', accountGrid).forEach(button => button.onclick = () => openServiceModal(Number(button.dataset.accountService)));
    $$('[data-account-submission]', accountGrid).forEach(button => button.onclick = async () => { try { await api(`/api/utilities/accounts/${button.dataset.accountSubmission}/meter-submission`, { method: 'POST', body: JSON.stringify({ submission_month: monthKey(state.month), submitted: true }) }); showToast('Показания отмечены как поданные'); await load(); } catch (error) { showToast(error.message, true); } });
    $$('[data-edit-account]', accountGrid).forEach(button => button.onclick = () => openAccountModal(state.accounts.find(item => item.id === Number(button.dataset.editAccount))));
    $$('[data-delete-account]', accountGrid).forEach(button => button.onclick = async () => { if (!window.confirm('Архивировать эту квартиру?')) return; try { await api(`/api/utilities/accounts/${button.dataset.deleteAccount}`, { method: 'DELETE' }); await load(); } catch (error) { showToast(error.message, true); } });
    $$('[data-toggle-payment]', $('#paymentList')).forEach(button => button.onclick = async () => { const payment = state.payments.find(item => item.id === Number(button.dataset.togglePayment)); if (!payment) return; try { await api(`/api/utilities/payments/${payment.id}`, { method: 'PATCH', body: JSON.stringify({ status: payment.status === 'paid' ? 'pending' : 'paid', paid_date: payment.status === 'paid' ? null : todayIso() }) }); await load(); } catch (error) { showToast(error.message, true); } });
    $$('[data-edit-payment]', $('#paymentList')).forEach(button => button.onclick = () => openPaymentModalV2(state.payments.find(item => item.id === Number(button.dataset.editPayment))));
    $$('[data-delete-payment]', $('#paymentList')).forEach(button => button.onclick = async () => { if (!window.confirm('Удалить платёж?')) return; try { await api(`/api/utilities/payments/${button.dataset.deletePayment}`, { method: 'DELETE' }); await load(); } catch (error) { showToast(error.message, true); } });
  };
  const openPaymentModalV2 = (payment = null, accountId = null) => { const selected = accountId || payment?.account_id || (state.accountFilter !== 'all' ? Number(state.accountFilter) : state.accounts[0]?.id); $('#utilityPaymentModalTitle').textContent = payment ? 'Редактировать платёж' : 'Новый платёж'; $('#utilityPaymentId').value = payment?.id || ''; $('#utilityPaymentAccount').innerHTML = state.accounts.map(account => `<option value="${account.id}">${escapeHtml(account.name)}${account.address ? ` · ${escapeHtml(account.address)}` : ''}</option>`).join(''); $('#utilityPaymentAccount').value = selected || ''; $('#utilityPaymentMonth').value = payment?.billing_month || monthKey(state.month); $('#utilityPaymentDue').value = payment?.due_date || todayIso(); $('#utilityPaymentAmount').value = payment?.amount_minor ? (payment.amount_minor / 100).toFixed(2).replace('.', ',') : ''; $('#utilityPaymentStatus').value = payment?.status === 'paid' ? 'paid' : 'pending'; $('#utilityPaymentPaidDate').value = payment?.paid_date || ''; $('#utilityPaymentNote').value = payment?.note || ''; state.paymentItems = (payment?.items || []).map(item => ({ ...item })); renderPaymentItems(); openModal('utilityPaymentModal'); };
  const renderPaymentItems = () => { const accountId = Number($('#utilityPaymentAccount').value); const services = state.services.get(accountId) || []; const editor = $('#paymentItemsEditor'); editor.innerHTML = state.paymentItems.map((item, index) => `<div class="payment-item-editor-row" data-payment-item="${index}"><select data-item-service>${services.map(service => `<option value="${service.id}" ${String(service.id) === String(item.service_id) ? 'selected' : ''}>${escapeHtml(service.name)}</option>`).join('')}</select><input data-item-tariff inputmode="decimal" placeholder="Тариф ₽/ед." value="${item.tariff_minor ? (item.tariff_minor / 100).toFixed(2).replace('.', ',') : ''}"><input data-item-previous inputmode="decimal" placeholder="Было" value="${item.previous_reading ?? ''}"><input data-item-current inputmode="decimal" placeholder="Стало" value="${item.current_reading ?? ''}"><input data-item-amount inputmode="decimal" placeholder="Сумма ₽" value="${item.amount_minor ? (item.amount_minor / 100).toFixed(2).replace('.', ',') : ''}"><button class="row-action" data-remove-payment-item="${index}" type="button">×</button></div>`).join(''); const calculate = row => { const tariff = Number(String($('[data-item-tariff]', row)?.value || '').replace(/\s/g, '').replace(',', '.')); const previous = Number(String($('[data-item-previous]', row)?.value || '').replace(/\s/g, '').replace(',', '.')); const current = Number(String($('[data-item-current]', row)?.value || '').replace(/\s/g, '').replace(',', '.')); if (Number.isFinite(tariff) && tariff > 0 && Number.isFinite(previous) && Number.isFinite(current) && current >= previous) { $('[data-item-amount]', row).value = ((current - previous) * tariff).toFixed(2).replace('.', ','); } }; $$('[data-item-tariff], [data-item-previous], [data-item-current]', editor).forEach(input => input.addEventListener('input', () => calculate(input.closest('[data-payment-item]')))); $$('[data-remove-payment-item]', editor).forEach(button => button.onclick = () => { state.paymentItems.splice(Number(button.dataset.removePaymentItem), 1); renderPaymentItems(); }); };
  const openReadingModal = accountId => { const services = state.services.get(accountId) || []; if (!services.length) { showToast('Сначала добавьте услугу для этой квартиры', true); return; } $('#utilityReadingAccount').value = accountId; $('#utilityReadingService').innerHTML = services.map(item => `<option value="${item.id}">${escapeHtml(item.name)}${item.unit ? ` · ${escapeHtml(item.unit)}` : ''}</option>`).join(''); $('#utilityReadingValue').value = ''; $('#utilityReadingDate').value = todayIso(); $('#utilityReadingNote').value = ''; openModal('utilityReadingModal'); };
  const openServiceModal = accountId => { $('#utilityServiceAccount').value = accountId; $('#utilityServiceName').value = ''; $('#utilityServiceUnit').value = ''; openModal('utilityServiceModal'); setTimeout(() => $('#utilityServiceName')?.focus(), 40); };
  pageRefresh = load; window.refreshCurrentPage = load; $('#utilitiesPrev').onclick = () => { state.month = new Date(state.month.getFullYear(), state.month.getMonth() - 1, 1); load(); }; $('#utilitiesNext').onclick = () => { state.month = new Date(state.month.getFullYear(), state.month.getMonth() + 1, 1); load(); }; $('#utilitiesToday').onclick = () => { state.month = firstOfMonth(new Date()); load(); }; filterSelect.onchange = () => { state.accountFilter = filterSelect.value; render(state.reminderSettings); }; $('#addUtilityAccount').onclick = () => openAccountModal(); $('#addUtilityPayment').onclick = () => openPaymentModalV2(); $('#addPaymentItem').onclick = () => { state.paymentItems.push({}); renderPaymentItems(); }; $('#utilityPaymentAccount').onchange = renderPaymentItems;
  $('#utilityAccountForm').onsubmit = async event => { event.preventDefault(); const id = $('#utilityAccountId').value; const payload = { name: $('#utilityName').value.trim(), address: $('#utilityAddress').value.trim(), provider: $('#utilityProvider').value.trim(), account_number: $('#utilityAccountNumber').value.trim() }; try { await api(id ? `/api/utilities/accounts/${id}` : '/api/utilities/accounts', { method: id ? 'PATCH' : 'POST', body: JSON.stringify(payload) }); closeModal('utilityAccountModal'); showToast(id ? 'Квартира обновлена' : 'Квартира добавлена'); await load(); } catch (error) { showToast(error.message, true); } };
  $('#utilityPaymentStatus').onchange = () => { const paid = $('#utilityPaymentStatus').value === 'paid'; $('#utilityPaymentPaidDate').disabled = !paid; if (paid && !$('#utilityPaymentPaidDate').value) $('#utilityPaymentPaidDate').value = todayIso(); };
  $('#utilityPaymentForm').onsubmit = async event => { event.preventDefault(); const id = $('#utilityPaymentId').value; const items = $$('#paymentItemsEditor [data-payment-item]').map(row => ({ service_id: Number($('[data-item-service]', row)?.value), service_name: $('[data-item-service] option:checked', row)?.textContent?.trim() || '', amount_minor: amountToMinor($('[data-item-amount]', row)?.value), tariff_minor: amountToMinor($('[data-item-tariff]', row)?.value), previous_reading: $('[data-item-previous]', row)?.value || null, current_reading: $('[data-item-current]', row)?.value || null })).filter(item => item.amount_minor); const payload = { account_id: Number($('#utilityPaymentAccount').value), billing_month: $('#utilityPaymentMonth').value, due_date: $('#utilityPaymentDue').value, amount_minor: amountToMinor($('#utilityPaymentAmount').value), status: $('#utilityPaymentStatus').value, paid_date: $('#utilityPaymentStatus').value === 'paid' ? ($('#utilityPaymentPaidDate').value || todayIso()) : null, note: $('#utilityPaymentNote').value.trim(), items }; if (!payload.amount_minor && !items.length) { showToast('Введите общую сумму или добавьте услугу', true); return; } try { await api(id ? `/api/utilities/payments/${id}` : '/api/utilities/payments', { method: id ? 'PATCH' : 'POST', body: JSON.stringify(payload) }); closeModal('utilityPaymentModal'); showToast(id ? 'Платёж обновлён' : 'Платёж добавлен'); await load(); } catch (error) { showToast(error.message, true); } };
  $('#utilityReadingForm').onsubmit = async event => { event.preventDefault(); const accountId = $('#utilityReadingAccount').value; try { await api(`/api/utilities/accounts/${accountId}/readings`, { method: 'POST', body: JSON.stringify({ service_id: Number($('#utilityReadingService').value), reading_value: $('#utilityReadingValue').value, reading_date: $('#utilityReadingDate').value, note: $('#utilityReadingNote').value.trim() }) }); closeModal('utilityReadingModal'); showToast('Показание сохранено'); await load(); } catch (error) { showToast(error.message, true); } };
  $('#utilityServiceForm').onsubmit = async event => { event.preventDefault(); const accountId = $('#utilityServiceAccount').value; try { await api(`/api/utilities/accounts/${accountId}/services`, { method: 'POST', body: JSON.stringify({ name: $('#utilityServiceName').value.trim(), unit: $('#utilityServiceUnit').value.trim() }) }); closeModal('utilityServiceModal'); showToast('Услуга добавлена'); await load(); if (accountId) { state.expanded.add(Number(accountId)); render(state.reminderSettings); } } catch (error) { showToast(error.message, true); } };
  $('#utilityReminderSettings').onclick = async () => { const result = await api('/api/utilities/reminders/settings'); $('#utilityReminderTime').value = result.settings.reminder_time || '09:00'; $('#utilityNotificationsEnabled').checked = Boolean(result.settings.notifications_enabled); openModal('utilityReminderSettingsModal'); };
  $('#utilityReminderSettingsForm').onsubmit = async event => { event.preventDefault(); try { await api('/api/utilities/reminders/settings', { method: 'PATCH', body: JSON.stringify({ reminder_time: $('#utilityReminderTime').value, notifications_enabled: $('#utilityNotificationsEnabled').checked }) }); closeModal('utilityReminderSettingsModal'); showToast('Настройки напоминаний сохранены'); await load(); } catch (error) { showToast(error.message, true); } };
  await load();
}

function startPage() {
  bindCommon(); initWelcome(); bindDataSync(); initDatePickers(); $('#taskForm')?.addEventListener('submit', saveTask); $('#noteForm')?.addEventListener('submit', saveNote); $('#sectionForm')?.addEventListener('submit', saveSection);
  const page = document.body.dataset.page; const init = page === 'week' ? initWeek : page === 'tasks' ? initTasks : page === 'assistant' ? initAssistantChat : page === 'month' ? initMonth : page === 'finance' ? initFinance : page === 'utilities' ? initUtilities : initHabits;
  maybeMigrateLegacy().then(() => loadSections()).then(() => init()).then(() => { pageReady = true; return initMoodPrompt(); }).catch(error => showToast(error.message, true));
}

document.addEventListener('DOMContentLoaded', startPage);
