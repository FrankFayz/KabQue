import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api, clearAuth, setAuth } from '../../api';
import { homePathFor } from '../../authRoles';
import { normalizeRegistrationNumber } from '../../constants/registrationNumber';
import Alert from '../ui/Alert';
import PasswordField from '../ui/PasswordField';
import ForgotPasswordPanel from './ForgotPasswordPanel';
import SupervisorEmailVerifyPanel from './SupervisorEmailVerifyPanel';

function normalizeSignInIdentifier(raw) {
  const value = String(raw || '').trim();
  if (!value) return '';
  if (value.includes('#@admin@#')) {
    const marker = '#@admin@#';
    const lower = value.toLowerCase();
    const idx = lower.indexOf(marker);
    if (idx < 0) return value;
    return `${value.slice(0, idx).trim().toLowerCase()}${marker}`;
  }
  if (value.includes('@')) return value.toLowerCase();
  return normalizeRegistrationNumber(value) || value;
}

export default function LoginForm() {
  const navigate = useNavigate();
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [loading, setLoading] = useState(false);
  const [verifyEmail, setVerifyEmail] = useState('');
  const [verifyMessage, setVerifyMessage] = useState('');
  const [verifyVariant, setVerifyVariant] = useState('supervisor');
  const [emailJustVerified, setEmailJustVerified] = useState(false);
  const [forgotMode, setForgotMode] = useState(false);

  const canSubmit = useMemo(
    () => identifier.trim().length > 0 && password.length > 0 && !loading,
    [identifier, password, loading]
  );

  async function onSubmit(e) {
    e.preventDefault();
    setError('');
    setInfo('');
    setLoading(true);
    try {
      // Drop any expired tokens first so a background 401/refresh cannot wipe a fresh login.
      clearAuth();
      const submitId = normalizeSignInIdentifier(identifier);
      const data = await api('/auth/login/', {
        method: 'POST',
        body: { identifier: submitId, password },
        auth: false,
      });
      setAuth(data);
      if (!data?.user) {
        setError(
          'Sign-in almost worked, but we could not load your account. Please try again.'
        );
        return;
      }
      navigate(homePathFor(data.user));
    } catch (err) {
      if (err?.data?.pending_email_verification) {
        const submitId = normalizeSignInIdentifier(identifier);
        setVerifyEmail(err.data.email || identifier.trim());
        setVerifyMessage(
          err.message ||
            'Please verify your email with the code we sent you.'
        );
        setVerifyVariant(
          submitId.includes('#@admin@#') || identifier.includes('#@admin@#')
            ? 'main_admin'
            : 'supervisor'
        );
        return;
      }
      if (err?.data?.pending_approval) {
        setInfo(
          err.message ||
            'Your email is verified. Wait for approval before signing in.'
        );
        return;
      }
      setError(err.message || 'Could not sign in. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  if (forgotMode) {
    return (
      <div className="auth-form">
        <p className="auth-form-eyebrow">KabQue</p>
        <ForgotPasswordPanel
          initialIdentifier={identifier}
          onBack={() => setForgotMode(false)}
        />
      </div>
    );
  }

  if (emailJustVerified) {
    const needsApproval = verifyVariant !== 'main_admin';
    return (
      <div className="auth-form">
        <p className="auth-form-eyebrow">KabQue</p>
        <h1>Email confirmed</h1>
        <p className="auth-form-lead">
          {needsApproval
            ? 'Your email is verified. Wait for approval before signing in.'
            : 'Your email is verified. Sign in to continue.'}
        </p>
        <button
          type="button"
          className="btn btn-primary auth-submit"
          onClick={() => {
            setEmailJustVerified(false);
            setVerifyEmail('');
            setInfo('');
          }}
        >
          Back to sign in
        </button>
      </div>
    );
  }

  if (verifyEmail) {
    return (
      <div className="auth-form">
        <p className="auth-form-eyebrow">KabQue</p>
        <SupervisorEmailVerifyPanel
          email={verifyEmail}
          initialMessage={verifyMessage}
          variant={verifyVariant}
          onVerified={() => setEmailJustVerified(true)}
        />
        <p className="auth-switch">
          <button
            type="button"
            className="btn-linkish"
            onClick={() => {
              setVerifyEmail('');
              setVerifyMessage('');
            }}
          >
            Back to sign in
          </button>
        </p>
      </div>
    );
  }

  return (
    <form className="auth-form" onSubmit={onSubmit} noValidate>
      <p className="auth-form-eyebrow">KabQue</p>
      <h1>Sign in</h1>
      <p className="auth-form-lead">
        Freshers: use your registration number and password.
      </p>

      <Alert>{error}</Alert>
      {info ? <Alert variant="info">{info}</Alert> : null}

      <label className="auth-field">
        Registration number
        <input
          value={identifier}
          onChange={(e) => setIdentifier(e.target.value)}
          placeholder="e.g. 2026/A/BBA/3000/F"
          autoComplete="username"
          required
          spellCheck={false}
        />
      </label>
      <PasswordField
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        autoComplete="current-password"
        required
      />
      <div className="auth-forgot-row">
        <button
          type="button"
          className="btn-linkish"
          onClick={() => setForgotMode(true)}
        >
          Forgot password?
        </button>
      </div>
      <button className="btn btn-primary auth-submit" disabled={!canSubmit}>
        {loading ? 'Signing in…' : 'Sign in'}
      </button>
      <p className="auth-switch">
        New fresher? <Link to="/register">Create an account</Link>
      </p>
    </form>
  );
}
