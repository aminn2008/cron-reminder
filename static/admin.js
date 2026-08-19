async function loadAll() {
  try {
    const me = await api('/api/me');
    document.getElementById('user-chip').textContent = '👤 ' + me.user.username;
    if (!me.user.is_admin) {
      toast('You are not an admin', 'error');
      setTimeout(() => (location.href = '/dashboard'), 800);
      return;
    }
  } catch (e) { return; }

  await Promise.all([loadOverview(), loadUsers(), loadJobs(), loadLogs()]);
}

async function loadOverview() {
  const o = await api('/api/admin/overview');
  document.getElementById('stats').innerHTML = `
    <div class="stat-card blue"><div class="icon">👥</div><div class="num">${o.users}</div><div class="lbl">Users</div></div>
    <div class="stat-card violet"><div class="icon">📋</div><div class="num">${o.jobs}</div><div class="lbl">Total reminders</div></div>
    <div class="stat-card green"><div class="icon">✅</div><div class="num">${o.logs - o.failed}</div><div class="lbl">Successful runs</div></div>
    <div class="stat-card red"><div class="icon">⚠️</div><div class="num">${o.failed}</div><div class="lbl">Errors</div></div>`;
}

async function loadUsers() {
  const data = await api('/api/admin/users');
  document.getElementById('users-body').innerHTML = data.users.map((u) => `
    <tr>
      <td>${u.id}</td>
      <td><b>${esc(u.username)}</b></td>
      <td>${esc(u.email)}</td>
      <td>${u.job_count}</td>
      <td>${u.is_admin ? '<span class="badge amber">👑 Admin</span>' : '<span class="badge gray">User</span>'}</td>
    </tr>`).join('');
}

async function loadJobs() {
  const data = await api('/api/admin/jobs');
  document.getElementById('jobs-body').innerHTML = data.jobs.map((j) => `
    <tr>
      <td>${j.id}</td>
      <td><b>${esc(j.name)}</b></td>
      <td>${esc(j.owner)}</td>
      <td><span class="badge violet">🔄 ${esc(j.interval_label || '—')}</span></td>
      <td>${fmtChannels(j)}</td>
      <td>${j.enabled ? '<span class="badge green">Active</span>' : '<span class="badge gray">Paused</span>'}</td>
    </tr>`).join('');
}

async function loadLogs() {
  const o = await api('/api/admin/overview');
  document.getElementById('logs-body').innerHTML = o.recent_logs.map((l) => `
    <tr>
      <td>${esc(l.executed_at)}</td>
      <td>${esc(l.username)}</td>
      <td>${esc(l.job_name)}</td>
      <td>${l.channel === 'email' ? '📧 Email' : '📱 Telegram'}</td>
      <td>${badge(l.status)}</td>
      <td style="font-size:12px;color:var(--text-dim)">${esc(l.detail)}</td>
    </tr>`).join('') || '<tr><td colspan="6" class="empty">No logs yet</td></tr>';
}

loadAll();

// Live refresh for the admin panel
setInterval(() => {
  loadOverview().catch(() => {});
  loadJobs().catch(() => {});
  loadLogs().catch(() => {});
}, 10000);
