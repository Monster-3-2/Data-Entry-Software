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

    // Timeout + retry: Render free tier cold-starts can take 30-50s.
    // First attempt: 25s timeout. On timeout, retry once with 40s timeout.
    const fetchWithTimeout = (ms) => {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), ms);
      return fetch(`${CONFIG.BACKEND_URL}${path}`, { ...opts, signal: controller.signal })
        .finally(() => clearTimeout(timer));
    };

    let res;
    try {
      res = await fetchWithTimeout(25000);
    } catch (e) {
      if (e.name === 'AbortError') {
        // Cold-start timeout — retry once with longer timeout
        console.warn('API timeout, retrying (cold-start?):', path);
        res = await fetchWithTimeout(50000);
      } else {
        throw e;
      }
    }

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

// ============================================================
// DateState — shared date across all pages (sessionStorage)
// Persists for the entire browser session (tab lifetime).
// Clears automatically when the tab is closed.
// ============================================================

const DateState = {
  _KEY_DATE:  'mahle_active_date',
  _KEY_FROM:  'mahle_range_from',
  _KEY_TO:    'mahle_range_to',

  // ── Single active date (entry page, history "today" view) ──
  getDate() {
    return sessionStorage.getItem(this._KEY_DATE) || this._today();
  },
  setDate(d) {
    if (d) sessionStorage.setItem(this._KEY_DATE, d);
  },

  // ── Date range (analytics dashboard, history filters) ──
  getFrom() {
    return sessionStorage.getItem(this._KEY_FROM) || this._daysAgo(29);
  },
  setFrom(d) {
    if (d) sessionStorage.setItem(this._KEY_FROM, d);
  },
  getTo() {
    return sessionStorage.getItem(this._KEY_TO) || this._today();
  },
  setTo(d) {
    if (d) sessionStorage.setItem(this._KEY_TO, d);
  },

  // ── Helpers ──
  _today() {
    return new Date().toISOString().split('T')[0];
  },
  _daysAgo(n) {
    return new Date(Date.now() - n * 86400000).toISOString().split('T')[0];
  },

  // Bind a single date <input> so it reads & writes DateState automatically
  bindDate(inputId, onChange) {
    const el = document.getElementById(inputId);
    if (!el) return;
    el.value = this.getDate();
    el.addEventListener('change', () => {
      this.setDate(el.value);
      if (onChange) onChange(el.value);
    });
  },

  // Bind a from/to date pair
  bindRange(fromId, toId, onChange) {
    const fromEl = document.getElementById(fromId);
    const toEl   = document.getElementById(toId);
    if (!fromEl || !toEl) return;
    fromEl.value = this.getFrom();
    toEl.value   = this.getTo();
    const notify = () => {
      this.setFrom(fromEl.value);
      this.setTo(toEl.value);
      if (onChange) onChange(fromEl.value, toEl.value);
    };
    fromEl.addEventListener('change', notify);
    toEl.addEventListener('change', notify);
  },
};

// ============================================================
// FIX 3: Custom in-app confirmation dialog (replaces browser confirm())
// ============================================================

