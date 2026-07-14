import { useEffect, useMemo, useState } from 'react';
import Panel from '../ui/Panel';
import StatusPill from '../ui/StatusPill';

const PAGE_SIZE = 10;

const STATUS_OPTIONS = [
  '',
  'waiting',
  'notified',
  'checked_in',
  'skipped',
];

function tomorrowISO() {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return d.toISOString().slice(0, 10);
}

function canReschedule(row) {
  if (['approved', 'rejected', 'waiting'].includes(row.status)) return false;
  return (
    Boolean(row.scheduled_date) ||
    ['notified', 'checked_in', 'skipped'].includes(row.status)
  );
}

export default function QueueTable({
  queue = [],
  status,
  search,
  busy = false,
  onStatusChange,
  onSearchChange,
  onReschedule,
}) {
  const [open, setOpen] = useState(false);
  const [page, setPage] = useState(0);
  const [dates, setDates] = useState({});

  const ordered = useMemo(
    () => [...queue].sort((a, b) => a.position - b.position || a.id - b.id),
    [queue]
  );

  const totalPages = Math.max(1, Math.ceil(ordered.length / PAGE_SIZE) || 1);
  const safePage = Math.min(page, totalPages - 1);
  const start = safePage * PAGE_SIZE;
  const pageRows = ordered.slice(start, start + PAGE_SIZE);
  const from = ordered.length === 0 ? 0 : start + 1;
  const to = Math.min(start + PAGE_SIZE, ordered.length);

  useEffect(() => {
    setPage(0);
  }, [status, search]);

  useEffect(() => {
    if (page > totalPages - 1) setPage(Math.max(0, totalPages - 1));
  }, [page, totalPages]);

  function dateFor(row) {
    return dates[row.id] || row.scheduled_date || tomorrowISO();
  }

  function openQueue() {
    setOpen(true);
    setPage(0);
  }

  if (!open) {
    return (
      <section className="queue-opener">
        <div className="queue-opener-copy">
          <p className="queue-opener-kicker">Live queue</p>
          <h2>Browse students in order</h2>
          <p>
            First-come first-served. Open the queue to review students in order.
            After you approve or reject with a secret code, they leave the queue
            automatically.
          </p>
          <dl className="queue-opener-meta">
            <div>
              <dt>In this view</dt>
              <dd>{ordered.length}</dd>
            </div>
            <div>
              <dt>Per page</dt>
              <dd>{PAGE_SIZE}</dd>
            </div>
          </dl>
        </div>
        <button type="button" className="btn queue-opener-btn" onClick={openQueue}>
          View top 10
        </button>
      </section>
    );
  }

  return (
    <Panel className="queue-browser">
      <div className="queue-browser-head">
        <div>
          <p className="queue-browser-kicker">Queue order</p>
          <h2>
            Students {from}–{to}
          </h2>
          <p className="muted">
            {ordered.length} student{ordered.length === 1 ? '' : 's'} · page{' '}
            {ordered.length ? safePage + 1 : 0} of {ordered.length ? totalPages : 0}
          </p>
        </div>
        <button type="button" className="btn btn-ghost" onClick={() => setOpen(false)}>
          Close
        </button>
      </div>

      <div className="table-tools queue-browser-tools">
        <div className="filters queue-browser-filters">
          <select value={status} onChange={(e) => onStatusChange(e.target.value)}>
            {STATUS_OPTIONS.map((s) => (
              <option key={s || 'all'} value={s}>
                {s ? s.replaceAll('_', ' ') : 'All statuses'}
              </option>
            ))}
          </select>
          <input
            value={search}
            onChange={(e) => onSearchChange(e.target.value.toUpperCase())}
            placeholder="Search by registration number"
            autoComplete="off"
            spellCheck={false}
            aria-label="Search by registration number"
          />
        </div>
      </div>

      {pageRows.length === 0 ? (
        <div className="queue-empty">
          <strong>No students in this view</strong>
          <p>Adjust filters or wait for students to join the queue.</p>
        </div>
      ) : (
        <ul className="queue-cards">
          {pageRows.map((row) => (
            <li key={row.id} className="queue-card">
              <div className="queue-card-top">
                <span className="queue-card-pos">#{row.position}</span>
                <StatusPill status={row.status} />
              </div>

              <div className="queue-card-identity">
                <strong>{row.student?.full_name || '—'}</strong>
                <span>{row.student?.registration_number || '—'}</span>
              </div>

              <div className="queue-card-grid">
                <div>
                  <span className="label">Faculty</span>
                  <strong>{row.student?.faculty || '—'}</strong>
                </div>
                <div>
                  <span className="label">Programme</span>
                  <strong>{row.student?.programme || '—'}</strong>
                </div>
                <div>
                  <span className="label">Email</span>
                  <strong>{row.student?.email || '—'}</strong>
                </div>
                <div>
                  <span className="label">Telephone</span>
                  <strong>{row.student?.phone || '—'}</strong>
                </div>
                <div>
                  <span className="label">Scheduled day</span>
                  <strong>{row.scheduled_date || 'Not assigned'}</strong>
                </div>
                <div>
                  <span className="label">Secret code</span>
                  <strong>
                    <code>{row.secret_code || '—'}</code>
                  </strong>
                </div>
              </div>

              {canReschedule(row) ? (
                <div className="queue-row-actions">
                  <input
                    type="date"
                    className="queue-row-date"
                    value={dateFor(row)}
                    min={new Date().toISOString().slice(0, 10)}
                    onChange={(e) =>
                      setDates((prev) => ({ ...prev, [row.id]: e.target.value }))
                    }
                    disabled={busy}
                  />
                  <button
                    type="button"
                    className="btn btn-tiny btn-primary"
                    disabled={busy}
                    onClick={() => onReschedule?.(row.id, dateFor(row))}
                  >
                    Reschedule
                  </button>
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      )}

      <div className="queue-pager">
        <button
          type="button"
          className="btn btn-queue-nav"
          disabled={safePage <= 0 || ordered.length === 0}
          onClick={() => setPage((p) => Math.max(0, p - 1))}
        >
          Back
        </button>
        <div className="queue-pager-status">
          <strong>
            {from}–{to}
          </strong>
          <span>of {ordered.length}</span>
        </div>
        <button
          type="button"
          className="btn btn-queue-nav btn-queue-nav-next"
          disabled={safePage >= totalPages - 1 || ordered.length === 0}
          onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
        >
          Next
        </button>
      </div>
    </Panel>
  );
}
