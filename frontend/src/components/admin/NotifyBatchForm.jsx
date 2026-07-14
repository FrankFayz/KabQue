import Panel from '../ui/Panel';

export default function NotifyBatchForm({
  batchSize,
  scheduledDate,
  channel,
  busy,
  remaining = 0,
  onBatchSizeChange,
  onScheduledDateChange,
  onChannelChange,
  onSubmit,
}) {
  const requested = Number(batchSize) || 0;
  const overRequest = remaining > 0 && requested > remaining;
  const noneWaiting = remaining === 0;

  return (
    <Panel title="Notify next batch">
      <form onSubmit={onSubmit} className="stack-form">
        <div className="notify-remaining-banner">
          <span className="label">Remaining to notify</span>
          <strong>{remaining}</strong>
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
          />
        </label>

        {noneWaiting ? (
          <p className="notify-warn">No students are waiting. Joiners appear here when they enter the queue.</p>
        ) : null}
        {overRequest ? (
          <p className="notify-warn">
            Only {remaining} student{remaining === 1 ? '' : 's'} remaining. The
            system will notify all {remaining} in first-come order.
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
          />
        </label>
        <label>
          Channel
          <select value={channel} onChange={(e) => onChannelChange(e.target.value)}>
            <option value="email">Email only</option>
            <option value="both">Email & SMS</option>
            <option value="sms">SMS only</option>
          </select>
        </label>
        <button className="btn btn-primary" disabled={busy || noneWaiting}>
          {busy ? 'Sending…' : 'Send notifications'}
        </button>
      </form>
    </Panel>
  );
}
