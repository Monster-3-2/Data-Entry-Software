// ============================================================
// MAHLE — Sidebar & Layout Builder
// Include this after config.js on every inner page
// ============================================================

function buildLayout(activePage) {
  const user = Auth.getUser();
  if (!user) { window.location.href = '/index.html'; return; }

  const isAdmin    = user.role === 'admin';
  const isOperator = user.role === 'operator';

  const initials = (user.name || 'U').split(' ').map(w => w[0]).join('').toUpperCase().slice(0,2);

  // Nav items — [label, href, icon_svg_path, roles_allowed]
  const navItems = [
    {
      section: 'Overview',
      items: [
        { label: 'Dashboard',       href: '/dashboard.html',         icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6', roles: ['admin','operator','viewer'] },
      ]
    },
    {
      section: 'Production',
      items: [
        { label: 'Data Entry',      href: '/production/entry.html',  icon: 'M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z', roles: ['admin','operator'] },
        { label: 'Entry History',   href: '/production/history.html',icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2', roles: ['admin','operator','viewer'] },
      ]
    },
    {
      section: 'Analytics',
      items: [
        { label: 'Dashboard',       href: '/analytics/dashboard.html', icon: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z', roles: ['admin','operator','viewer'] },
        { label: 'Monthly Summary', href: '/analytics/monthly.html',   icon: 'M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z', roles: ['admin','operator','viewer'] },
      ]
    },
    {
      section: 'Master Data',
      items: [
        { label: 'Lines & Models',  href: '/master/lines.html',      icon: 'M4 6h16M4 10h16M4 14h16M4 18h16', roles: ['admin'] },
        { label: 'Product Master',  href: '/master/products.html',   icon: 'M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4', roles: ['admin'] },
        { label: 'Shifts',          href: '/master/shifts.html',     icon: 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z', roles: ['admin'] },
        { label: 'Downtime Reasons',href: '/master/reasons.html',    icon: 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z', roles: ['admin'] },
        { label: 'Master Overview', href: '/master/overview.html', icon: 'M3 10h18M3 14h18M10 3v18M14 3v18M3 6a3 3 0 013-3h12a3 3 0 013 3v12a3 3 0 01-3 3H6a3 3 0 01-3-3V6z', roles: ['admin','operator','viewer'] },
        { label: 'Users',           href: '/master/users.html',      icon: 'M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z', roles: ['admin'] },
      ]
    }
  ];

  // Build sidebar HTML
  let navHTML = '';
  navItems.forEach(section => {
    const visibleItems = section.items.filter(i => i.roles.includes(user.role));
    if (!visibleItems.length) return;

    navHTML += `<div class="nav-section-label">${section.section}</div>`;
    visibleItems.forEach(item => {
      const isActive = window.location.pathname.endsWith(item.href.replace(/^\//, '')) ? 'active' : '';
      navHTML += `
        <a class="nav-item ${isActive}" href="${item.href}">
          <svg class="icon" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="${item.icon}"/>
          </svg>
          ${item.label}
        </a>`;
    });
  });

  const sidebarHTML = `
    <aside class="sidebar" id="sidebar">
      <a class="sidebar-logo" href="/dashboard.html">
        <div class="logo-mark">
          <img src="mahle.png" alt="Company Logo" style="width:28px;height:28px;object-fit:contain;">
        </div>
        <div class="logo-text">
          <div class="logo-name">MAHLE</div>
          <div class="logo-sub">Sanand MIS</div>
        </div>
      </a>
      <nav class="sidebar-nav">${navHTML}</nav>
      <div class="sidebar-footer">
        <div class="user-badge">
          <div class="user-avatar">${initials}</div>
          <div class="user-info">
            <div class="user-name">${user.name || user.email}</div>
            <div class="user-role">${user.role}</div>
          </div>
          <button class="btn-logout" onclick="handleLogout()" title="Sign out">
            <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"/>
            </svg>
          </button>
        </div>
      </div>
    </aside>`;

  // Insert into DOM
  document.body.insertAdjacentHTML('afterbegin', sidebarHTML);

  // Apply app-layout wrapper
  document.body.classList.add('has-sidebar');
}

async function handleLogout() {
  try { await API.post('/api/auth/logout', {}); } catch (_) {}
  Auth.clear();
  window.location.href = '/index.html';
}
