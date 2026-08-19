async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (res.status === 401) {
    
    if (location.pathname !== '/') location.href = '/';
    throw new Error('unauthorized');
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || t('err.server'));
  return data;
}

function toast(msg, type = '') {
  const box = document.getElementById('toasts');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  box.appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s == null ? '' : String(s);
  return d.innerHTML;
}

function badge(status) {
  const map = {
    success: ['green', t('badge.success')],
    failed: ['red', t('badge.failed')],
    skipped: ['gray', t('badge.skipped')],
  };
  const [cls, label] = map[status] || ['gray', status];
  return `<span class="badge ${cls}">${label}</span>`;
}

function fmtChannels(job) {
  const parts = [];
  if (job.email_to) parts.push(`<span class="badge blue">${t('channel.email')}</span>`);
  if (job.telegram_chat_id) parts.push(`<span class="badge amber">${t('channel.telegram')}</span>`);
  return parts.join(' ') || '<span class="badge gray">—</span>';
}

async function logout() {
  try { await api('/api/logout', { method: 'POST' }); } catch (e) {}
  location.href = '/';
}
