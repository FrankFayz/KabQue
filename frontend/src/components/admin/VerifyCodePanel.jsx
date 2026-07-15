import StatusPill from '../ui/StatusPill';
import Panel from '../ui/Panel';
import Alert from '../ui/Alert';

export default function VerifyCodePanel({
  secretCode,
  verified,
  busy,
  error,
  message,
  onSecretCodeChange,
  onVerify,
  onComplete,
}) {
  const entry = verified?.entry;
  const student = entry?.student;

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
            Approve or Reject finishes the visit. Back to queue returns them to
            waiting for a later schedule.
          </p>

          <div className="cta-row">
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => onComplete('approved')}
              disabled={busy}
            >
              Approve
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => onComplete('rejected')}
              disabled={busy}
            >
              Reject
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => onComplete('back_to_queue')}
              disabled={busy}
            >
              Back to queue
            </button>
          </div>
        </div>
      ) : null}
    </Panel>
  );
}
