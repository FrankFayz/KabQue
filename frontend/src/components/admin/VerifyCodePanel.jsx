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
  const canDecideToday = Boolean(verified?.schedule_is_today);

  return (
    <Panel
      title="Check in"
      className={`desk-panel desk-panel-verify verify-panel${
        entry ? ' is-live' : ''
      }`}
    >
      <form onSubmit={onVerify} className="stack-form">
        <label>
          Secret code
          <input
            value={secretCode}
            onChange={(e) => onSecretCodeChange(e.target.value.toUpperCase())}
            placeholder="ABCD1234"
            autoComplete="off"
            spellCheck={false}
            required
            disabled={deskLocked && Boolean(entry)}
          />
        </label>
        <Alert>{error}</Alert>
        <Alert variant="info">{!error && !entry ? message : ''}</Alert>
        <button
          className="btn btn-primary"
          disabled={busy || !secretCode.trim()}
        >
          {busy ? 'Checking…' : 'Confirm'}
        </button>
      </form>

      {entry && student ? (
        <div className="verify-result">
          <div className="verify-result-top">
            <div>
              <h3>{student.full_name || '—'}</h3>
              <p className="verify-reg">{student.registration_number || '—'}</p>
            </div>
            <StatusPill status={entry.status} />
          </div>

          <div
            className={`verify-schedule${
              canDecideToday ? ' is-today' : ' is-other'
            }`}
          >
            <span className="label">Approval day</span>
            <strong>{entry.scheduled_date || 'Not assigned'}</strong>
            <p>{verified.schedule_note}</p>
          </div>

          <dl className="verify-facts">
            <div>
              <dt>Faculty</dt>
              <dd>{student.faculty || '—'}</dd>
            </div>
            <div>
              <dt>Programme</dt>
              <dd>{student.programme || '—'}</dd>
            </div>
            {(entry.position != null &&
              entry.status !== 'waiting' &&
              Number(entry.position) > 0) ||
            entry.secret_code ||
            secretCode ? (
              <div>
                <dt>Queue #</dt>
                <dd>
                  {entry.position != null &&
                  entry.status !== 'waiting' &&
                  Number(entry.position) > 0
                    ? `#${entry.position}`
                    : '—'}
                </dd>
              </div>
            ) : null}
          </dl>

          <div className="cta-row verify-cta">
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => onComplete('approved')}
              disabled={deskLocked || !canDecideToday}
              aria-busy={completeBusy === 'approved'}
              title={
                canDecideToday
                  ? 'Accept documents and finish visit'
                  : 'Only today’s schedule can be approved'
              }
            >
              {completeBusy === 'approved' ? 'Approving…' : 'Approve'}
            </button>
            <button
              type="button"
              className="btn btn-danger-outline"
              onClick={() => onComplete('rejected')}
              disabled={deskLocked || !canDecideToday}
              aria-busy={completeBusy === 'rejected'}
              title={
                canDecideToday
                  ? 'Remove from today’s queue'
                  : 'Only today’s schedule can be deleted'
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
              title="Return to waiting for a later day"
            >
              {completeBusy === 'back_to_queue' ? 'Returning…' : 'Back to queue'}
            </button>
          </div>
        </div>
      ) : null}
    </Panel>
  );
}
