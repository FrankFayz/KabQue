export default function AdminStats({ counts = {} }) {
  const inQueue =
    counts.in_queue ?? counts.unscheduled ?? counts.waiting ?? counts.total ?? 0;
  const scheduled = counts.scheduled ?? 0;

  return (
    <div className="stat-row desk-stat-row" aria-label="Desk counts">
      <div className="stat desk-stat desk-stat-queue">
        <span className="label">In queue</span>
        <strong>{inQueue}</strong>
        <span className="stat-hint">Joined · not scheduled</span>
      </div>

      <div className="stat desk-stat desk-stat-scheduled">
        <span className="label">Scheduled</span>
        <strong>{scheduled}</strong>
        <span className="stat-hint">Has an approval day</span>
      </div>

      <div className="stat desk-stat desk-stat-approved">
        <span className="label">Approved</span>
        <strong>{counts.approved ?? 0}</strong>
        <span className="stat-hint">All-time desk finishes</span>
      </div>
    </div>
  );
}
