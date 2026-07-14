import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api, setAuth } from '../../api';
import { homePathFor } from '../../authRoles';
import Alert from '../ui/Alert';
import PasswordField from '../ui/PasswordField';

export default function RegisterForm() {
  const navigate = useNavigate();
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [passwordConfirm, setPasswordConfirm] = useState('');
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [loading, setLoading] = useState(false);

  async function onSubmit(e) {
    e.preventDefault();
    setError('');
    setInfo('');

    if (password !== passwordConfirm) {
      setError('Passwords do not match.');
      return;
    }

    setLoading(true);
    try {
      const data = await api('/auth/register/', {
        method: 'POST',
        auth: false,
        body: {
          identifier: identifier.trim(),
          password,
        },
      });

      // Supervisors must wait for Main Admin approval — no tokens issued
      if (data.pending_approval) {
        setInfo(
          data.message ||
            'Account created. Wait for Main Admin approval before signing in.'
        );
        setPassword('');
        setPasswordConfirm('');
        return;
      }

      setAuth(data);
      navigate(homePathFor(data.user));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <form className="auth-form" onSubmit={onSubmit}>
      <p className="auth-form-eyebrow">KabQue</p>
      <h1>Create account</h1>
      <Alert>{error}</Alert>
      {info ? <Alert variant="info">{info}</Alert> : null}
      <label>
        Account
        <input
          value={identifier}
          onChange={(e) => setIdentifier(e.target.value)}
          placeholder="Reg number, @kab.ac.ug, or Main Admin username"
          autoComplete="username"
          required
        />
      </label>
      <PasswordField
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        autoComplete="new-password"
        minLength={6}
        required
      />
      <PasswordField
        label="Confirm password"
        value={passwordConfirm}
        onChange={(e) => setPasswordConfirm(e.target.value)}
        autoComplete="new-password"
        minLength={6}
        required
      />
      <button className="btn btn-primary auth-submit" disabled={loading}>
        {loading ? 'Creating account…' : 'Create account'}
      </button>
      <p className="auth-switch">
        Already registered? <Link to="/login">Sign in</Link>
      </p>
    </form>
  );
}
