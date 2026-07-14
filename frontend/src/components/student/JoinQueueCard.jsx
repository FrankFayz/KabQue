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
      setInfo(
        editing === 'email' ? 'Email updated.' : 'SMS number updated.'
      );
      onProfileUpdated?.(data);
    } catch (err) {
      setError(scrubError(err.message));
    } finally {
      setSavingContact(false);
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
  const savedEmail = (profile?.email || '').trim();
  const savedPhone = (profile?.phone || '').trim();

  return (
    <Panel title="Join the queue" className="join-queue-card">
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

      {locating ? (
        <div
          className={`gps-status${phase === 'confirming' ? ' is-confirming' : ''}`}
          role="status"
        >
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
        disabled={loading || Boolean(editing)}
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
