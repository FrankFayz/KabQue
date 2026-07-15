import { useEffect, useState } from 'react';
import { api, friendlyUserMessage, setAuth } from '../../api';
import { isValidE164 } from '../../constants/eastAfricaPhones';
import { captureCampusLocation } from '../../geo/campusLocation';
import Alert from '../ui/Alert';
import GpsPinIcon from '../ui/GpsPinIcon';
import Panel from '../ui/Panel';
import PhoneInput from '../ui/PhoneInput';

function locationErrorText(err) {
  const loc = err?.data?.location;
  if (typeof loc === 'string' && loc.trim()) {
    return friendlyUserMessage(loc, 'We could not confirm you are on campus.');
  }
  if (Array.isArray(loc) && loc.length) {
    return friendlyUserMessage(
      loc.map(String).join(' '),
      'We could not confirm you are on campus.'
    );
  }
  return friendlyUserMessage(
    err?.message,
    'We could not confirm you are on campus. Try outdoors with GPS on.'
  );
}

function buttonLabel(phase) {
  if (phase === 'locating') return 'Getting GPS fix…';
  if (phase === 'sampling') return 'Confirming GPS…';
  if (phase === 'confirming') return 'Verifying campus…';
  return 'Join queue';
}

function statusCopy(phase) {
  if (phase === 'locating') {
    return {
      title: 'Getting GPS fix',
      body: 'Allow location access. Stay still outdoors for a strong campus fix.',
    };
  }
  if (phase === 'sampling') {
    return {
      title: 'Confirming GPS',
      body: 'Taking a few readings to block fake-location jumps. Stay still…',
    };
  }
  return {
    title: 'Verifying campus area',
    body: 'Matching your location to the Kikungiri Campus join zone…',
  };
}