function showConfirm(message, onConfirm, options = {}) {
  const existing = document.getElementById('mahle-confirm');
  if (existing) existing.remove();

  const overlay = document.createElement('div');
  overlay.id = 'mahle-confirm';
  overlay.style.cssText = [
    'position:fixed','inset:0','z-index:9999',
    'background:rgba(0,0,0,0.45)',
    'display:flex','align-items:center','justify-content:center',
    'animation:fadeIn 0.15s ease',
  ].join(';');

  const type    = options.type || 'danger';   // danger | warning | info
  const label   = options.confirmLabel || (type === 'danger' ? 'Delete' : 'Confirm');
  const colors  = { danger:'#DC2626', warning:'#D97706', info:'#0077CC' };
  const icons   = { danger:'🗑', warning:'⚠', info:'ℹ' };
  const btnColor = colors[type] || colors.danger;

  overlay.innerHTML = `
    <div style="
      background:var(--bg-card,#fff);
      border-radius:12px;
      box-shadow:0 20px 60px rgba(0,0,0,0.3);
      padding:28px 32px;
      max-width:420px;
      width:90%;
      animation:slideUp 0.2s ease;
    ">
      <div style="display:flex;align-items:flex-start;gap:14px;margin-bottom:20px">
        <div style="font-size:1.8rem;line-height:1">${icons[type]}</div>
        <div>
          <div style="font-weight:700;font-size:1rem;margin-bottom:6px;color:var(--text-primary,#111)">
            ${options.title || 'Are you sure?'}
          </div>
          <div style="font-size:0.875rem;color:var(--text-muted,#666);line-height:1.5">${message}</div>
        </div>
      </div>
      <div style="display:flex;justify-content:flex-end;gap:10px">
        <button id="mc-cancel" style="
          padding:8px 18px;border-radius:6px;border:1px solid var(--border,#ddd);
          background:transparent;cursor:pointer;font-size:0.875rem;font-weight:600;
          color:var(--text-muted,#666);
        ">Cancel</button>
        <button id="mc-confirm" style="
          padding:8px 18px;border-radius:6px;border:none;
          background:${btnColor};color:white;cursor:pointer;
          font-size:0.875rem;font-weight:700;
        ">${label}</button>
      </div>
    </div>`;

  // Add keyframe styles once
  if (!document.getElementById('mahle-confirm-style')) {
    const s = document.createElement('style');
    s.id = 'mahle-confirm-style';
    s.textContent = `
      @keyframes fadeIn  { from { opacity:0 } to { opacity:1 } }
      @keyframes slideUp { from { transform:translateY(16px);opacity:0 } to { transform:translateY(0);opacity:1 } }
    `;
    document.head.appendChild(s);
  }

  document.body.appendChild(overlay);

  const close = () => {
    overlay.style.opacity = '0';
    overlay.style.transition = 'opacity 0.15s';
    setTimeout(() => overlay.remove(), 150);
  };

  document.getElementById('mc-cancel').onclick  = close;
  document.getElementById('mc-confirm').onclick = () => { close(); onConfirm(); };
  overlay.onclick = e => { if (e.target === overlay) close(); };
  document.addEventListener('keydown', function esc(e) {
    if (e.key === 'Escape') { close(); document.removeEventListener('keydown', esc); }
  });
}

// ============================================================
// FIX 4: Performance — deduplication + multi-tier cache + debounce
// ============================================================

// ── Debounce utility ──
function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

// ── In-flight deduplication: same GET reuses one Promise ──
const _inflight = {};
const _origGet  = API.get.bind(API);
API.get = function(path) {
  if (_inflight[path]) return _inflight[path];
  const p = _origGet(path).finally(() => delete _inflight[path]);
  _inflight[path] = p;
  return p;
};

// ── Multi-tier cache ──
//   Tier 1 — master data (lines/shifts/models/reasons): 5 min (rarely changes)
//   Tier 2 — analytics/summary data:                    90 sec
//   Tier 3 — production entries:                        30 sec (changes often)
const _cache = {};
const CACHE_RULES = [
  { prefix: '/api/master/lines',    ttl: 300000 },
  { prefix: '/api/master/shifts',   ttl: 300000 },
  { prefix: '/api/master/models',   ttl: 300000 },
  { prefix: '/api/master/reasons',  ttl: 300000 },
  { prefix: '/api/master/products', ttl: 300000 },
  { prefix: '/api/master/shift-groups', ttl: 300000 },
  { prefix: '/api/analytics/',      ttl: 90000  },
  { prefix: '/api/production/entries', ttl: 30000 },
];

const _origReq = API.request.bind(API);
API.request = function(method, path, body) {
  if (method === 'GET') {
    const rule = CACHE_RULES.find(r => path.startsWith(r.prefix));
    if (rule) {
      const now = Date.now();
      if (_cache[path] && now - _cache[path].ts < rule.ttl) {
        return Promise.resolve(_cache[path].data);
      }
      return _origReq(method, path, body).then(data => {
        _cache[path] = { ts: Date.now(), data };
        return data;
      });
    }
  }
  // On any write (POST/PUT/DELETE), bust cache for that resource prefix
  if (['POST','PUT','DELETE'].includes(method)) {
    const prefix = path.split('?')[0].replace(/\/[^/]+$/, '');
    Object.keys(_cache).forEach(k => { if (k.startsWith(prefix)) delete _cache[k]; });
  }
  return _origReq(method, path, body);
};

// ── Prefetch master data on page load (hide network latency) ──
(function prefetchMaster() {
  const paths = [
    '/api/master/lines', '/api/master/shifts',
    '/api/master/reasons', '/api/master/shift-groups',
  ];
  // Ping the health endpoint first to wake up Render free-tier cold-start
  // Then prefetch master data — by the time user clicks, data is ready
  setTimeout(() => {
    fetch(`${CONFIG.BACKEND_URL}/`, { method: 'GET' }).catch(() => {});
    paths.forEach(p => API.get(p).catch(() => {}));
  }, 100);
})();
