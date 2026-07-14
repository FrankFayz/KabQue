import { useState } from 'react';
import StatusPill from '../ui/StatusPill';
import SecretCodeCard from './SecretCodeCard';
import Alert from '../ui/Alert';

function canReturnToWaiting(queue) {
  if (!queue) return false;
  if (['approved', 'rejected', 'waiting'].includes(queue.status)) return false;
  return (
    Boolean(queue.scheduled_date) ||
    ['notified', 'checked_in', 'skipped'].includes(queue.status)
  );
}

export default function QueueStatusBoard({ queue, busy = false, onReschedule, onLeave }) {
  const [localError, setLocalError] = useState('');
  const canDefer = canReturnToWaiting(queue);
  const hasBatchNumber =
    queue?.status !== 'waiting' &&
    queue?.position != null &&
    Number(queue.position) > 0;

  if (!queue) return null;

  async function handleReturnToWaiting() {
    setLocalError('');
    const ok = window.confirm(
      'Cannot attend this approval day?\n\n' +
        'You will return to the waiting queue. You cannot choose a new date — ' +
        'wait until the supervisor notifies the next schedule.'
    );
    if (!ok) return;
    try {
      await onReschedule?.();
    } catch (err) {
      setLocalError(err.message);
    }
  }

  async function handleLeave() {
    setLocalError('');
    const ok = window.confirm(
      'Leave the queue completely? You can join again later from campus.'
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
        {canDefer ? (
          <div className="queue-defer">
            <p className="queue-defer-copy">
              Cannot make this approval day? Return to the waiting queue. KabQue
              will not let you pick a date — wait for the next supervisor schedule.
            </p>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleReturnToWaiting}
              disabled={busy}
            >
              {busy ? 'Returning…' : 'Return to waiting queue'}
            </button>
          </div>
        ) : null}
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
