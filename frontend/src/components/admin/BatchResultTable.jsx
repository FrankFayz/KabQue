import { useEffect, useState } from 'react';
import Panel from '../ui/Panel';
import Alert from '../ui/Alert';
import StatusPill from '../ui/StatusPill';

function deliveryLabel(channel) {
  if (!channel) return null;
  const dest = (channel.destination || '').trim();
  if (channel.success) {
    if (channel.channel === 'sms' && dest) {
      return { ok: true, text: `SMS → ${dest}` };
    }
    if (channel.channel === 'email' && dest) {
      return { ok: true, text: `Email → ${dest}` };
    }
    return { ok: true, text: `${String(channel.channel || '').toUpperCase()} delivered` };
  }
  const prefix =
    channel.channel === 'sms' && dest
      ? `SMS ${dest}`
      : String(channel.channel || 'Message').toUpperCase();
  return {
    ok: false,
    text: `${prefix} could not be sent`,
  };
}

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
        <p className="batch-reschedule-kicker">Awaiting desk approval</p>
        <h3>Reschedule remaining students</h3>
        <p>
          Anyone still in this table (not approved or deleted) can move to a new
          day. They get fresh queue numbers 1–N and new secret codes.
        </p>
      </div>

      <div className="batch-reschedule-fields">
        <label>
          Students to move
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
          New approval date
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
          ? 'No remaining students — all were approved, deleted, or already moved.'
          : over
            ? `Only ${maxCount} remain awaiting desk approval.`
            : `${maxCount} awaiting · will be numbered 1–${count || 'N'} on the new day`}
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
          {busy ? 'Rescheduling…' : 'Confirm reschedule'}
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
        Reschedule
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
  const [open, setOpen] = useState(true);
  const [rescheduleOpen, setRescheduleOpen] = useState(false);
  const students = result?.students || [];
  const batchId = result?.batch?.id;
  const remaining = result?.remaining_in_batch ?? students.length;
  const canReschedule = Boolean(batchId && onBatchReschedule && remaining > 0);
  const scheduled =
    result?.batch?.scheduled_date ||
    students[0]?.scheduled_date ||
    '—';
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
    setOpen(true);
  }, [batchId]);

  // Past approval day with people still waiting → open reschedule so it is obvious
  useEffect(() => {
    if (dayPassed && canReschedule) setRescheduleOpen(true);
  }, [dayPassed, canReschedule, batchId]);

  if (!result?.batch) return null;

  async function handleRescheduleSubmit({ count, scheduledDate }) {
    if (!onBatchReschedule) return;
    const ok = await onBatchReschedule({
      batchId,
      count,
      scheduledDate,
    });
    if (ok) setRescheduleOpen(false);
  }

  const rescheduleForm = rescheduleOpen ? (
    <ReschedulePanel
      maxCount={remaining}
      busy={rescheduleBusy}
      error={rescheduleError}
      message={rescheduleMessage}
      onSubmit={handleRescheduleSubmit}
      onCancel={() => setRescheduleOpen(false)}
    />
  ) : null;

  const openerCopy = remaining > 0
    ? `${remaining} student${remaining === 1 ? '' : 's'} still awaiting desk approval for ${scheduled}. Reschedule any who were not finished that day onto a new date.`
    : `All students from this batch have been approved, deleted, or moved. Nothing left to reschedule.`;

  if (!open) {
    return (
      <section className="batch-opener" aria-label="Open batch results">
        <div className="batch-opener-copy">
          <p className="batch-opener-kicker">Awaiting desk approval</p>
          <h2>
            {remaining > 0
              ? `${remaining} remaining · day ${scheduled}`
              : 'Batch cleared'}
          </h2>
          <p>{openerCopy}</p>
          {dayPassed ? (
            <p className="batch-day-ended">
              Approval day has passed — reschedule remaining students to continue.
            </p>
          ) : null}
          <dl className="batch-opener-meta">
            <div>
              <dt>Remaining</dt>
              <dd>{remaining}</dd>
            </div>
            <div>
              <dt>Day</dt>
              <dd className="batch-opener-day">{scheduled}</dd>
            </div>
          </dl>
        </div>
        <div className="batch-opener-actions">
          <button
            type="button"
            className="btn batch-opener-btn"
            onClick={() => setOpen(true)}
          >
            View batch table
          </button>
          {canReschedule ? (
            <button
              type="button"
              className="btn batch-opener-reschedule"
              onClick={() => setRescheduleOpen((v) => !v)}
              disabled={rescheduleBusy}
            >
              {rescheduleOpen ? 'Hide reschedule' : 'Reschedule remaining'}
            </button>
          ) : null}
        </div>
        {rescheduleForm}
      </section>
    );
  }

  return (
    <Panel wide className="batch-browser">
      <div className="batch-browser-head">
        <div>
          <p className="batch-browser-kicker">Live batch table</p>
          <h2>
            {remaining > 0
              ? isRescheduleResult
                ? 'Rescheduled — awaiting desk approval'
                : 'Awaiting desk approval'
              : 'Batch cleared'}
          </h2>
          <p className="muted">
            {remaining} remaining · day {scheduled}
            {result.carried_from_batch
              ? ` · ${result.carried_from_batch} carried from prior batch`
              : ''}
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
              {rescheduleOpen ? 'Hide reschedule' : 'Reschedule remaining'}
            </button>
          ) : null}
          <button type="button" className="btn btn-ghost" onClick={() => setOpen(false)}>
            Collapse
          </button>
        </div>
      </div>

      {rescheduleForm}

      {dayPassed ? (
        <Alert>
          Approval day {scheduled} has ended. Students still here cannot be
          approved until you reschedule them onto today or a future day.
        </Alert>
      ) : null}

      <Alert variant="info">{result.message || openerCopy}</Alert>
      {result.shortage ? (
        <Alert>
          Requested {result.requested}, only {result.available} available — all
          available seats were filled (batch leftovers first, then waiting).
        </Alert>
      ) : null}
      {emailFailed ? (
        <Alert>Email failed for {result.emails_failed} student(s).</Alert>
      ) : null}
      {smsFailed ? (
        <Alert>
          SMS could not be delivered for {result.sms_failed} student
          {result.sms_failed === 1 ? '' : 's'}
          {Array.isArray(result.sms_errors) && result.sms_errors[0]
            ? `: ${result.sms_errors[0]}`
            : '. Open the MySMSGate app on the gateway phone and keep it online.'}
        </Alert>
      ) : null}

      <div className="batch-summary-grid">
        <div className="batch-stat">
          <span className="label">Still awaiting</span>
          <strong>{remaining}</strong>
        </div>
        <div className="batch-stat">
          <span className="label">Approval day</span>
          <strong className="batch-stat-date">{scheduled}</strong>
        </div>
        <div className="batch-stat">
          <span className="label">Emails sent</span>
          <strong>
            {result.delivery_pending
              ? `${result.emails_sent ?? 0}…`
              : (result.emails_sent ?? 0)}
          </strong>
        </div>
        <div className="batch-stat">
          <span className="label">SMS sent</span>
          <strong>
            {result.delivery_pending
              ? `${result.sms_sent ?? 0}…`
              : (result.sms_sent ?? 0)}
          </strong>
        </div>
      </div>
      {result.delivery_pending ? (
        <p className="hint batch-delivery-hint">
          Confirming email and SMS delivery — totals update as messages go out.
        </p>
      ) : null}

      {remaining === 0 ? (
        <p className="batch-empty-note">
          No students remain. Everyone from this batch was approved, deleted, or
          moved to another day.
        </p>
      ) : (
        <div className="table-wrap batch-table-wrap">
          <table className="batch-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Name</th>
                <th>Reg. no.</th>
                <th>Status</th>
                <th>Email</th>
                <th>SMS to</th>
                <th>Secret code</th>
                <th>Reschedule</th>
              </tr>
            </thead>
            <tbody>
              {students.map((s) => (
                <tr key={`${s.queue_entry_id || s.registration_number}-${s.secret_code}`}>
                  <td>
                    <span className="batch-pos">#{s.position}</span>
                  </td>
                  <td>
                    <strong className="batch-name">{s.full_name || '—'}</strong>
                  </td>
                  <td>{s.registration_number}</td>
                  <td>
                    <StatusPill status={s.status || 'notified'} />
                  </td>
                  <td className="batch-contact">{s.email || '—'}</td>
                  <td className="batch-contact">{s.phone || '—'}</td>
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
