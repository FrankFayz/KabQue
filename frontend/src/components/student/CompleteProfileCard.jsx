import { useState } from 'react';
import { api, setAuth } from '../../api';
import FacultyProgrammeFields from '../auth/FacultyProgrammeFields';
import Alert from '../ui/Alert';
import Panel from '../ui/Panel';

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

  function update(field) {
    return (e) => setForm((f) => ({ ...f, [field]: e.target.value }));
  }

  function updateAcademic(patch) {
    setForm((f) => ({ ...f, ...patch }));
  }

  async function onSubmit(e) {
    e.preventDefault();
    setError('');
    if (!form.email.trim() && !form.phone.trim()) {
      setError('Provide at least an email or a telephone number for notifications.');
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
          email: form.email.trim(),
          phone: form.phone.trim(),
        },
      });
      if (data.user) setAuth({ user: data.user });
      onSaved?.(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Panel title="Complete your details" className="complete-profile-card">
      <p className="muted">
        Registration number <strong>{profile?.registration_number || '—'}</strong>
      </p>
      <Alert>{error}</Alert>
      <form className="complete-profile-form" onSubmit={onSubmit}>
        <div className="grid-2">
          <label>
            Full name
            <input
              value={form.full_name}
              onChange={update('full_name')}
              required
            />
          </label>
          <label>
            Email
            <input
              type="email"
              value={form.email}
              onChange={update('email')}
              autoComplete="email"
              placeholder="you@example.com"
            />
          </label>
          <label>
            Telephone
            <input
              value={form.phone}
              onChange={update('phone')}
              placeholder="07…"
              autoComplete="tel"
            />
          </label>
          <FacultyProgrammeFields
            faculty={form.faculty}
            programme={form.programme}
            onChange={updateAcademic}
          />
        </div>
        <p className="hint">Provide at least email or telephone.</p>
        <button type="submit" className="btn btn-primary" disabled={loading}>
          {loading ? 'Saving…' : 'Save details'}
        </button>
      </form>
    </Panel>
  );
}
