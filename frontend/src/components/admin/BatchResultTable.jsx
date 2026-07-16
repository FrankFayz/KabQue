import { useEffect, useState } from 'react';
import Panel from '../ui/Panel';
import Alert from '../ui/Alert';
import StatusPill from '../ui/StatusPill';

function deliveryLabel(channel) {
  if (!channel) return null;
  if (channel.success) {
    return { ok: true, text: `${String(channel.channel || '').toUpperCase()} delivered` };
  }
  return {
    ok: false,
    text: `${String(channel.channel || 'Message').toUpperCase()} could not be sent`,
  };
}

function defaultTomorrow() {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return d.toISOString().slice(0, 10);
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
        <p className="batch-reschedule-kicker">End-of-day / carry forward</p>
        <h3>Reschedule remaining students</h3>
        <p>
          Only students still in this table (not yet approved) are moved. Enter how
          many and the new day — they receive fresh queue numbers 1–N and new secret
          codes.
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
            min={new Date().toISOString().slice(0, 10)}
            onChange={(e) => setDate(e.target.value)}
            required
            disabled={busy || maxCount < 1}
          />
        </label>
      </div>

      <p className="batch-reschedule-hint">
        {maxCount < 1
          ? 'No remaining students — all were approved or already moved.'
          : over
            ? `Only ${maxCount} remain in this batch table.`
            : `${maxCount} remaining · will be numbered 1–${count || 'N'} on the new day`}
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

export default function BatchResultTable({
  result,
  onBatchReschedule,
  rescheduleBusy = false,
  rescheduleError = '',
  rescheduleMessage = '',
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
  const isRescheduleResult = Boolean(result?.rescheduled);
  const mode = result?.channel || 'both';
  const smsFailed =
    Number(result?.sms_failed || 0) > 0 && (mode === 'sms' || mode === 'both');
  const emailFailed =
    Number(result?.emails_failed || 0) > 0 &&
    (mode === 'email' || mode === 'both');

  // Keep the table open while the batch id is steady — only reset when a new batch arrives
  useEffect(() => {
    setRescheduleOpen(false);
    setOpen(true);
  }, [batchId]);

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
    ? `${remaining} student${remaining === 1 ? '' : 's'} still in this batch for ${scheduled}. Approved students leave the table; reschedule remaining ones onto a new day when ready.`
    : `All students from this batch have been approved or moved. Nothing left to reschedule.`;

  if (!open) {
    return (
      <section className="batch-opener" aria-label="Open batch results">
        <div className="batch-opener-copy">
          <p className="batch-opener-kicker">Live batch table</p>
          <h2>
            {remaining > 0
              ? `${remaining} remaining · day ${scheduled}`
              : 'Batch cleared'}
          </h2>
          <p>{openerCopy}</p>
          <dl className="batch-opener-meta">
            <div>
              <dt>Remaining</dt>
              <dd>{remaining}</dd>
            </div>
            <div>
              <dt>Day</dt>
              <dd className="batch-opener-day">{scheduled}</dd>
            </div>
            {result.carried_from_batch != null ? (
              <div>
                <dt>Carried in</dt>
                <dd>{result.carried_from_batch}</dd>
              </div>
            ) : null}
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
                ? 'Rescheduled — pending approval'
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
          {Number(result.emails_sent || 0) > 0
            ? ' Email may still have gone through.'
            : ''}
        </Alert>
      ) : null}

      <div className="batch-summary-grid">
        <div className="batch-stat">
          <span className="label">Still in table</span>
          <strong>{remaining}</strong>
        </div>
        <div className="batch-stat">
          <span className="label">Approval day</span>
          <strong className="batch-stat-date">{scheduled}</strong>
        </div>
        <div className="batch-stat">
          <span className="label">Emails sent</span>
          <strong>{result.emails_sent ?? 0}</strong>
        </div>
        <div className="batch-stat">
          <span className="label">SMS sent</span>
          <strong>{result.sms_sent ?? 0}</strong>
        </div>
      </div>

      {remaining === 0 ? (
        <p className="batch-empty-note">
          No students remain. Everyone from this batch was approved, rejected, or
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
                <th>Phone</th>
                <th>Secret code</th>
                <th>Delivery</th>
              </tr>
            </thead>
            <tbody>
              {students.map((s) => {
                const emailChannel = (s.channels || []).find((c) => c.channel === 'email');
                const smsChannel = (s.channels || []).find((c) => c.channel === 'sms');
                const parts = [deliveryLabel(emailChannel), deliveryLabel(smsChannel)].filter(
                  Boolean
                );
                return (
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
                      <div className="batch-delivery">
                        {parts.length
                          ? parts.map((p) => (
                              <span
                                key={p.text}
                                className={`batch-delivery-pill${p.ok ? ' is-ok' : ' is-bad'}`}
                              >
                                {p.text}
                              </span>
                            ))
                          : '—'}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}
