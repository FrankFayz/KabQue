import StatusPill from '../ui/StatusPill';
import Panel from '../ui/Panel';
import Alert from '../ui/Alert';

export default function VerifyCodePanel({
  secretCode,
  verified,
  busy,
  completeBusy = null,
  error,
  message,
  onSecretCodeChange,
  onVerify,
  onComplete,
}) {
  const entry = verified?.entry;
  const student = entry?.student;
  const deskLocked = Boolean(busy || completeBusy);

  return (
    <Panel title="Confirm identity" className="verify-panel">
      <form onSubmit={onVerify} className="stack-form">
        <p className="muted">
          Enter the secret code from the fresher’s email or SMS. A valid code
          confirms who they are and shows their assigned day.
        </p>
        <label>
          Secret code
          <input
            value={secretCode}
            onChange={(e) => onSecretCodeChange(e.target.value.toUpperCase())}
            placeholder="ABCD1234"
            autoComplete="off"
            spellCheck={false}
            required
          />
        </label>
        <Alert>{error}</Alert>
        <Alert variant="info">{!error ? message : ''}</Alert>
        <button className="btn btn-primary" disabled={busy || !secretCode.trim()}>
          {busy ? 'Checking…' : 'Confirm identity'}
        </button>
      </form>

      {entry && student ? (
        <div className="verify-result">
          <div className="verify-result-top">
            <div>
              <p className="verify-result-kicker">Fresher confirmed</p>
              <h3>{student.full_name || '—'}</h3>
              <p className="muted">{student.registration_number || '—'}</p>
            </div>
            <StatusPill status={entry.status} />
          </div>

          <div
            className={`verify-schedule${
              verified.schedule_is_today ? ' is-today' : ' is-other'
            }`}
          >
            <span className="label">Scheduled day</span>
            <strong>{entry.scheduled_date || 'Not assigned'}</strong>
            <p>{verified.schedule_note}</p>
          </div>

          <div className="verify-grid">
            <div>
              <span className="label">Queue number</span>
              <strong>
                {entry.position != null &&
                entry.status !== 'waiting' &&
                Number(entry.position) > 0
                  ? `#${entry.position}`
                  : 'Not assigned yet'}
              </strong>
            </div>
            <div>
              <span className="label">Faculty</span>
              <strong>{student.faculty || '—'}</strong>
            </div>
            <div>
              <span className="label">Programme</span>
              <strong>{student.programme || '—'}</strong>
            </div>
            <div>
              <span className="label">Email</span>
              <strong>{student.email || '—'}</strong>
            </div>
            <div>
              <span className="label">Telephone</span>
              <strong>{student.phone || '—'}</strong>
            </div>
            <div>
              <span className="label">Secret code</span>
              <strong>
                <code>{entry.secret_code || secretCode}</code>
              </strong>
            </div>
          </div>

          <p className="muted verify-auto-leave">
            Approve finishes the visit. Delete removes them from today’s queue.
            Back to queue returns them to waiting for a later schedule.
          </p>

          <div className="cta-row">
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => onComplete('approved')}
              disabled={deskLocked || !verified?.schedule_is_today}
              aria-busy={completeBusy === 'approved'}
              title={
                verified?.schedule_is_today
                  ? 'Accept documents and clear them from today’s queue'
                  : 'Only students scheduled for today can be approved'
              }
            >
              {completeBusy === 'approved' ? 'Approving…' : 'Approve'}
            </button>
            <button
              type="button"
              className="btn btn-danger-outline"
              onClick={() => onComplete('rejected')}
              disabled={deskLocked || !verified?.schedule_is_today}
              aria-busy={completeBusy === 'rejected'}
              title={
                verified?.schedule_is_today
                  ? 'Remove this fresher from today’s queue (documents not accepted)'
                  : 'Only students scheduled for today can be deleted'
              }
            >
              {completeBusy === 'rejected' ? 'Deleting…' : 'Delete'}
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => onComplete('back_to_queue')}
              disabled={deskLocked}
              aria-busy={completeBusy === 'back_to_queue'}
              title="Return them to the waiting queue for a later schedule"
            >
              {completeBusy === 'back_to_queue' ? 'Returning…' : 'Back to queue'}
            </button>
          </div>
        </div>
      ) : null}
    </Panel>
  );
}