export default function JoinQueueCard({ profile, onJoined, onProfileUpdated }) {
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [phase, setPhase] = useState('idle'); // idle | locating | sampling | confirming
  const [loading, setLoading] = useState(false);
  const [savingContact, setSavingContact] = useState(false);
  const [phone, setPhone] = useState(profile?.phone || '');
  const [email, setEmail] = useState(profile?.email || '');
  const [editing, setEditing] = useState(null); // null | 'email' | 'phone'

  useEffect(() => {
    setPhone(profile?.phone || '');
    setEmail(profile?.email || '');
  }, [profile?.phone, profile?.email]);

  async function saveContact(e) {
    e.preventDefault();
    setError('');
    const nextPhone = phone.trim();
    const nextEmail = email.trim();
    if (nextPhone && !isValidE164(nextPhone)) {
      setError(
        'Enter a valid East African mobile number with country code (e.g. Uganda +256…).'
      );
      return;
    }
    if (!nextEmail && !nextPhone) {
      setError('Keep at least an email or telephone for notifications.');
      return;
    }
    setSavingContact(true);
    try {
      const data = await api('/student/profile/', {
        method: 'POST',
        body: {
          full_name: profile?.full_name || '',
          faculty: profile?.faculty || '',
          programme: profile?.programme || '',
          email: nextEmail,
          phone: nextPhone,
        },
      });
      if (data.user) setAuth({ user: data.user });
      setEditing(null);
      setInfo(editing === 'email' ? 'Email updated.' : 'SMS number updated.');
      onProfileUpdated?.(data);
    } catch (err) {
      setError(
        friendlyUserMessage(err.message, 'Could not join the queue right now. Please try again.')
      );
    } finally {
      setSavingContact(false);
    }
  }

  async function joinQueue() {
    if (loading) return;
    setError('');
    setInfo('');
    setLoading(true);
    setPhase('locating');
    try {
      const loc = await captureCampusLocation({
        onPhase: (next) => setPhase(next),
      });
      setPhase('confirming');
      await api('/student/join-queue/', {
        method: 'POST',
        body: {
          latitude: loc.latitude,
          longitude: loc.longitude,
          accuracy: loc.accuracy,
          altitude: loc.altitude,
          altitude_accuracy: loc.altitude_accuracy,
          speed: loc.speed,
          heading: loc.heading,
          captured_at: loc.captured_at,
          sample_count: loc.sample_count,
          sample_spread_m: loc.sample_spread_m,
          samples: loc.samples,
        },
      });
      setInfo('You joined the queue.');
      setPhase('idle');
      onJoined?.();
    } catch (err) {
      setError(locationErrorText(err));
      setInfo('');
      setPhase('idle');
    } finally {
      setLoading(false);
    }
  }

  const busyGps = loading || phase !== 'idle';
  const savedEmail = (profile?.email || '').trim();
  const savedPhone = (profile?.phone || '').trim();
  const status = busyGps ? statusCopy(phase === 'idle' ? 'locating' : phase) : null;

  return (
    <Panel title="Join the queue" className="join-queue-card student-join">
      <p className="student-join-lede">
        Confirm your contacts, then join only when you are inside the campus GPS
        zone. Fake-location apps are blocked when possible.
      </p>
      {profile?.full_name ? (
        <p className="muted join-queue-name">{profile.full_name}</p>
      ) : null}
      {profile && (
        <div className="status-grid join-profile-grid">
          <div>
            <span className="label">Reg. number</span>
            <strong>{profile.registration_number}</strong>
          </div>
          <div>
            <span className="label">Faculty</span>
            <strong className="join-wrap-text">{profile.faculty || '—'}</strong>
          </div>
          <div>
            <span className="label">Programme</span>
            <strong className="join-wrap-text">{profile.programme || '—'}</strong>
          </div>
        </div>
      )}

      <section className="join-contact-block" aria-label="Notification contacts">
        <header className="join-contact-head">
          <p className="join-contact-kicker">Notification contacts</p>
          <p className="hint">
            Saved from your profile — KabQue uses these when your day is notified.
          </p>
        </header>

        <div className="join-contact-list">
          <div className="join-contact-item">
            <span className="label">Email</span>
            {editing !== 'email' ? (
              <div className="join-contact-summary">
                <strong className="join-contact-value">
                  {savedEmail || 'Not set'}
                </strong>
                <button
                  type="button"
                  className="btn btn-ghost btn-tiny"
                  disabled={busyGps}
                  onClick={() => {
                    setEditing('email');
                    setEmail(savedEmail);
                    setError('');
                    setInfo('');
                  }}
                >
                  {savedEmail ? 'Change' : 'Add email'}
                </button>
              </div>
            ) : (
              <form className="join-contact-edit" onSubmit={saveContact}>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  placeholder="you@example.com"
                  disabled={savingContact}
                />
                <div className="join-contact-edit-actions">
                  <button
                    type="submit"
                    className="btn btn-primary btn-tiny"
                    disabled={savingContact}
                  >
                    {savingContact ? 'Saving…' : 'Save email'}
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost btn-tiny"
                    disabled={savingContact}
                    onClick={() => {
                      setEditing(null);
                      setEmail(savedEmail);
                    }}
                  >
                    Cancel
                  </button>
                </div>
              </form>
            )}
          </div>

          <div className="join-contact-item">
            <span className="label">Telephone (SMS)</span>
            {editing !== 'phone' ? (
              <div className="join-contact-summary">
                <strong className="join-contact-value join-contact-phone">
                  {savedPhone || 'Not set'}
                </strong>
                <button
                  type="button"
                  className="btn btn-ghost btn-tiny"
                  disabled={busyGps}
                  onClick={() => {
                    setEditing('phone');
                    setPhone(savedPhone);
                    setError('');
                    setInfo('');
                  }}
                >
                  {savedPhone ? 'Change' : 'Add number'}
                </button>
              </div>
            ) : (
              <form className="join-contact-edit" onSubmit={saveContact}>
                <PhoneInput
                  value={phone}
                  onChange={setPhone}
                  disabled={savingContact}
                />
                <div className="join-contact-edit-actions">
                  <button
                    type="submit"
                    className="btn btn-primary btn-tiny"
                    disabled={savingContact}
                  >
                    {savingContact ? 'Saving…' : 'Save number'}
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost btn-tiny"
                    disabled={savingContact}
                    onClick={() => {
                      setEditing(null);
                      setPhone(savedPhone);
                    }}
                  >
                    Cancel
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      </section>

      {status ? (
        <div
          className={`gps-status${phase === 'confirming' ? ' is-confirming' : ''}`}
          role="status"
          aria-live="polite"
        >
          <div className="gps-status-icon-wrap" aria-hidden="true">
            <span className="gps-pulse" />
            <span className="gps-pulse gps-pulse-delay" />
            <GpsPinIcon className="gps-status-icon" size={36} />
          </div>
          <div className="gps-status-copy">
            <strong>{status.title}</strong>
            <p>{status.body}</p>
          </div>
        </div>
      ) : null}

      <Alert>{error}</Alert>
      <Alert variant="info">{!error && !busyGps ? info : ''}</Alert>

      <button
        type="button"
        className={`btn btn-primary btn-join-gps${busyGps ? ' is-busy' : ''}`}
        onClick={joinQueue}
        disabled={busyGps || Boolean(editing)}
        aria-busy={busyGps}
      >
        <GpsPinIcon className="btn-join-gps-icon" size={18} />
        <span>{buttonLabel(busyGps && phase === 'idle' ? 'locating' : phase)}</span>
      </button>
    </Panel>
  );
}
