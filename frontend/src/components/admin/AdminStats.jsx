export default function AdminStats({ counts = {} }) {
  const waiting = counts.remaining ?? counts.waiting ?? 0;
  const leftovers = counts.batch_leftovers ?? 0;
  const pool = counts.notify_pool ?? waiting + leftovers;
  const items = [
    {
      label: 'Total',
      value: counts.total,
      hint: 'Everyone still on the desk list',
      tone: '',
    },
    {
      label: 'To schedule',
      value: pool,
      hint:
        leftovers > 0
          ? `${waiting} waiting · ${leftovers} still in a batch`
          : waiting > 0
            ? 'New joiners waiting for a notify day'
            : 'No one waiting to notify',
      tone: pool > 0 ? 'stat-remaining is-hot' : 'stat-remaining',
    },
    {
      label: 'Notified',
      value: counts.notified,
      hint: 'Has a day + queue number',
      tone: '',
    },
    {
      label: 'Checked in',
      value: counts.checked_in,
      hint: 'Code verified at desk',
      tone: '',
    },
    {
      label: 'Approved',
      value: counts.approved,
      hint: 'Cleared · left live tables',
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
