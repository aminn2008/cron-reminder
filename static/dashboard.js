let jobs = [];
let currentUserEmail = null;


const UNIT_MINUTES = { minutes: 1, hours: 60, days: 1440, weeks: 10080, months: 43200 };

function toMinutes(val, unit) {
  return val * (UNIT_MINUTES[unit] || 1);
}

function humanizeInterval(m) {
  if (!m || m < 1) return '—';
  const fa = getLang() === 'fa';
  const num = (n) => (fa ? faNum(n) : String(n));
  let rem = m;
  const units = [
    [43200, 'month'], [10080, 'week'], [1440, 'day'], [60, 'hour'], [1, 'minute'],
  ];
  const parts = [];
  for (const [mul, name] of units) {
    const n = Math.floor(rem / mul);
    if (n > 0) {
      parts.push(fa ? `${num(n)} ${t('unit.' + name)}` : `${num(n)} ${t('unit.' + name)}${n > 1 ? 's' : ''}`);
      rem -= n * mul;
    }
  }
  if (!parts.length) return t('min1');
  return t('every.prefix') + parts.join(' ');
}

function decompose(m) {
  const units = [['months', 43200], ['weeks', 10080], ['days', 1440], ['hours', 60], ['minutes', 1]];
  for (const [unit, mul] of units) {
    if (m % mul === 0) return { val: m / mul, unit };
  }
  return { val: m, unit: 'minutes' };
}

function updateConversion() {
  const val = parseInt(document.getElementById('f-interval').value, 10);
  const unit = document.getElementById('f-unit').value;
  const conv = document.getElementById('f-conv');
  if (!val || val < 1) {
    conv.textContent = '';
    return;
  }
  const m = toMinutes(val, unit);
  conv.textContent = '= ' + humanizeInterval(m);
}


