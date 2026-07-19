import { useEffect, useState } from 'react';
import Panel from '../ui/Panel';
import Alert from '../ui/Alert';
import StatusPill from '../ui/StatusPill';

function defaultTomorrow() {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return d.toISOString().slice(0, 10);
}

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

function ReschedulePanel({
  maxCount,
  busy,
  error,
  message,
  onSubmit,
  onCancel,
}) {
  const [count, setCount] = useState(String(Math.max(1, maxCount || 1)));
  const [date, setDate] = useState(defaultTomorrow);

  useEffect(() => {
    setCount(String(Math.max(1, maxCount || 1)));
  }, [maxCount]);

  function handleSubmit(e) {
    e.preventDefault();
    onSubmit({
      count: Number(count),
      scheduledDate: date,
    });
  }

  const over = Number(count) > maxCount;

  return (
    <form className="batch-reschedule" onSubmit={handleSubmit}>
      <div className="batch-reschedule-copy">
        <h3>Move remaining</h3>
        <p>
          Move unfinished students to a new day. They get fresh queue numbers and
          codes.
        </p>
      </div>

      <div className="batch-reschedule-fields">
        <label>
          How many
          <input
            type="number"
            min={1}
            max={Math.max(1, maxCount)}
            value={count}
            onChange={(e) => setCount(e.target.value)}
            required
            disabled={busy || maxCount < 1}
          />
        </label>
        <label>
          New day
          <input
            type="date"
            value={date}
            min={todayISO()}
            onChange={(e) => setDate(e.target.value)}
            required
            disabled={busy || maxCount < 1}
          />
        </label>
      </div>

      <p className="batch-reschedule-hint">
        {maxCount < 1
          ? 'Nothing left to move.'
          : over
            ? `Only ${maxCount} remain.`
            : `${maxCount} awaiting · numbered 1–${count || 'N'} on the new day`}
      </p>

      <Alert>{error}</Alert>
      <Alert variant="info">{!error ? message : ''}</Alert>

      <div className="batch-reschedule-actions">
        <button type="button" className="btn btn-ghost" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
        <button
          type="submit"
          className="btn batch-reschedule-submit"
          disabled={busy || maxCount < 1 || !count || Number(count) < 1}
        >
          {busy ? 'Moving…' : 'Confirm move'}
        </button>
      </div>
    </form>
  );
}

function RowReschedule({ entryId, busy, onReschedule }) {
  const [date, setDate] = useState(defaultTomorrow);

  return (
    <div className="batch-row-reschedule">
      <input
        type="date"
        value={date}
        min={todayISO()}
        onChange={(e) => setDate(e.target.value)}
        disabled={busy}
        aria-label="New approval date"
      />
      <button
        type="button"
        className="btn btn-tiny btn-primary"
        disabled={busy || !date}
        onClick={() => onReschedule?.(entryId, date)}
      >
        Move
      </button>
    </div>
  );
}

