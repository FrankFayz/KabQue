export default function AdminStats({ counts = {} }) {
  const waiting = counts.remaining ?? counts.waiting ?? 0;
  const leftovers = counts.batch_leftovers ?? 0;
  const pool = counts.notify_pool ?? waiting + leftovers;
  const items = [
    ['Total', counts.total, 'In queue'],
    ['To schedule', pool, leftovers > 0 ? `${waiting} waiting · ${leftovers} in batch` : 'Waiting + batch leftovers'],
    ['Notified', counts.notified, 'Assigned a day'],
    ['Checked in', counts.checked_in, 'At the desk'],
    ['Approved', counts.approved, 'Left batch table'],
  ];

  return (
    <div className="stat-row">
      {items.map(([label, value, hint]) => (
        <div
          key={label}
          className={`stat${label === 'To schedule' ? ' stat-remaining' : ''}`}
        >
          <span className="label">{label}</span>
          <strong>{value ?? 0}</strong>
          <span className="stat-hint">{hint}</span>
        </div>
      ))}
    </div>
  );
}
