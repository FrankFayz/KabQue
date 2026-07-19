import { useEffect, useMemo, useState } from 'react';
import Panel from '../ui/Panel';
import StatusPill from '../ui/StatusPill';

const PAGE_SIZE = 10;

const STATUS_OPTIONS = [
  { value: '', label: 'Waiting (unscheduled)' },
  { value: 'notified', label: 'Scheduled · notified' },
  { value: 'checked_in', label: 'Scheduled · checked in' },
  { value: 'skipped', label: 'Scheduled · skipped' },
  { value: 'all', label: 'All live' },
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
  const [page, setPage] = useState(0);
  const [dates, setDates] = useState({});

  const ordered = useMemo(
    () =>
      [...queue].sort((a, b) => {
        const aTime = new Date(a.created_at || 0).getTime();
        const bTime = new Date(b.created_at || 0).getTime();
        if (aTime !== bTime) return aTime - bTime;
        return (a.id || 0) - (b.id || 0);
      }),
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

  return (
    <Panel className="queue-browser desk-panel">
      <div className="queue-browser-head">
        <div>
          <h2>Queue</h2>
          <p className="muted">
            {ordered.length === 0
              ? 'No students in this view'
              : `${from}–${to} of ${ordered.length}`}
          </p>
        </div>
      </div>

      <div className="table-tools queue-browser-tools">
        <div className="filters queue-browser-filters">
          <select
            value={status}
            onChange={(e) => onStatusChange(e.target.value)}
            aria-label="Filter by status"
          >
            {STATUS_OPTIONS.map((s) => (
              <option key={s.value || 'queue'} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
          <input
            value={search}
            onChange={(e) => onSearchChange(e.target.value.toUpperCase())}
            placeholder="Reg. number"
            autoComplete="off"
            spellCheck={false}
            aria-label="Search by registration number"
          />
        </div>
      </div>

      {pageRows.length === 0 ? (
        <div className="queue-empty">
          <strong>No students here</strong>
          <p>Change the filter or wait for new joiners.</p>
        </div>
      ) : (
        <ul className="queue-cards">
          {pageRows.map((row) => (
            <li key={row.id} className="queue-card queue-card-smart">
              <div className="queue-card-top">
                <span
                  className={`queue-card-pos${
                    row.position != null &&
                    row.status !== 'waiting' &&
                    Number(row.position) > 0
                      ? ''
                      : ' is-queued'
                  }`}
                >
                  {row.position != null &&
                  row.status !== 'waiting' &&
                  Number(row.position) > 0
                    ? `#${row.position}`
                    : 'Waiting'}
                </span>
                <StatusPill status={row.status} />
              </div>

              <div className="queue-card-identity">
                <strong>{row.student?.full_name || '—'}</strong>
                <span>{row.student?.registration_number || '—'}</span>
              </div>

              <p className="queue-card-line">
                {[row.student?.faculty, row.student?.programme]
                  .filter(Boolean)
                  .join(' · ') || '—'}
              </p>

              <div className="queue-card-meta">
                <span>{row.scheduled_date || 'No day yet'}</span>
                {row.secret_code ? <code>{row.secret_code}</code> : null}
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
                    Move
                  </button>
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      )}

      {ordered.length > PAGE_SIZE ? (
        <div className="queue-pager">
          <button
            type="button"
            className="btn btn-queue-nav"
            disabled={safePage <= 0}
            onClick={() => setPage((p) => Math.max(0, p - 1))}
          >
            Back
          </button>
          <div className="queue-pager-status">
            <strong>
              {safePage + 1}/{totalPages}
            </strong>
          </div>
          <button
            type="button"
            className="btn btn-queue-nav btn-queue-nav-next"
            disabled={safePage >= totalPages - 1}
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
          >
            Next
          </button>
        </div>
      ) : null}
    </Panel>
  );
}