export default function BatchResultTable({
  result,
  onBatchReschedule,
  onStudentReschedule,
  rescheduleBusy = false,
  rescheduleError = '',
  rescheduleMessage = '',
  studentRescheduleBusy = false,
}) {
  const [rescheduleOpen, setRescheduleOpen] = useState(false);
  const students = result?.students || [];
  const batchId = result?.batch?.id;
  const remaining = result?.remaining_in_batch ?? students.length;
  const canReschedule = Boolean(batchId && onBatchReschedule && remaining > 0);
  const scheduled =
    result?.batch?.scheduled_date || students[0]?.scheduled_date || '—';
  const dayPassed =
    Boolean(scheduled) &&
    scheduled !== '—' &&
    scheduled < todayISO() &&
    remaining > 0;
  const isRescheduleResult = Boolean(result?.rescheduled);
  const mode = result?.channel || 'both';
  const smsFailed =
    Number(result?.sms_failed || 0) > 0 && (mode === 'sms' || mode === 'both');
  const emailFailed =
    Number(result?.emails_failed || 0) > 0 &&
    (mode === 'email' || mode === 'both');

  useEffect(() => {
    setRescheduleOpen(false);
  }, [batchId]);

  useEffect(() => {
    if (dayPassed && canReschedule) setRescheduleOpen(true);
  }, [dayPassed, canReschedule, batchId]);

  if (!result?.batch) {
    return (
      <div className="desk-empty-card" role="status">
        <strong>No active batch</strong>
        <p>Notify a group above — their codes and day will show here.</p>
      </div>
    );
  }

  async function handleRescheduleSubmit({ count, scheduledDate }) {
    if (!onBatchReschedule) return;
    const ok = await onBatchReschedule({
      batchId,
      count,
      scheduledDate,
    });
    if (ok) setRescheduleOpen(false);
  }

  return (
    <Panel wide className="batch-browser desk-panel">
      <div className="batch-browser-head">
        <div>
          <h2>
            {remaining > 0
              ? isRescheduleResult
                ? 'Moved batch · awaiting desk'
                : 'Awaiting desk'
              : 'Batch cleared'}
          </h2>
          <p className="batch-browser-meta">
            <span>
              <strong>{remaining}</strong> left
            </span>
            <span aria-hidden="true">·</span>
            <span>
              Day <strong>{scheduled}</strong>
            </span>
            {result.carried_from_batch ? (
              <>
                <span aria-hidden="true">·</span>
                <span>{result.carried_from_batch} carried forward</span>
              </>
            ) : null}
          </p>
        </div>
        <div className="batch-browser-actions">
          {canReschedule ? (
            <button
              type="button"
              className="btn batch-browser-reschedule"
              onClick={() => setRescheduleOpen((v) => !v)}
              disabled={rescheduleBusy}
            >
              {rescheduleOpen ? 'Cancel move' : 'Move remaining'}
            </button>
          ) : null}
        </div>
      </div>

      {rescheduleOpen ? (
        <ReschedulePanel
          maxCount={remaining}
          busy={rescheduleBusy}
          error={rescheduleError}
          message={rescheduleMessage}
          onSubmit={handleRescheduleSubmit}
          onCancel={() => setRescheduleOpen(false)}
        />
      ) : null}

      {dayPassed ? (
        <Alert>
          Day {scheduled} has ended. Move remaining students to today or a future
          day before approving.
        </Alert>
      ) : null}

      {result.message && remaining > 0 ? (
        <Alert variant="info">{result.message}</Alert>
      ) : null}
      {result.shortage ? (
        <Alert>
          Asked for {result.requested}, only {result.available} available — all
          seats filled.
        </Alert>
      ) : null}
      {emailFailed ? (
        <Alert>Email failed for {result.emails_failed} student(s).</Alert>
      ) : null}
      {smsFailed ? (
        <Alert>
          SMS failed for {result.sms_failed} student
          {result.sms_failed === 1 ? '' : 's'}. Keep the gateway phone online,
          then try again.
        </Alert>
      ) : null}

      <div className="batch-summary-grid batch-summary-compact">
        <div className="batch-stat">
          <span className="label">Emails</span>
          <strong>
            {result.delivery_pending
              ? `${result.emails_sent ?? 0}…`
              : (result.emails_sent ?? 0)}
          </strong>
        </div>
        <div className="batch-stat">
          <span className="label">SMS</span>
          <strong>
            {result.delivery_pending
              ? `${result.sms_sent ?? 0}…`
              : (result.sms_sent ?? 0)}
          </strong>
        </div>
      </div>
      {result.delivery_pending ? (
        <p className="hint batch-delivery-hint">Updating delivery totals…</p>
      ) : null}

      {remaining === 0 ? (
        <p className="batch-empty-note">
          Everyone from this batch was approved, deleted, or moved.
        </p>
      ) : (
        <div className="table-wrap batch-table-wrap">
          <table className="batch-table batch-table-smart">
            <thead>
              <tr>
                <th>#</th>
                <th>Student</th>
                <th>Status</th>
                <th>Code</th>
                <th>Move</th>
              </tr>
            </thead>
            <tbody>
              {students.map((s) => (
                <tr
                  key={`${s.queue_entry_id || s.registration_number}-${s.secret_code}`}
                >
                  <td>
                    <span className="batch-pos">#{s.position}</span>
                  </td>
                  <td>
                    <strong className="batch-name">{s.full_name || '—'}</strong>
                    <span className="batch-sub">
                      {s.registration_number || '—'}
                      {s.phone ? ` · ${s.phone}` : ''}
                    </span>
                  </td>
                  <td>
                    <StatusPill status={s.status || 'notified'} />
                  </td>
                  <td>
                    <code className="batch-code">{s.secret_code || '—'}</code>
                  </td>
                  <td>
                    {s.queue_entry_id && onStudentReschedule ? (
                      <RowReschedule
                        entryId={s.queue_entry_id}
                        busy={studentRescheduleBusy || rescheduleBusy}
                        onReschedule={onStudentReschedule}
                      />
                    ) : (
                      '—'
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}
