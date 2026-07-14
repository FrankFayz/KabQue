export default function AdminStats({ counts = {} }) {
  const remaining = counts.remaining ?? counts.waiting ?? 0;
  const items = [
    ['Total', counts.total, 'In queue'],
    ['Remaining', remaining, 'Still waiting to notify'],
    ['Notified', counts.notified, 'Assigned a day'],
    ['Checked in', counts.checked_in, 'At the desk'],
    ['Approved', counts.approved, 'Completed'],
  ];

  return (
    <div className="stat-row">
      {items.map(([label, value, hint]) => (
        <div
          key={label}
          className={`stat${label === 'Remaining' ? ' stat-remaining' : ''}`}
        >
          <span className="label">{label}</span>
          <strong>{value ?? 0}</strong>
          <span className="stat-hint">{hint}</span>
        </div>
      ))}
    </div>
  );
}
