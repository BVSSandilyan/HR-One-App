/* ── HR ONEAPP — Global App JS ── */

let notifOpen = false;

function toggleNotifs() {
  const dropdown = document.getElementById('notif-dropdown');
  notifOpen = !notifOpen;
  dropdown.style.display = notifOpen ? 'block' : 'none';
  if (notifOpen) loadNotifications();
}

document.addEventListener('click', function (e) {
  if (!e.target.closest('.notif-area')) {
    const dd = document.getElementById('notif-dropdown');
    if (dd) dd.style.display = 'none';
    notifOpen = false;
  }
});

async function loadNotifications() {
  try {
    const res = await fetch('/meeting/notifications');
    const data = await res.json();
    const list = document.getElementById('notif-list');
    const count = document.getElementById('notif-count');
    if (!list || !count) return;

    count.textContent = data.length;
    count.style.display = data.length > 0 ? 'flex' : 'none';

    if (data.length === 0) {
      list.innerHTML = '<p style="padding:1rem;color:var(--text-faint);text-align:center;font-size:.82rem;">No new notifications</p>';
      return;
    }

    list.innerHTML = data.map(n => `
      <div class="notif-item ${n.type}" id="notif-${n.id}">
        <div style="flex:1;">
          <p style="margin-bottom:3px;">${n.message}</p>
          <small style="color:var(--text-faint);">${new Date(n.created_at).toLocaleString()}</small>
          ${n.type === 'meeting' && n.ref_id ?
            `<br/><a href="/meeting/${n.ref_id}/join" style="color:var(--accent);font-size:.78rem;font-weight:700;">→ Join Meeting</a>` : ''}
          ${n.type === 'registration' && n.ref_id && window.HR_USER_ROLE === 'admin' ?
            `<br/><a href="/admin/registrations/${n.ref_id}" style="color:var(--warning);font-size:.78rem;font-weight:700;">→ View Registration Request</a>` : ''}
          ${n.type === 'leave' && n.ref_id && window.HR_USER_ROLE === 'admin' ? `
            <div class="notif-leave-actions" id="notif-leave-${n.ref_id}" style="display:flex;gap:.4rem;margin-top:.5rem;">
              <button class="notif-act-btn approve" onclick="quickLeaveAction(${n.ref_id}, 'approve', ${n.id})">✓ Approve</button>
              <button class="notif-act-btn decline" onclick="quickLeaveAction(${n.ref_id}, 'decline', ${n.id})">✕ Decline</button>
            </div>` : ''}
        </div>
        <button class="notif-dismiss" onclick="dismissNotif(${n.id})">✕</button>
      </div>
    `).join('');

    const meetingNotifs = data.filter(n => n.type === 'meeting');
    if (meetingNotifs.length > 0) showMeetingAlert(meetingNotifs[0]);

  } catch (e) { console.error('Notification error:', e); }
}

/* Admin approves/declines a leave request directly from the bell dropdown —
   no page navigation required. Falls back to a flash message on the next
   page load if the fetch itself fails, since the action already round-tripped
   to the server by the time any UI update could fail. */
async function quickLeaveAction(leaveId, action, notifId) {
  const block = document.getElementById(`notif-leave-${leaveId}`);
  if (block) block.innerHTML = '<span style="font-size:.78rem;color:var(--text-faint);">Processing…</span>';
  try {
    const res = await fetch(`/leave/${leaveId}/quick/${action}`, { method: 'POST' });
    const data = await res.json();
    if (data.status === 'ok') {
      if (block) {
        block.innerHTML = `<span style="font-size:.78rem;font-weight:700;color:${data.new_status === 'approved' ? 'var(--success)' : 'var(--danger)'};">
          ${data.new_status === 'approved' ? '✓ Approved' : '✕ Declined'}
        </span>`;
      }
      setTimeout(() => dismissNotif(notifId), 1200);
    } else if (data.status === 'needs_rate') {
      // This request exceeds the employee's leave balance — approving it
      // requires the admin to enter a ₹/day deduction rate, which there's
      // no room for in the notification dropdown. Send them to the full
      // review page instead of silently approving with no deduction.
      if (block) {
        block.innerHTML = `<a href="${data.redirect}" style="font-size:.78rem;font-weight:700;color:var(--warning);">
          ⚠ Exceeds balance by ${data.excess_days.toFixed(1)}d — click to set deduction
        </a>`;
      }
    } else if (block) {
      block.innerHTML = `<span style="font-size:.78rem;color:var(--danger);">${data.message || 'Already reviewed'}</span>`;
    }
  } catch (e) {
    if (block) block.innerHTML = '<span style="font-size:.78rem;color:var(--danger);">Network error — try the Leave Requests page</span>';
  }
}

async function dismissNotif(id) {
  await fetch(`/meeting/notifications/read/${id}`, { method: 'POST' });
  document.getElementById(`notif-${id}`)?.remove();
  const remaining = document.querySelectorAll('.notif-item').length;
  const count = document.getElementById('notif-count');
  if (count) count.textContent = remaining;
}

function showMeetingAlert(notif) {
  if (document.getElementById('meeting-popup')) return;
  const popup = document.createElement('div');
  popup.id = 'meeting-popup';
  popup.style.cssText = `
    position:fixed;bottom:1.5rem;right:1.5rem;z-index:9999;
    background:var(--surface);border-radius:14px;box-shadow:var(--shadow-lg);
    padding:1.25rem 1.5rem;max-width:320px;border-left:4px solid var(--accent);
    animation:slideIn .3s ease;color:var(--text);
  `;
  popup.innerHTML = `
    <style>@keyframes slideIn{from{transform:translateX(120%)}to{transform:translateX(0)}}</style>
    <div style="display:flex;justify-content:space-between;align-items:flex-start;">
      <div>
        <p style="font-weight:700;margin-bottom:.4rem;">📹 Meeting Alert</p>
        <p style="font-size:.83rem;color:var(--text-muted);margin-bottom:.75rem;">${notif.message}</p>
        <a href="/meeting/${notif.ref_id}/join" onclick="dismissPopup(${notif.id})"
          style="background:var(--accent);color:#fff;padding:.4rem .9rem;border-radius:6px;font-size:.78rem;font-weight:700;">
          Join Meeting
        </a>
      </div>
      <button onclick="document.getElementById('meeting-popup').remove()"
        style="background:none;border:none;cursor:pointer;color:var(--text-faint);font-size:1.1rem;margin-left:.5rem;">✕</button>
    </div>
  `;
  document.body.appendChild(popup);
  setTimeout(() => popup.remove(), 15000);
}

async function dismissPopup(notifId) {
  await dismissNotif(notifId);
  document.getElementById('meeting-popup')?.remove();
}

setInterval(loadNotifications, 20000);
window.addEventListener('load', () => setTimeout(loadNotifications, 1000));

/* ── DARK MODE (session-only, sessionStorage) ── */
function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  const icon = document.getElementById('theme-icon');
  if (icon) icon.textContent = theme === 'dark' ? '☀️' : '🌙';
}

function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme') || 'light';
  const next = current === 'dark' ? 'light' : 'dark';
  applyTheme(next);
  try { sessionStorage.setItem('hr_theme', next); } catch (e) {}
}

(function initTheme() {
  let saved = 'light';
  try { saved = sessionStorage.getItem('hr_theme') || 'light'; } catch (e) {}
  applyTheme(saved);
})();

/* ── MOBILE SIDEBAR ── */
function toggleSidebar() {
  document.querySelector('.sidebar')?.classList.toggle('open');
}
