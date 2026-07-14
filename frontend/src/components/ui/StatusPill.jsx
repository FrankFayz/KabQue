export default function StatusPill({ status, children }) {
  if (!status && !children) return null;
  const label = children || String(status || '').replaceAll('_', ' ');
  return <span className={`pill status-${status || 'waiting'}`}>{label}</span>;
}
