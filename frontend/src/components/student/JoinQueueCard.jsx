import { useState } from 'react';
import { api, getCurrentPosition } from '../../api';
import Alert from '../ui/Alert';
import Panel from '../ui/Panel';

export default function JoinQueueCard({ profile, onJoined }) {
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [loading, setLoading] = useState(false);

  async function joinQueue() {
    setError('');
    setInfo('Checking your GPS location…');
    setLoading(true);
    try {
      const loc = await getCurrentPosition();
      setInfo('Confirming you are within Kabale University campus…');
      const data = await api('/student/join-queue/', {
        method: 'POST',
        body: {
          latitude: loc.latitude,
          longitude: loc.longitude,
        },
      });
      setInfo('');
      // Parent reloads live queue status from the API
      onJoined?.(data);
    } catch (err) {
      const locMsg =
        err.data?.location ||
        (Array.isArray(err.data?.location) ? err.data.location.join(' ') : null);
      setError(locMsg || err.message);
      setInfo('');
    } finally {
      setLoading(false);
    }
  }

  return (
    <Panel title="Join the queue" className="join-queue-card">
      {profile?.full_name ? (
        <p className="muted">{profile.full_name}</p>
      ) : null}
      {profile && (
        <div className="status-grid">
          <div>
            <span className="label">Reg. number</span>
            <strong>{profile.registration_number}</strong>
          </div>
          <div>
            <span className="label">Faculty</span>
            <strong>{profile.faculty || '—'}</strong>
          </div>
          <div>
            <span className="label">Programme</span>
            <strong>{profile.programme || '—'}</strong>
          </div>
        </div>
      )}
      <Alert>{error}</Alert>
      <Alert variant="info">{!error ? info : ''}</Alert>
      <button
        type="button"
        className="btn btn-primary"
        onClick={joinQueue}
        disabled={loading}
      >
        {loading ? 'Checking location…' : 'Join queue'}
      </button>
    </Panel>
  );
}
