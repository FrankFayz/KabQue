import Panel from '../ui/Panel';
import Alert from '../ui/Alert';

/**
 * Notify waiting (unscheduled) students — batch leftovers are handled separately.
 */
export default function NotifyBatchForm({
  batchSize,
  scheduledDate,
  channel,
  busy,
  remaining = 0,
  leftovers = 0,
  error,
  message,
  onBatchSizeChange,
  onScheduledDateChange,
  onChannelChange,
  onSubmit,
}) {
  const unscheduled = Number(remaining) || 0;
  const carry = Number(leftovers) || 0;
  const requested = Number(batchSize) || 0;
  const canNotify = unscheduled > 0 || carry > 0;
  const overRequest = unscheduled > 0 && requested > unscheduled;

  return (
    <Panel title="Notify batch" className="desk-panel desk-panel-notify">
      <form onSubmit={onSubmit} className="stack-form">
        <p className="desk-panel-lead">
          <strong>{unscheduled}</strong> waiting
          {carry > 0 ? (
            <>
              {' '}
              · <strong>{carry}</strong> leftover in batch
            </>
          ) : null}
        </p>

        <div className="desk-form-row">
          <label>
            Students
            <input
              type="number"
              min={1}
              max={500}
              value={batchSize}
              onChange={(e) => onBatchSizeChange(e.target.value)}
              required
              disabled={busy}
            />
          </label>
          <label>
            Approval day
            <input
              type="date"
              value={scheduledDate}
              min={new Date().toISOString().slice(0, 10)}
              onChange={(e) => onScheduledDateChange(e.target.value)}
              required
              disabled={busy}
            />
          </label>
        </div>

        <label>
          Send via
          <select
            value={channel}
            onChange={(e) => onChannelChange(e.target.value)}
            disabled={busy}
            aria-label="Notification channel"
          >
            <option value="both">Email & SMS</option>
            <option value="email">Email only</option>
            <option value="sms">SMS only</option>
          </select>
        </label>

        {!canNotify ? (
          <p className="notify-warn">No students waiting to notify.</p>
        ) : null}
        {canNotify && unscheduled === 0 && carry > 0 ? (
          <p className="notify-warn notify-warn-info">
            Queue is empty — notify will use {carry} student
            {carry === 1 ? '' : 's'} still in a batch table.
          </p>
        ) : null}
        {overRequest ? (
          <p className="notify-warn">
            Only {unscheduled} waiting
            {carry > 0 ? ` (+${carry} leftover)` : ''}. We’ll take what’s available.
          </p>
        ) : null}

        <Alert>{error}</Alert>
        <Alert variant="info">{!error ? message : ''}</Alert>

        <button className="btn btn-primary" disabled={busy || !canNotify}>
          {busy ? 'Sending…' : 'Send notifications'}
        </button>
      </form>
    </Panel>
  );
}
