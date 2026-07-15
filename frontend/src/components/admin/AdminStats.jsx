export default function AdminStats({ counts = {} }) {
  const items = [
    {
      label: 'In queue',
      value: counts.total,
      hint: 'Live on the desk list now',
      tone: '',
    },
    {
      label: 'Notified',
      value: counts.notified,
      hint: 'Has a day + queue number',
      tone: '',
    },
    {
      label: 'Approved',
      value: counts.approved,
      hint: 'All-time desk approvals',
      tone: '',
    },
  ];

  return (
    <div className="stat-row desk-stat-row">
      {items.map((item) => (
        <div key={item.label} className={`stat ${item.tone}`.trim()}>
          <span className="label">{item.label}</span>
          <strong>{item.value ?? 0}</strong>
          <span className="stat-hint">{item.hint}</span>
        </div>
      ))}
    </div>
  );
}
