function switchTab(name) {
  document.getElementById('tab-login').classList.toggle('active', name === 'login');
  document.getElementById('tab-register').classList.toggle('active', name === 'register');
  document.getElementById('login-form').classList.toggle('hidden', name !== 'login');
  document.getElementById('register-form').classList.toggle('hidden', name !== 'register');
}

async function doLogin(e) {
  e.preventDefault();
  try {
    await api('/api/login', {
      method: 'POST',
      body: JSON.stringify({
        username: document.getElementById('login-username').value,
        password: document.getElementById('login-password').value,
      }),
    });
    location.href = '/dashboard';
  } catch (err) {
    toast(err.message, 'error');
  }
}

async function doRegister(e) {
  e.preventDefault();
  try {
    await api('/api/register', {
      method: 'POST',
      body: JSON.stringify({
        username: document.getElementById('reg-username').value,
        email: document.getElementById('reg-email').value,
        password: document.getElementById('reg-password').value,
      }),
    });
    toast('Registration successful! Welcome 🎉', 'success');
    setTimeout(() => (location.href = '/dashboard'), 600);
  } catch (err) {
    toast(err.message, 'error');
  }
}

// Already logged in? Go straight to the dashboard
api('/api/me')
  .then(() => (location.href = '/dashboard'))
  .catch(() => {});

// Telegram Web App (Mini App): auto-login with initData
async function tryTelegramWebApp() {
  try {
    const tg = window.Telegram && window.Telegram.WebApp;
    if (!tg || !tg.initData) return false;
    tg.expand();
    const res = await fetch('/api/telegram/webapp-login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ init_data: tg.initData }),
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      location.href = '/dashboard';
      return true;
    }
    toast(data.detail || 'Telegram login failed', 'error');
  } catch (e) {}
  return false;
}
tryTelegramWebApp();
