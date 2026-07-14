import { useEffect, useState } from 'react';
import { api, getCurrentPosition, setAuth } from '../../api';
import { isValidE164 } from '../../constants/eastAfricaPhones';
import Alert from '../ui/Alert';
import Panel from '../ui/Panel';
import PhoneInput from '../ui/PhoneInput';

export default function JoinQueueCard({ profile, onJoined, onProfileUpdated }) {
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [loading, setLoading] = useState(false);
  const [savingPhone, setSavingPhone] = useState(false);
  const [phone, setPhone] = useState(profile?.phone || '');
  const [editingPhone, setEditingPhone] = useState(false);

  useEffect(() => {
    setPhone(profile?.phone || '');
  }, [profile?.phone]);

  async function savePhone(e) {
    e.preventDefault();
    setError('');
    const next = phone.trim();
    if (next && !isValidE164(next)) {
      setError(
        'Enter a valid East African mobile number with country code (e.g. Uganda +256…).'
      );
      return;
    }
    if (!next && !(profile?.email || '').trim()) {
      setError('Provide a telephone number (or keep an email on your profile) for notifications.');
      return;
    }
    setSavingPhone(true);
    try {
      const data = await api('/student/profile/', {
        method: 'POST',
        body: {
          full_name: profile?.full_name || '',
          faculty: profile?.faculty || '',
          programme: profile?.programme || '',
          email: profile?.email || '',
          phone: next,
        },
      });
      if (data.user) setAuth({ user: data.user });
      setEditingPhone(false);
      setInfo('SMS number updated.');
      onProfileUpdated?.(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setSavingPhone(false);
    }
  }

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

      <div className="sms-phone-block">
        <span className="label">SMS number</span>
        {!editingPhone ? (
          <div className="sms-phone-summary">
            <strong>{phone || 'Not set'}</strong>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => setEditingPhone(true)}
            >
              {phone ? 'Change' : 'Add number'}
            </button>
          </div>
        ) : (
          <form className="stack-form" onSubmit={savePhone}>
            <PhoneInput value={phone} onChange={setPhone} />
            <div className="cta-row">
              <button className="btn btn-primary" disabled={savingPhone}>
                {savingPhone ? 'Saving…' : 'Save number'}
              </button>
              <button
                type="button"
                className="btn btn-ghost"
                disabled={savingPhone}
                onClick={() => {
                  setEditingPhone(false);
                  setPhone(profile?.phone || '');
                }}
              >
                Cancel
              </button>
            </div>
          </form>
        )}
      </div>

      <Alert>{error}</Alert>
      <Alert variant="info">{!error ? info : ''}</Alert>
      <button
        type="button"
        className="btn btn-primary"
        onClick={joinQueue}
        disabled={loading || editingPhone}
      >
        {loading ? 'Checking location…' : 'Join queue'}
      </button>
    </Panel>
  );
}
