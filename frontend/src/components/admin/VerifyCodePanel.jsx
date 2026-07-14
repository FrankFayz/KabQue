import Panel from '../ui/Panel';

export default function VerifyCodePanel({
  secretCode,
  verified,
  busy,
  onSecretCodeChange,
  onVerify,
  onComplete,
}) {
  return (
    <Panel title="Verify secret code">
      <form onSubmit={onVerify} className="stack-form">
        <p className="muted">Student presents the code from their notification.</p>
        <label>
          Secret code
          <input
            value={secretCode}
            onChange={(e) => onSecretCodeChange(e.target.value.toUpperCase())}
            placeholder="ABCD1234"
            required
          />
        </label>
        <button className="btn btn-primary" disabled={busy}>
          Confirm identity
        </button>
      </form>

      {verified?.entry && (
        <div className="verify-card">
          <p>
            <strong>{verified.entry.student.full_name}</strong>
          </p>
          <p className="muted">
            {verified.entry.student.registration_number} · Position #
            {verified.entry.position}
          </p>
          <p className="muted">
            {verified.entry.student.faculty} · {verified.entry.student.programme}
          </p>
          <div className="cta-row">
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => onComplete('approved')}
              disabled={busy}
            >
              Approve docs
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
              onClick={() => onComplete('skipped')}
              disabled={busy}
            >
              No-show
            </button>
          </div>
        </div>
      )}
    </Panel>
  );
}
