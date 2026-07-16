import Panel from '../ui/Panel';
import Alert from '../ui/Alert';

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
  const waiting = Number(remaining) || 0;
  const carry = Number(leftovers) || 0;
  const pool = waiting + carry;
  const requested = Number(batchSize) || 0;
  const overRequest = pool > 0 && requested > pool;
  const noneAvailable = pool === 0;

  return (
    <Panel title="Notify next batch">
      <form onSubmit={onSubmit} className="stack-form">
        <div className={`notify-remaining-banner${pool > 0 ? ' has-pool' : ''}`}>
          <span className="label">Available to schedule</span>
          <strong>{pool}</strong>
          <span className="notify-pool-breakdown">
            {carry > 0 ? `${carry} still in batch table` : null}
            {carry > 0 && waiting > 0 ? ' · ' : null}
            {waiting > 0 || carry === 0
              ? `${waiting} waiting joiner${waiting === 1 ? '' : 's'}`
              : null}
          </span>
        </div>

        <label>
          How many students
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

        {noneAvailable ? (
          <p className="notify-warn">
            Nothing to notify. Waiting queue is empty and no unapproved students
            remain in a batch table.
          </p>
        ) : null}
        {!noneAvailable && waiting === 0 && carry > 0 ? (
          <p className="notify-warn notify-warn-info">
            No new waiting joiners — the next batch will include the {carry}{' '}
            student{carry === 1 ? '' : 's'} still in a batch table.
          </p>
        ) : null}
        {overRequest ? (
          <p className="notify-warn">
            Only {pool} student{pool === 1 ? '' : 's'} available. The system
            will notify all {pool} (carry-overs first, then waiting).
          </p>
        ) : null}

        <label>
          Approval date
          <input
            type="date"
            value={scheduledDate}
            min={new Date().toISOString().slice(0, 10)}
            onChange={(e) => onScheduledDateChange(e.target.value)}
            required
            disabled={busy}
          />
        </label>
        <label>
          Channel
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

        <Alert>{error}</Alert>
        <Alert variant="info">{!error ? message : ''}</Alert>

        <button className="btn btn-primary" disabled={busy || noneAvailable}>
          {busy ? 'Sending…' : 'Send notifications'}
        </button>
      </form>
    </Panel>
  );
}
