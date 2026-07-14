import Panel from '../ui/Panel';
import Alert from '../ui/Alert';

function deliveryLabel(channel) {
  if (!channel) return null;
  if (channel.success) return `${channel.channel.toUpperCase()} sent`;
  return `${channel.channel.toUpperCase()} failed: ${channel.error || 'error'}`;
}

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
          Emails <strong>{result.emails_sent ?? '—'}</strong>
        </span>
        <span>
          SMS <strong>{result.sms_sent ?? '—'}</strong>
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
              <th>Email</th>
              <th>Phone</th>
              <th>Secret code</th>
              <th>Delivery</th>
            </tr>
          </thead>
          <tbody>
            {students.map((s) => {
              const emailChannel = (s.channels || []).find((c) => c.channel === 'email');
              const smsChannel = (s.channels || []).find((c) => c.channel === 'sms');
              const parts = [deliveryLabel(emailChannel), deliveryLabel(smsChannel)].filter(
                Boolean
              );
              return (
                <tr key={`${s.registration_number}-${s.secret_code}`}>
                  <td>{s.position}</td>
                  <td>{s.full_name}</td>
                  <td>{s.registration_number}</td>
                  <td>{s.email || '—'}</td>
                  <td>{s.phone || '—'}</td>
                  <td>
                    <code>{s.secret_code}</code>
                  </td>
                  <td>{parts.length ? parts.join(' · ') : '—'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}
