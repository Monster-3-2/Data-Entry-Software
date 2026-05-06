// ============================================================
// MAHLE Production — Global Config
// Update BACKEND_URL after deploying to Render
// ============================================================

const CONFIG = {
  BACKEND_URL: 'https://data-entry-software-jx8u.onrender.com',  
  APP_NAME: 'MAHLE Production',
  APP_TAGLINE: 'Thermal Systems Manufacturing Intelligence',
};

// ============================================================
// Auth helpers
// ============================================================

const Auth = {
  getToken() {
    return localStorage.getItem('mahle_token');
  },
  getUser() {
    const u = localStorage.getItem('mahle_user');
    return u ? JSON.parse(u) : null;
  },
  setSession(token, user) {
    localStorage.setItem('mahle_token', token);
    localStorage.setItem('mahle_user', JSON.stringify(user));
  },
  clear() {
    localStorage.removeItem('mahle_token');
    localStorage.removeItem('mahle_user');
  },
  isLoggedIn() {
    return !!this.getToken();
  },
  role() {
    const u = this.getUser();
    return u ? u.role : null;
  },
  requireAuth(allowedRoles = []) {
    if (!this.isLoggedIn()) {
      window.location.href = '/index.html';
      return false;
    }
    if (allowedRoles.length && !allowedRoles.includes(this.role())) {
      window.location.href = '/dashboard.html';
      return false;
    }
    return true;
  }
};

// ============================================================
// API helper
// ============================================================

const API = {
  async request(method, path, body = null) {
    const headers = { 'Content-Type': 'application/json' };
    const token = Auth.getToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const opts = { method, headers };
    if (body) opts.body = JSON.stringify(body);

    const res = await fetch(`${CONFIG.BACKEND_URL}${path}`, opts);

    if (res.status === 401) {
      Auth.clear();
      window.location.href = '/index.html';
      return;
    }
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Request failed' }));
      throw new Error(err.detail || 'Request failed');
    }
    return res.json();
  },

  get(path)         { return this.request('GET', path); },
  post(path, body)  { return this.request('POST', path, body); },
  put(path, body)   { return this.request('PUT', path, body); },
  delete(path)      { return this.request('DELETE', path); },
};

// ============================================================
// Toast notification
// ============================================================

function showToast(message, type = 'success') {
  const existing = document.getElementById('mahle-toast');
  if (existing) existing.remove();

  const toast = document.createElement('div');
  toast.id = 'mahle-toast';
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <span class="toast-icon">${type === 'success' ? '✓' : type === 'error' ? '✕' : 'ℹ'}</span>
    <span>${message}</span>
  `;
  document.body.appendChild(toast);
  setTimeout(() => toast.classList.add('show'), 10);
  setTimeout(() => { toast.classList.remove('show'); setTimeout(() => toast.remove(), 300); }, 3000);
}

// ============================================================
// Format helpers
// ============================================================

function fmtDate(d) {
  return d ? new Date(d).toLocaleDateString('en-IN') : '-';
}

function fmtNum(n, dec = 2) {
  return Number(n || 0).toFixed(dec);
}

function efficiency(output, target) {
  if (!target) return 0;
  return ((output / target) * 100).toFixed(1);
}

function efficiencyColor(pct) {
  const p = parseFloat(pct);
  if (p >= 95) return 'var(--green)';
  if (p >= 80) return 'var(--amber)';
  return 'var(--red)';
}
