import { useEffect, useState } from 'react';
import { api, getCurrentPosition, setAuth } from '../../api';
import { isValidE164 } from '../../constants/eastAfricaPhones';
import Alert from '../ui/Alert';
import GpsPinIcon from '../ui/GpsPinIcon';
import Panel from '../ui/Panel';
import PhoneInput from '../ui/PhoneInput';

function scrubError(message) {
  const text = String(message || '');
  if (
    /<!doctype/i.test(text) ||
    /<html/i.test(text) ||
    /Server Error \(500\)/i.test(text)
  ) {
    return 'Could not join the queue right now. Please try again.';
  }
  return text;
}

function locationErrorText(err) {
  const loc = err?.data?.location;
  if (typeof loc === 'string' && loc.trim()) return loc;
  if (Array.isArray(loc) && loc.length) return loc.map(String).join(' ');
  return scrubError(err?.message || 'Unable to confirm your location.');
}

export default function JoinQueueCard({ profile, onJoined, onProfileUpdated }) {
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [phase, setPhase] = useState('idle'); // idle | locating | confirming | done
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
      setError(scrubError(err.message));
    } finally {
      setSavingPhone(false);
    }
  }

  async function joinQueue() {
    setError('');
    setInfo('');
    setLoading(true);
    setPhase('locating');
    try {
      const loc = await getCurrentPosition();
      setPhase('confirming');
      const data = await api('/student/join-queue/', {
        method: 'POST',
        body: {
          latitude: loc.latitude,
          longitude: loc.longitude,
        },
      });
      setPhase('done');
      setInfo('');
      onJoined?.(data);
    } catch (err) {
      setError(locationErrorText(err));
      setInfo('');
      setPhase('idle');
    } finally {
      setLoading(false);
    }
  }

  const locating = phase === 'locating' || phase === 'confirming';

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

      {locating ? (
        <div className={`gps-status${phase === 'confirming' ? ' is-confirming' : ''}`} role="status">
          <div className="gps-status-icon-wrap" aria-hidden="true">
            <span className="gps-pulse" />
            <span className="gps-pulse gps-pulse-delay" />
            <GpsPinIcon className="gps-status-icon" size={36} />
          </div>
          <div className="gps-status-copy">
            <strong>
              {phase === 'locating' ? 'Checking location' : 'Confirming campus area'}
            </strong>
            <p>
              {phase === 'locating'
                ? 'Allow GPS access so KabQue can verify you are on campus.'
                : 'Matching your coordinates to the allowed join zone…'}
            </p>
          </div>
        </div>
      ) : null}

      <Alert>{error}</Alert>
      <Alert variant="info">{!error && !locating ? info : ''}</Alert>

      <button
        type="button"
        className="btn btn-primary btn-join-gps"
        onClick={joinQueue}
        disabled={loading || editingPhone}
      >
        {locating ? (
          <>
            <GpsPinIcon className="btn-join-gps-icon" size={18} />
            <span>Checking location…</span>
          </>
        ) : (
          <>
            <GpsPinIcon className="btn-join-gps-icon" size={18} />
            <span>Join queue</span>
          </>
        )}
      </button>
    </Panel>
  );
}
