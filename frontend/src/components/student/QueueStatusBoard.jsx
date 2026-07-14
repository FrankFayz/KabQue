import { useEffect, useState } from 'react';
import StatusPill from '../ui/StatusPill';
import SecretCodeCard from './SecretCodeCard';
import Alert from '../ui/Alert';

function tomorrowISO() {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return d.toISOString().slice(0, 10);
}

function canManageAssignment(queue) {
  if (!queue) return false;
  if (['approved', 'rejected'].includes(queue.status)) return false;
  return (
    Boolean(queue.scheduled_date) ||
    ['notified', 'checked_in', 'skipped'].includes(queue.status)
  );
}

export default function QueueStatusBoard({ queue, busy = false, onReschedule, onLeave }) {
  const [date, setDate] = useState(() => queue?.scheduled_date || tomorrowISO());
  const [localError, setLocalError] = useState('');
  const manage = canManageAssignment(queue);
  const hasBatchNumber =
    queue?.has_batch_number === true ||
    (queue?.position != null && queue?.status !== 'waiting');

  useEffect(() => {
    setDate(queue?.scheduled_date || tomorrowISO());
  }, [queue?.scheduled_date, queue?.id]);

  if (!queue) return null;

  async function handleReschedule() {
    setLocalError('');
    if (!date) {
      setLocalError('Choose a new date.');
      return;
    }
    try {
      await onReschedule?.(date);
    } catch (err) {
      setLocalError(err.message);
    }
  }

  async function handleLeave() {
    setLocalError('');
    const ok = window.confirm(
      'Leave the queue and cancel this assignment? You can join again later from campus.'
    );
    if (!ok) return;
    try {
      await onLeave?.();
    } catch (err) {
      setLocalError(err.message);
    }
  }

  return (
    <div className="status-board">
      <div className="status-hero">
        <span className="label">
          {hasBatchNumber ? 'Your queue number' : 'Queue status'}
        </span>
        {hasBatchNumber ? (
          <strong className="pos">#{queue.position}</strong>
        ) : (
          <strong className="pos pos-pending">Pending</strong>
        )}
        <StatusPill status={queue.status} />
      </div>

      {!hasBatchNumber ? (
        <p className="queue-pending-note">
          You are in the priority queue. Your number will be assigned when the
          supervisor notifies the next approval batch (in arrival order).
        </p>
      ) : null}

      <div className="status-grid">
        {queue.status === 'waiting' ? (
          <div>
            <span className="label">Waiting ahead</span>
            <strong>{queue.students_ahead_waiting ?? '—'}</strong>
          </div>
        ) : null}
        <div>
          <span className="label">Scheduled day</span>
          <strong>{queue.scheduled_date || 'Not assigned yet'}</strong>
        </div>
        <div>
          <span className="label">Registration no.</span>
          <strong>{queue.student?.registration_number}</strong>
        </div>
        <div>
          <span className="label">Faculty</span>
          <strong>{queue.student?.faculty || '—'}</strong>
        </div>
        <div>
          <span className="label">Programme</span>
          <strong>{queue.student?.programme || '—'}</strong>
        </div>
      </div>
      <SecretCodeCard code={queue.secret_code} scheduledDate={queue.scheduled_date} />

      <div className="queue-manage">
        <Alert>{localError}</Alert>
        {manage && (
          <div className="queue-manage-row">
            <label className="queue-manage-date">
              New date
              <input
                type="date"
                value={date}
                min={new Date().toISOString().slice(0, 10)}
                onChange={(e) => setDate(e.target.value)}
                disabled={busy}
              />
            </label>
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleReschedule}
              disabled={busy}
            >
              {busy ? 'Working…' : 'Reschedule'}
            </button>
          </div>
        )}
        {!['approved', 'rejected'].includes(queue.status) && (
          <button
            type="button"
            className="btn btn-danger-outline"
            onClick={handleLeave}
            disabled={busy}
          >
            Leave queue
          </button>
        )}
      </div>
    </div>
  );
}
