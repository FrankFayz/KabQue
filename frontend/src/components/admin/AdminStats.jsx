export default function AdminStats({ counts = {}, onJump }) {
  const waiting =
    counts.in_queue ?? counts.unscheduled ?? counts.waiting ?? counts.total ?? 0;
  const scheduled = counts.scheduled ?? 0;
  const approved = counts.approved ?? 0;

  const items = [
    {
      key: 'waiting',
      label: 'Waiting',
      value: waiting,
      hint: 'Ready to schedule',
      className: 'desk-stat desk-stat-queue',
      jump: 'notify',
    },
    {
      key: 'today',
      label: 'Scheduled',
      value: scheduled,
      hint: 'Have an approval day',
      className: 'desk-stat desk-stat-scheduled',
      jump: 'batch',
    },
    {
      key: 'approved',
      label: 'Approved',
      value: approved,
      hint: 'Finished at desk',
      className: 'desk-stat desk-stat-approved',
      jump: null,
    },
  ];

  return (
    <div className="stat-row desk-stat-row" aria-label="Desk counts">
      {items.map((item) => {
        const clickable = Boolean(onJump && item.jump);
        const Tag = clickable ? 'button' : 'div';
        return (
          <Tag
            key={item.key}
            type={clickable ? 'button' : undefined}
            className={`stat ${item.className}${clickable ? ' desk-stat-jump' : ''}`}
            onClick={clickable ? () => onJump(item.jump) : undefined}
          >
            <span className="label">{item.label}</span>
            <strong>{item.value}</strong>
            <span className="stat-hint">{item.hint}</span>
          </Tag>
        );
      })}
    </div>
  );
}
