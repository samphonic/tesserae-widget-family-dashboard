export default async function render(shadow, ctx) {
  const data = ctx.data || {};

  // Display error state if server-side fetch failed
  if (data.error) {
    shadow.innerHTML = `
      <link rel="stylesheet" href="/static/icons/phosphor/bold/style.css">
      <div style="padding: 2rem; color: var(--text-primary); font-family: var(--font-family, sans-serif);">
        <i class="ph-bold ph-warning-circle" style="font-size: 2rem; color: var(--accent-1);"></i>
        <h2 style="margin: 0.5rem 0;">Unable to load dashboard</h2>
        <p style="color: var(--text-secondary);">${data.error}</p>
      </div>
    `;
    return;
  }

  const dateInfo = data.date_info || { weekday: "Monday", day: "1", month_year: "January" };
  const weather = data.weather || {};
  const agenda = data.agenda || [];
  const isSample = data.is_sample_data;

  shadow.innerHTML = `
    <link rel="stylesheet" href="/static/icons/phosphor/regular/style.css">
    <link rel="stylesheet" href="/static/icons/phosphor/bold/style.css">
    <style>
      :host {
        display: block;
        width: 100%;
        height: 100%;
        box-sizing: border-box;
      }
      * {
        box-sizing: border-box;
        margin: 0;
        padding: 0;
      }
      .dashboard {
        display: flex;
        flex-direction: column;
        width: 100%;
        height: 100%;
        background: var(--surface, #ffffff);
        color: var(--text-primary, #111111);
        font-family: var(--font-family, system-ui, -apple-system, sans-serif);
        overflow: hidden;
      }

      /* Full-Width Top Header */
      .top-header {
        padding: 0.75rem 1.5rem 0.5rem;
        border-bottom: var(--stroke-2, 2px) solid var(--surface-sunken, #e5e5e5);
        background: var(--surface, #ffffff);
      }
      .header-weekday {
        font-size: 2.2rem;
        font-weight: 900;
        text-transform: uppercase;
        letter-spacing: -0.02em;
        line-height: 1;
        color: var(--accent-4, #1971c2);
      }

      .content-body {
        display: flex;
        flex: 1;
        min-height: 0;
        overflow: hidden;
      }
      
      /* Left Column: Date & Weather */
      .sidebar {
        width: 38%;
        height: 100%;
        border-right: var(--stroke-2, 2px) solid var(--surface-sunken, #e5e5e5);
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        padding: var(--space-4, 1.25rem);
      }
      .date-card {
        display: flex;
        flex-direction: column;
      }
      .day-number {
        font-size: 5.5rem;
        font-weight: 900;
        line-height: 0.9;
        letter-spacing: -0.04em;
        margin-bottom: 0.35rem;
      }
      .month-year {
        font-size: 1.25rem;
        font-weight: 600;
        color: var(--text-secondary, #555555);
      }

      .weather-card {
        background: var(--surface-sunken, #f8f9fa);
        border-radius: var(--radius-2, 6px);
        padding: 0.9rem;
        display: flex;
        flex-direction: column;
        gap: 0.35rem;
      }
      .weather-main {
        display: flex;
        align-items: center;
        gap: 0.75rem;
      }
      .weather-icon {
        font-size: 2.75rem;
        color: var(--text-primary, #111111);
      }
      .weather-hl-large {
        display: flex;
        gap: 0.5rem;
        font-size: 2.1rem;
        font-weight: 800;
        line-height: 1;
      }
      .arrow {
        font-size: 1.5rem;
        font-weight: 700;
        color: var(--text-secondary, #555555);
        margin-right: 1px;
      }
      .weather-condition {
        font-size: 1.05rem;
        font-weight: 700;
      }
      .weather-current {
        font-size: 0.95rem;
        color: var(--text-secondary, #555555);
        font-weight: 600;
      }

      /* Right Column: Calendar Agenda */
      .agenda-container {
        width: 62%;
        height: 100%;
        padding: var(--space-4, 1.5rem);
        display: flex;
        flex-direction: column;
        overflow: hidden;
      }
      .agenda-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 0.75rem;
        padding-bottom: 0.5rem;
        border-bottom: var(--stroke-1, 1px) solid var(--surface-sunken);
      }
      .agenda-title {
        font-size: 1.1rem;
        font-weight: 800;
        letter-spacing: 0.05em;
        display: flex;
        align-items: center;
        gap: 0.5rem;
      }
      .sample-pill {
        font-size: 0.75rem;
        font-weight: 700;
        background: var(--accent-1);
        color: var(--surface-sunken);
        padding: 2px 8px;
        border-radius: 999px;
      }
      .events-scroll {
        flex: 1;
        overflow-y: hidden; /* E-ink renders static snapshot */
        display: flex;
        flex-direction: column;
        gap: 0.85rem;
      }
      .day-group {
        display: flex;
        flex-direction: column;
        gap: 0.35rem;
      }
      .day-badge {
        font-size: 0.8rem;
        font-weight: 800;
        letter-spacing: 0.06em;
        color: var(--text-secondary);
      }
      .day-group.today .day-badge {
        color: var(--accent-4);
      }
      .event-row {
        display: flex;
        align-items: center;
        background: var(--surface-sunken);
        padding: 0.45rem 0.75rem;
        border-radius: var(--radius-1, 4px);
        gap: 0.6rem;
      }
      .event-time {
        font-size: 0.8rem;
        font-weight: 700;
        min-width: 65px;
        color: var(--text-secondary);
        flex-shrink: 0;
      }
      .event-time.all-day {
        font-weight: 800;
        color: var(--accent-4);
      }
      .event-title {
        font-size: 0.95rem;
        font-weight: 600;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .empty-notice {
        font-size: 0.95rem;
        font-style: italic;
        color: var(--text-muted);
        padding: 1rem 0;
      }
    </style>

    <div class="dashboard">
      <!-- Full-Width Top Header -->
      <header class="top-header">
        <div class="header-weekday">${dateInfo.weekday}</div>
      </header>

      <div class="content-body">
        <!-- Left Column: Day/Month & Weather -->
        <section class="sidebar">
          <div class="date-card">
            <div class="day-number">${dateInfo.day}</div>
            <div class="month-year">${dateInfo.month_year}</div>
          </div>

          <div class="weather-card">
            <div class="weather-main">
              <i class="ph-bold ${weather.icon || 'ph-sun'} weather-icon" aria-hidden="true"></i>
              <div class="weather-hl-large">
                <span><span class="arrow">↑</span>${weather.high}°</span>
                <span><span class="arrow">↓</span>${weather.low}°</span>
              </div>
            </div>
            <div class="weather-condition">${weather.condition}</div>
            <div class="weather-current">Currently ${weather.current_temp}${weather.unit}</div>
          </div>
        </section>

        <!-- Right Column: Agenda -->
        <section class="agenda-container">
          <div class="agenda-header">
            <div class="agenda-title">
              <i class="ph-bold ph-calendar-check" aria-hidden="true"></i>
              UPCOMING AGENDA
            </div>
            ${isSample ? `<div class="sample-pill">SAMPLE PREVIEW</div>` : ''}
          </div>

          <div class="events-scroll">
            ${agenda.length === 0 ? `
              <div class="empty-notice">No upcoming events scheduled.</div>
            ` : agenda.map(group => `
              <div class="day-group ${group.label === 'TODAY' ? 'today' : ''}">
                <div class="day-badge">${group.label}</div>
                ${group.events.map(ev => `
                  <div class="event-row">
                    <div class="event-time ${ev.is_all_day ? 'all-day' : ''}">${ev.time_str}</div>
                    <i class="ph-bold ${ev.icon || 'ph-calendar-blank'}" style="font-size: 0.95rem; flex-shrink: 0;" aria-hidden="true"></i>
                    <div class="event-title">${ev.title}</div>
                  </div>
                `).join('')}
              </div>
            `).join('')}
          </div>
        </section>
      </div>
    </div>
  `;
}