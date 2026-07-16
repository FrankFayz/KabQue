import Panel from '../ui/Panel';
import Alert from '../ui/Alert';

/**
 * “Available to schedule” = unscheduled students still in the live queue
 * (status waiting). Batch leftovers are separate — they are not this count.
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
    <Panel title="Notify next batch">
      <form onSubmit={onSubmit} className="stack-form">
        <div
          className={`notify-remaining-banner${unscheduled > 0 ? ' has-pool' : ''}`}
        >
          <span className="label">Available to schedule</span>
          <strong>{unscheduled}</strong>
          <span className="notify-pool-breakdown">
            Unscheduled in queue (no approval day yet)
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

        {!canNotify ? (
          <p className="notify-warn">
            Nothing to notify. No unscheduled students in the queue.
          </p>
        ) : null}
        {canNotify && unscheduled === 0 && carry > 0 ? (
          <p className="notify-warn notify-warn-info">
            No unscheduled joiners right now. Notify will use {carry} student
            {carry === 1 ? '' : 's'} still left in a batch table.
          </p>
        ) : null}
        {overRequest ? (
          <p className="notify-warn">
            Only {unscheduled} unscheduled student
            {unscheduled === 1 ? '' : 's'} in the queue. The system will take
            what is available
            {carry > 0 ? ` (plus ${carry} from a batch table)` : ''}.
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

        <button className="btn btn-primary" disabled={busy || !canNotify}>
          {busy ? 'Sending…' : 'Send notifications'}
        </button>
      </form>
    </Panel>
  );
}
