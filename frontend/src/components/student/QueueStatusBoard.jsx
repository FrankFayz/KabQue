import { useState } from 'react';
import StatusPill from '../ui/StatusPill';
import DayApprovalProgress from './DayApprovalProgress';
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
  const dayProgress = queue?.day_progress;

  if (!queue) return null;

  async function handleReturnToWaiting() {
    setLocalError('');
    const ok = window.confirm(
      'Leave this approval day and return to waiting?\n\nYou will wait for the next schedule.'
    );
    if (!ok) return;
    try {
      await onReschedule?.();
    } catch (err) {
      setLocalError(err.message || 'Could not update your queue request. Please try again.');
    }
  }

  async function handleLeave() {
    setLocalError('');
    const ok = window.confirm(
      'Do you really want to leave the queue?\n\n' +
        'OK — exit the queue.\n' +
        'Cancel — stay in the queue.'
    );
    if (!ok) return;
    try {
      await onLeave?.();
    } catch (err) {
      setLocalError(err.message || 'Could not leave the queue. Please try again.');
    }
  }

  const facts = [
    queue.status === 'waiting'
      ? {
          label: 'Waiting ahead',
          value: queue.students_ahead_waiting ?? '—',
        }
      : null,
    {
      label: 'Scheduled day',
      value: queue.scheduled_date || 'Not assigned yet',
    },
    {
      label: 'Registration no.',
      value: queue.student?.registration_number || '—',
    },
    {
      label: 'Faculty',
      value: queue.student?.faculty || '—',
    },
    {
      label: 'Programme',
      value: queue.student?.programme || '—',
    },
  ].filter(Boolean);

  return (
    <div className="status-board student-status">
      <div className="student-status-hero">
        <div className="student-status-hero-copy">
          <span className="label">
            {hasBatchNumber ? 'Your queue number' : 'Queue status'}
          </span>
          {hasBatchNumber ? (
            <strong className="pos">#{queue.position}</strong>
          ) : (
            <strong className="pos pos-pending">Pending</strong>
          )}
          <p className="student-status-hero-note">
            {hasBatchNumber
              ? 'Bring your required documents and present this number with your secret code at the desk.'
              : 'You are in the priority queue. Your number is assigned when the next batch is notified.'}
          </p>
        </div>
        <div className="student-status-pill-wrap">
          <StatusPill status={queue.status} />
        </div>
      </div>

      {dayProgress ? <DayApprovalProgress progress={dayProgress} /> : null}

      {!hasBatchNumber ? (
        <p className="queue-pending-note">
          Stay reachable by email and SMS. KabQue will notify you in arrival order.
        </p>
      ) : null}

      <div className="student-fact-grid" role="list">
        {facts.map((fact) => (
          <div key={fact.label} className="student-fact" role="listitem">
            <span className="label">{fact.label}</span>
            <strong>{fact.value}</strong>
          </div>
        ))}
      </div>

      <SecretCodeCard
        code={queue.secret_code}
        scheduledDate={queue.scheduled_date}
        requiredDocuments={queue.required_documents}
      />

      <div className="queue-manage">
        <Alert>{localError}</Alert>
        {canDefer ? (
          <button
            type="button"
            className="btn btn-secondary"
            onClick={handleReturnToWaiting}
            disabled={busy}
          >
            {busy ? 'Returning…' : 'Return to waiting queue'}
          </button>
        ) : null}
        {!['approved', 'rejected'].includes(queue.status) && (
          <button
            type="button"
            className="btn btn-danger-outline"
            onClick={handleLeave}
            disabled={busy}
          >
            {busy ? 'Leaving…' : 'Exit queue'}
          </button>
        )}
      </div>
    </div>
  );
}