function setMode(mode) {
  const once = mode === 'once';
  document.getElementById('mode-repeat').classList.toggle('active', !once);
  document.getElementById('mode-once').classList.toggle('active', once);
  document.getElementById('repeat-section').classList.toggle('hidden', once);
  document.getElementById('once-section').classList.toggle('hidden', !once);
  document.getElementById('f-interval').required = !once;
  document.getElementById('f-once-at').required = once;
  if (once && !document.getElementById('f-once-at').value) {
    
    const d = new Date(Date.now() + 3600 * 1000);
    const pad = (n) => String(n).padStart(2, '0');
    document.getElementById('f-once-at').value =
      `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }
}

function toLocalInput(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return '';
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}


async function loadAll() {
  try {
    const me = await api('/api/me');
    currentUserEmail = me.user.email;
    document.getElementById('user-chip').textContent = '👤 ' + me.user.username;
    if (me.user.is_admin) document.getElementById('admin-link').classList.remove('hidden');
  } catch (e) {}

  await Promise.all([loadJobs(), loadStats(), loadLogs(), loadTelegramStatus(), loadTelegramPanel()]);
}


async function loadTelegramStatus() {
  try {
    const s = await api('/api/telegram/status');
    const el = document.getElementById('tg-status');
    if (!el) return;
    if (s.configured) {
      el.textContent = s.bot_username
        ? `${t('tg.botActive')} @${s.bot_username} ${t('tg.sendToGetChatId')}`
        : t('tg.botConfigured');
    } else {
      el.textContent = t('tg.notConfigured');
    }
  } catch (e) {}
}

async function testTelegram() {
  const chatId = document.getElementById('f-chat').value.trim();
  if (!chatId) {
    toast(t('tg.enterChatId'), 'error');
    return;
  }
  try {
    await api('/api/telegram/test', {
      method: 'POST',
      body: JSON.stringify({ chat_id: chatId }),
    });
    toast(t('tg.testSent'), 'success');
  } catch (err) {
    toast(err.message, 'error');
  }
}


async function loadTelegramPanel() {
  const el = document.getElementById('tg-panel');
  if (!el) return;
  try {
    const [status, bind] = await Promise.all([
      api('/api/telegram/status'),
      api('/api/telegram/bind-status'),
    ]);
    if (!status.configured) {
      el.innerHTML = `<p class="hint">${t('tg.notConfigured')}</p>`;
      return;
    }
    if (bind.bound) {
      el.innerHTML = `
        <p>${t('tg.linkedTo')} <code>${esc(bind.chat_id)}</code></p>
        <p class="hint">${t('tg.manageHint')}</p>
        <button class="btn danger small" onclick="unbindTelegram()">${t('tg.unlink')}</button>`;
    } else {
      el.innerHTML = `
        <p>${t('tg.step1')} <button class="btn ghost small" onclick="getBindCode()">${t('tg.getBindCode')}</button></p>
        <p class="hint" id="bind-code-box"></p>
        <p class="hint">${t('tg.step2')} <b>@${esc(status.bot_username || 'your bot')}</b></p>
        <p class="hint">${t('tg.step3')}</p>`;
    }
  } catch (e) {
    el.innerHTML = `<p class="hint">${t('tg.loadFailed')}</p>`;
  }
}

async function getBindCode() {
  try {
    const r = await api('/api/telegram/bind-code', { method: 'POST' });
    const box = document.getElementById('bind-code-box');
    if (box) box.innerHTML = `${tWith('tg.bindCodeMsg', { n: r.expires_minutes })} <code class="code-box">${esc(r.code)}</code>`;
  } catch (err) {
    toast(err.message, 'error');
  }
}

async function unbindTelegram() {
  if (!confirm(t('confirm.unbind'))) return;
  try {
    await api('/api/telegram/unbind', { method: 'POST' });
    toast(t('tg.unlinked'), 'success');
    loadTelegramPanel();
  } catch (err) {
    toast(err.message, 'error');
  }
}

async function loadJobs() {
  const data = await api('/api/jobs');
  jobs = data.jobs;
  const body = document.getElementById('jobs-body');
  if (!jobs.length) {
    body.innerHTML = `<tr><td colspan="6" class="empty">${t('dash.emptyJobs')}</td></tr>`;
    return;
  }
  body.innerHTML = jobs.map((j) => `
    <tr>
      <td><b>${esc(j.name)}</b></td>
      <td><span class="badge ${j.type === 'once' ? 'blue' : 'violet'}">${j.type === 'once' ? '🔔' : '🔄'} ${esc(j.interval_label || '—')}</span></td>
      <td>${fmtChannels(j)}</td>
      <td>${j.next_run ? esc(j.next_run) : `<span class="badge gray">${t('status.disabled')}</span>`}</td>
      <td>${j.enabled ? `<span class="badge green">${t('status.active')}</span>` : `<span class="badge gray">${t('status.paused')}</span>`}</td>
      <td><div class="actions">
        <button class="btn ghost small" onclick="runNow(${j.id})" title="${t('action.runNow')}">▶️</button>
        <button class="btn ghost small" onclick="toggleJob(${j.id})" title="${t('action.pauseResume')}">${j.enabled ? '⏸️' : '▶️'}</button>
        <button class="btn ghost small" onclick="editJob(${j.id})" title="${t('action.edit')}">✏️</button>
        <button class="btn danger small" onclick="deleteJob(${j.id})" title="${t('action.delete')}">🗑️</button>
      </div></td>
    </tr>`).join('');
}

async function loadStats() {
  const s = await api('/api/stats');
  document.getElementById('stats').innerHTML = `
    <div class="stat-card blue"><div class="icon">📋</div><div class="num">${s.total}</div><div class="lbl">${t('stats.total')}</div></div>
    <div class="stat-card violet"><div class="icon">⚡</div><div class="num">${s.enabled}</div><div class="lbl">${t('stats.active')}</div></div>
    <div class="stat-card green"><div class="icon">📧</div><div class="num">${s.success}</div><div class="lbl">${t('stats.sent')}</div></div>
    <div class="stat-card red"><div class="icon">⚠️</div><div class="num">${s.failed}</div><div class="lbl">${t('stats.failed')}</div></div>`;
}

async function loadLogs() {
  const data = await api('/api/logs?limit=30');
  const body = document.getElementById('logs-body');
  if (!data.logs.length) {
    body.innerHTML = `<tr><td colspan="5" class="empty">${t('common.noLogs')}</td></tr>`;
    return;
  }
  body.innerHTML = data.logs.map((l) => `
    <tr>
      <td>${esc(l.executed_at)}</td>
      <td>${esc(l.job_name)}</td>
      <td>${l.channel === 'email' ? t('channel.email') : t('channel.telegram')}</td>
      <td>${badge(l.status)}</td>
      <td style="font-size:12px;color:var(--text-dim)">${esc(l.detail)}</td>
    </tr>`).join('');
}


async function runNow(id) {
  try {
    await api(`/api/jobs/${id}/run-now`, { method: 'POST' });
    toast(t('runNow.toast'), 'success');
    await Promise.all([loadLogs(), loadStats()]);
  } catch (e) { toast(e.message, 'error'); }
}

async function toggleJob(id) {
  try {
    await api(`/api/jobs/${id}/toggle`, { method: 'POST' });
    await Promise.all([loadJobs(), loadStats()]);
  } catch (e) { toast(e.message, 'error'); }
}

async function deleteJob(id) {
  if (!confirm(t('confirm.deleteJob'))) return;
  try {
    await api(`/api/jobs/${id}`, { method: 'DELETE' });
    toast(t('job.deleted'), 'success');
  } catch (e) {
    toast(e.message, 'error');
  }
  await Promise.all([loadJobs(), loadStats()]);
}


function openModal(job) {
  document.getElementById('modal-title').textContent = job ? t('modal.edit') : t('modal.new');
  document.getElementById('f-id').value = job ? job.id : '';
  document.getElementById('f-name').value = job ? job.name : '';
  document.getElementById('f-message').value = job ? job.message : '';

  
  const emailHint = document.getElementById('f-email-default');
  emailHint.textContent = currentUserEmail ? t('modal.defaultEmail') + ' ' + currentUserEmail : '';
  document.getElementById('f-email').placeholder = currentUserEmail || t('modal.emailPh');
  document.getElementById('f-email').value = job ? (job.email_to || currentUserEmail || '') : (currentUserEmail || '');

  document.getElementById('f-chat').value = job ? (job.telegram_chat_id || '') : '';
  document.getElementById('f-enabled').checked = job ? job.enabled : true;

  if (job && job.type === 'once' && job.send_once_at) {
    setMode('once');
    document.getElementById('f-once-at').value = toLocalInput(job.send_once_at);
  } else {
    setMode('repeat');
    const m = job ? (job.interval_minutes || 60) : 60;
    const dec = decompose(m);
    document.getElementById('f-interval').value = dec.val;
    document.getElementById('f-unit').value = dec.unit;
    document.querySelectorAll('.preset').forEach((b) => {
      b.classList.toggle('active', parseInt(b.dataset.m, 10) === m);
    });
    updateConversion();
  }

  document.getElementById('modal').classList.remove('hidden');
}

function editJob(id) {
  const job = jobs.find((j) => j.id === id);
  if (job) openModal(job);
}

function closeModal() {
  document.getElementById('modal').classList.add('hidden');
}


document.querySelectorAll('.preset').forEach((btn) => {
  btn.addEventListener('click', () => {
    const m = parseInt(btn.dataset.m, 10);
    const dec = decompose(m);
    document.getElementById('f-interval').value = dec.val;
    document.getElementById('f-unit').value = dec.unit;
    document.querySelectorAll('.preset').forEach((b) => b.classList.toggle('active', b === btn));
    updateConversion();
  });
});

document.getElementById('f-interval').addEventListener('input', () => {
  document.querySelectorAll('.preset').forEach((b) => b.classList.remove('active'));
  updateConversion();
});
document.getElementById('f-unit').addEventListener('change', updateConversion);

async function saveJob(e) {
  e.preventDefault();
  const id = document.getElementById('f-id').value;
  const onceMode = !document.getElementById('once-section').classList.contains('hidden');
  const val = parseInt(document.getElementById('f-interval').value, 10);
  const unit = document.getElementById('f-unit').value;
  const payload = {
    name: document.getElementById('f-name').value,
    message: document.getElementById('f-message').value,
    interval_minutes: onceMode ? null : toMinutes(val, unit),
    send_once_at: onceMode ? (document.getElementById('f-once-at').value || null) : null,
    email_to: document.getElementById('f-email').value.trim() || null,
    telegram_chat_id: document.getElementById('f-chat').value.trim() || null,
    enabled: document.getElementById('f-enabled').checked,
  };
  try {
    if (id) {
      await api(`/api/jobs/${id}`, { method: 'PUT', body: JSON.stringify(payload) });
      toast(t('job.updated'), 'success');
    } else {
      await api('/api/jobs', { method: 'POST', body: JSON.stringify(payload) });
      toast(t('job.created'), 'success');
    }
    closeModal();
    await Promise.all([loadJobs(), loadStats()]);
  } catch (err) {
    toast(err.message, 'error');
  }
}

loadAll();


window.addEventListener('langchange', () => {
  loadJobs().catch(() => {});
  loadStats().catch(() => {});
  loadLogs().catch(() => {});
  loadTelegramStatus().catch(() => {});
  loadTelegramPanel().catch(() => {});
  updateConversion();
});

setInterval(() => {
  loadJobs().catch(() => {});
  loadStats().catch(() => {});
  loadLogs().catch(() => {});
}, 10000);
