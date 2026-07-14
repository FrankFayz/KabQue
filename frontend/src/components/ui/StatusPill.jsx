export default function StatusPill({ status }) {
  if (!status) return null;
  return <span className={`pill status-${status}`}>{status.replaceAll('_', ' ')}</span>;
}
