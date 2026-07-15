import { useState } from 'react';
import { api, setAuth, userError } from '../../api';
import { validateEastAfricaPhone } from '../../constants/eastAfricaPhones';
import FacultyProgrammeFields from '../auth/FacultyProgrammeFields';
import Alert from '../ui/Alert';
import PhoneInput from '../ui/PhoneInput';

function UserBadgeIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="8" r="3.5" stroke="currentColor" strokeWidth="1.75" />
      <path
        d="M5.5 19.5c1.6-3.2 4-4.8 6.5-4.8s4.9 1.6 6.5 4.8"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
      />
    </svg>
  );
}

function MailIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="3.5" y="5.5" width="17" height="13" rx="2" stroke="currentColor" strokeWidth="1.75" />
      <path d="M4 7l8 6 8-6" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function PhoneIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M8.5 4.5h2.2l1.1 3.2-1.4 1.4a12.5 12.5 0 0 0 5.5 5.5l1.4-1.4 3.2 1.1v2.2c0 .9-.7 1.7-1.6 1.8-7.4.8-13.5-5.3-12.7-12.7.1-.9.9-1.6 1.8-1.6Z"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function GradIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M3 10.5 12 6l9 4.5-9 4.5L3 10.5Z" stroke="currentColor" strokeWidth="1.75" strokeLinejoin="round" />
      <path d="M7 12.5v4.2c0 .4.8 1.5 5 2.3 4.2-.8 5-1.9 5-2.3v-4.2" stroke="currentColor" strokeWidth="1.75" />
      <path d="M21 10.5v5" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
    </svg>
  );
}

function isFormComplete(form) {
  return Boolean(
    form.full_name.trim() &&
      form.email.trim() &&
      form.phone.trim() &&
      form.faculty &&
      form.programme
  );
}

export default function CompleteProfileCard({ profile, onSaved }) {
  const [form, setForm] = useState({
    full_name: profile?.full_name || '',
    faculty: profile?.faculty || '',
    programme: profile?.programme || '',
    email: profile?.email || '',
    phone: profile?.phone || '',
  });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const ready = isFormComplete(form);

  function update(field) {
    return (e) => setForm((f) => ({ ...f, [field]: e.target.value }));
  }

  function updateAcademic(patch) {
    setForm((f) => ({ ...f, ...patch }));
  }

  async function onSubmit(e) {
    e.preventDefault();
    setError('');
    if (!isFormComplete(form)) {
      setError('Fill in every field — name, email, telephone, faculty, and programme.');
      return;
    }
    const email = form.email.trim();
    const phoneCheck = validateEastAfricaPhone(form.phone.trim());
    if (!phoneCheck.ok) {
      setError(phoneCheck.error);
      return;
    }
    setLoading(true);
    try {
      const data = await api('/student/profile/', {
        method: 'POST',
        body: {
          full_name: form.full_name.trim(),
          faculty: form.faculty,
          programme: form.programme,
          email,
          phone: phoneCheck.value,
        },
      });
      if (data.user) setAuth({ user: data.user });
      onSaved?.(data);
    } catch (err) {
      setError(userError(err, 'Could not save your profile. Please check every field and try again.'));
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="profile-setup">
      <header className="profile-setup-hero">
        <div className="profile-setup-badge" aria-hidden="true">
          <UserBadgeIcon />
        </div>
        <div className="profile-setup-hero-copy">
          <p className="profile-setup-kicker">Fresher profile</p>
          <h2>Complete your details</h2>
          <p>
            Fill every field before you join the campus queue. Your email is used
            for notifications and password resets.
          </p>
        </div>
        <div className="profile-setup-reg">
          <span className="label">Registration number</span>
          <strong>{profile?.registration_number || '—'}</strong>
        </div>
      </header>

      <Alert>{error}</Alert>

      <form className="profile-setup-form" onSubmit={onSubmit} noValidate>
        <section className="profile-setup-block">
          <div className="profile-setup-block-head">
            <span className="profile-setup-block-icon" aria-hidden="true">
              <UserBadgeIcon />
            </span>
            <div>
              <h3>Identity</h3>
              <p>As it appears on your university documents</p>
            </div>
          </div>
          <label className="profile-field">
            Full name
            <input
              value={form.full_name}
              onChange={update('full_name')}
              placeholder="e.g. Amina Nakato"
              autoComplete="name"
              required
            />
          </label>
        </section>

        <section className="profile-setup-block">
          <div className="profile-setup-block-head">
            <span className="profile-setup-block-icon" aria-hidden="true">
              <MailIcon />
            </span>
            <div>
              <h3>Contact for notifications</h3>
              <p>Email and telephone are both required</p>
            </div>
          </div>
          <div className="profile-setup-grid">
            <label className="profile-field">
              <span className="profile-field-label">
                <MailIcon /> Email
              </span>
              <input
                type="email"
                value={form.email}
                onChange={update('email')}
                autoComplete="email"
                placeholder="you@example.com"
                required
              />
            </label>
            <div className="profile-field phone-field">
              <span className="profile-field-label">
                <PhoneIcon /> Telephone (SMS)
              </span>
              <PhoneInput
                value={form.phone}
                onChange={(phone) => setForm((f) => ({ ...f, phone }))}
                placeholder="7XXXXXXXX"
                required
              />
            </div>
          </div>
        </section>

        <section className="profile-setup-block">
          <div className="profile-setup-block-head">
            <span className="profile-setup-block-icon" aria-hidden="true">
              <GradIcon />
            </span>
            <div>
              <h3>Academic placement</h3>
              <p>Faculty and programme for queue analytics</p>
            </div>
          </div>
          <div className="profile-setup-academic">
            <FacultyProgrammeFields
              faculty={form.faculty}
              programme={form.programme}
              onChange={updateAcademic}
            />
          </div>
        </section>

        <div className="profile-setup-footer">
          <p className="hint">
            After saving, join the queue when you are within the campus GPS zone.
            Use this email later if you forget your password.
          </p>
          <button
            type="submit"
            className="btn btn-primary profile-setup-submit"
            disabled={loading || !ready}
          >
            {loading ? 'Saving profile…' : 'Save and continue'}
          </button>
        </div>
      </form>
    </section>
  );
}
