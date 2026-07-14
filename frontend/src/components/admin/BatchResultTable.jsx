import Panel from '../ui/Panel';
import Alert from '../ui/Alert';

export default function BatchResultTable({ result }) {
  const students = result?.students || [];
  if (!result || !students.length) return null;

  return (
    <Panel title="Last batch notified">
      <Alert variant="info">{result.message || ''}</Alert>
      {result.shortage ? (
        <Alert>
          Requested {result.requested}, but only {result.available} were waiting —
          all remaining waiters were notified.
        </Alert>
      ) : null}
      <div className="batch-summary">
        <span>
          Notified <strong>{result.notified_count}</strong>
        </span>
        <span>
          Remaining <strong>{result.remaining ?? '—'}</strong>
        </span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Name</th>
              <th>Reg. no.</th>
              <th>Secret code</th>
            </tr>
          </thead>
          <tbody>
            {students.map((s) => (
              <tr key={`${s.registration_number}-${s.secret_code}`}>
                <td>{s.position}</td>
                <td>{s.full_name}</td>
                <td>{s.registration_number}</td>
                <td>
                  <code>{s.secret_code}</code>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}
