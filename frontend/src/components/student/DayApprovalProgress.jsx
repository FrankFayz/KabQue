import { useEffect, useState } from 'react';

function formatApprovalDay(iso) {
  if (!iso) return 'your approval day';
  try {
    const d = new Date(`${iso}T12:00:00`);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleDateString(undefined, {
      weekday: 'short',
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    });
  } catch {
    return iso;
  }
}

/**
 * Live day-session progress for a notified fresher.
 * Fills as the desk clears that day’s notified cohort; remaining shrinks with each finish.
 */
export default function DayApprovalProgress({ progress }) {
  const [displayPercent, setDisplayPercent] = useState(0);

  const total = Math.max(0, Number(progress?.total) || 0);
  const finished = Math.max(0, Number(progress?.finished) || 0);
  const remaining = Math.max(0, Number(progress?.remaining) || 0);
  const percent = Math.max(0, Math.min(100, Number(progress?.percent) || 0));
  const yourNumber = progress?.your_number;
  const ahead = Math.max(0, Number(progress?.ahead_today) || 0);
  const dayLabel = formatApprovalDay(progress?.scheduled_date);

  useEffect(() => {
    const id = requestAnimationFrame(() => setDisplayPercent(percent));
    return () => cancelAnimationFrame(id);
  }, [percent]);

  if (!progress || total < 1) return null;

  const stage =
    percent >= 100
      ? 'Session complete — last visits finishing at the desk'
      : percent >= 70
        ? 'Almost there — most of today’s group has been seen'
        : percent >= 35
          ? 'Desk is moving through today’s notified students'
          : 'Approval day is underway — stay ready with your code';

  const placeLine =
    yourNumber != null && Number(yourNumber) > 0
      ? ahead === 0
        ? `You are queue #${yourNumber} · near the front of today’s remaining list`
        : `You are queue #${yourNumber} · about ${ahead} still ahead in today’s session`
      : null;

  return (
    <section
      className="day-progress"
      aria-label="Approval day progress"
      aria-live="polite"
    >
      <header className="day-progress-head">
        <div>
          <p className="day-progress-kicker">Approval day · live</p>
          <h2 className="day-progress-title">{dayLabel}</h2>
        </div>
        <div className="day-progress-score" aria-hidden={false}>
          <strong>{finished}</strong>
          <span>of {total} finished</span>
        </div>
      </header>

      <div
        className="day-progress-track"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        aria-valuetext={`${finished} of ${total} students finished for this approval day`}
      >
        <div
          className="day-progress-fill"
          style={{ width: `${displayPercent}%` }}
        />
      </div>

      <div className="day-progress-meta">
        <p className="day-progress-stage">{stage}</p>
        <p className="day-progress-remaining">
          {remaining === 0
            ? 'No students left on today’s desk list'
            : remaining === 1
              ? '1 student still expected at the desk today'
              : `${remaining} students still expected at the desk today`}
        </p>
        {placeLine ? <p className="day-progress-place">{placeLine}</p> : null}
      </div>
    </section>
  );
}
