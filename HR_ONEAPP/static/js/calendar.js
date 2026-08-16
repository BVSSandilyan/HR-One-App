/* ════════════════════════════════════════════
   HR ONEAPP — Shared Calendar Widget
   Read-only: click a day to see its events.
   Usage: initCalendar('cal-container-id', '/api/calendar/endpoint')
   ════════════════════════════════════════════ */

function initCalendar(containerId, feedUrl, opts = {}) {
  const root = document.getElementById(containerId);
  if (!root) return;

  let current = new Date();
  current.setDate(1);
  let allEvents = [];
  let activePopover = null;

  const DOW = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
  const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December'];

  root.innerHTML = `
    <div class="cal-header">
      <span class="cal-title">${opts.title || 'Calendar'}</span>
      <div class="cal-nav">
        <button id="${containerId}-prev">‹</button>
        <span class="cal-month-label" id="${containerId}-label"></span>
        <button id="${containerId}-next">›</button>
      </div>
    </div>
    <div class="cal-legend" id="${containerId}-legend"></div>
    <div class="cal-grid" id="${containerId}-grid"></div>
  `;

  document.getElementById(`${containerId}-prev`).onclick = () => { current.setMonth(current.getMonth()-1); render(); };
  document.getElementById(`${containerId}-next`).onclick = () => { current.setMonth(current.getMonth()+1); render(); };

  /* Build YYYY-MM-DD from the LOCAL calendar fields, never via toISOString().
     toISOString() converts through UTC first — for any timezone ahead of UTC
     (e.g. IST, UTC+5:30) that silently rolls local midnight back to the
     previous day, which is exactly what shifted every event one cell off
     in this widget. getFullYear/getMonth/getDate read the local fields
     directly, so this is immune to the browser's timezone. */
  function dateKey(d){
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${dd}`;
  }

  function buildLegend(events){
    const seen = {};
    events.forEach(e => { if (e.category && !seen[e.category]) seen[e.category] = e.color || '#64748b'; });
    const legend = document.getElementById(`${containerId}-legend`);
    legend.innerHTML = Object.entries(seen).map(([cat,color]) =>
      `<span><span class="legend-dot" style="background:${color}"></span>${cat}</span>`
    ).join('') || '<span style="color:var(--text-faint);">No events yet</span>';
  }

  function render(){
    document.getElementById(`${containerId}-label`).textContent =
      `${MONTHS[current.getMonth()]} ${current.getFullYear()}`;

    const grid = document.getElementById(`${containerId}-grid`);
    grid.innerHTML = DOW.map(d => `<div class="cal-dow">${d}</div>`).join('');

    const year = current.getFullYear(), month = current.getMonth();
    const firstDay = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month+1, 0).getDate();
    const todayKey = dateKey(new Date());

    // Group events by date
    const byDate = {};
    allEvents.forEach(e => {
      const k = e.start;
      (byDate[k] = byDate[k] || []).push(e);
    });

    for (let i=0;i<firstDay;i++){
      grid.insertAdjacentHTML('beforeend', '<div class="cal-day empty"></div>');
    }

    for (let day=1; day<=daysInMonth; day++){
      const d = new Date(year, month, day);
      const key = dateKey(d);
      const evts = byDate[key] || [];
      const isToday = key === todayKey;
      const dotRow = evts.slice(0,4).map(e => `<span class="cal-evt-dot" style="background:${e.color||'#64748b'}"></span>`).join('');

      const cell = document.createElement('div');
      cell.className = `cal-day${isToday ? ' today' : ''}`;
      cell.innerHTML = `
        <span class="cal-day-num">${day}</span>
        <div class="cal-dot-row">${dotRow}</div>
        ${evts.length ? `<span class="cal-day-count">${evts.length}</span>` : ''}
      `;
      cell.onclick = (ev) => showPopover(ev, key, evts);
      grid.appendChild(cell);
    }

    buildLegend(allEvents);
  }

  function showPopover(clickEvent, dateKeyStr, evts){
    closePopover();
    const pop = document.createElement('div');
    pop.className = 'cal-popover';
    const niceDate = new Date(dateKeyStr + 'T00:00:00').toLocaleDateString(undefined, {weekday:'short', month:'short', day:'numeric', year:'numeric'});

    pop.innerHTML = `
      <div class="cal-popover-header">
        <span>${niceDate}</span>
        <button class="cal-popover-close">✕</button>
      </div>
      ${evts.length ? evts.map(e => `
        <div class="cal-popover-evt">
          <span class="dot" style="background:${e.color||'#64748b'}"></span>
          <span>${e.title}</span>
        </div>`).join('') : '<div class="cal-popover-empty">No events on this day.</div>'}
    `;
    document.body.appendChild(pop);

    const rect = clickEvent.currentTarget.getBoundingClientRect();
    let left = rect.left + window.scrollX;
    let top  = rect.bottom + window.scrollY + 6;
    if (left + 260 > window.innerWidth) left = window.innerWidth - 280;
    pop.style.left = `${left}px`;
    pop.style.top  = `${top}px`;

    pop.querySelector('.cal-popover-close').onclick = closePopover;
    activePopover = pop;

    setTimeout(() => {
      document.addEventListener('click', outsideClickHandler);
    }, 0);
  }

  function outsideClickHandler(e){
    if (activePopover && !activePopover.contains(e.target)) closePopover();
  }

  function closePopover(){
    if (activePopover){
      activePopover.remove();
      activePopover = null;
      document.removeEventListener('click', outsideClickHandler);
    }
  }

  // Initial skeleton while loading
  document.getElementById(`${containerId}-grid`).innerHTML =
    '<div style="grid-column:1/-1;padding:2rem;text-align:center;color:var(--text-faint);"><span class="spinner"></span> Loading calendar…</div>';

  fetch(feedUrl)
    .then(r => r.json())
    .then(data => { allEvents = data || []; render(); })
    .catch(() => {
      document.getElementById(`${containerId}-grid`).innerHTML =
        '<div style="grid-column:1/-1;padding:2rem;text-align:center;color:var(--text-faint);">Could not load calendar events.</div>';
    });
}
