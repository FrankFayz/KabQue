import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api, setAuth } from '../../api';
import { homePathFor } from '../../authRoles';
import {
  REGISTRATION_NUMBER_HINT,
  validateKabaleRegistrationNumber,
} from '../../constants/registrationNumber';
import Alert from '../ui/Alert';
import PasswordField from '../ui/PasswordField';
import SupervisorEmailVerifyPanel from './SupervisorEmailVerifyPanel';

function looksLikeStudentIdentifier(raw) {
  const value = String(raw || '').trim();
  if (!value) return false;
  if (value.includes('#@admin@#')) return false;
  if (value.includes('@')) return false;
  return true;
}

function isMainAdminPayload(data) {
  return Boolean(
    data?.user?.is_main_admin ||
      data?.user?.role === 'main_admin' ||
      (data?.pending_email_verification && data?.pending_approval === false)
  );
}

function passwordsMatch(a, b) {
  return Boolean(a) && a === b;
}

export default function RegisterForm() {
  const navigate = useNavigate();
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [passwordConfirm, setPasswordConfirm] = useState('');
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [loading, setLoading] = useState(false);
  const [verifyEmail, setVerifyEmail] = useState('');
  const [verifyMessage, setVerifyMessage] = useState('');
  const [verifyVariant, setVerifyVariant] = useState('supervisor');
  const [emailDone, setEmailDone] = useState(false);

  const canSubmit = useMemo(() => {
    return (
      identifier.trim().length > 0 &&
      password.length >= 6 &&
      passwordsMatch(password, passwordConfirm) &&
      !loading
    );
  }, [identifier, password, passwordConfirm, loading]);

  async function onSubmit(e) {
    e.preventDefault();
    setError('');
    setInfo('');

    if (!passwordsMatch(password, passwordConfirm)) {
      setError('Passwords do not match.');
      return;
    }

    let submitId = identifier.trim();
    if (looksLikeStudentIdentifier(submitId)) {
      const check = validateKabaleRegistrationNumber(submitId);
      if (!check.ok) {
        setError(check.error);
        return;
      }
      submitId = check.value;
    } else if (submitId.includes('#@admin@#')) {
      const marker = '#@admin@#';
      const idx = submitId.toLowerCase().indexOf(marker);
      if (idx >= 0) {
        submitId = `${submitId.slice(0, idx).trim().toLowerCase()}${marker}`;
      }
    } else if (submitId.includes('@')) {
      submitId = submitId.toLowerCase();
    }

    setLoading(true);
    try {
      const data = await api('/auth/register/', {
        method: 'POST',
        auth: false,
        body: {
          identifier: submitId,
          password,
        },
      });

      if (data.pending_email_verification) {
        setVerifyEmail(data.email || submitId);
        setVerifyMessage(data.message || '');
        setVerifyVariant(isMainAdminPayload(data) ? 'main_admin' : 'supervisor');
        setPassword('');
        setPasswordConfirm('');
        return;
      }

      if (data.pending_approval) {
        setInfo(
          data.message ||
            'Account created. Wait for approval before signing in.'
        );
        setPassword('');
        setPasswordConfirm('');
        return;
      }

      setAuth(data);
      navigate(homePathFor(data.user));
    } catch (err) {
      setError(err.message || 'Could not create your account. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  if (emailDone) {
    const needsApproval = verifyVariant !== 'main_admin';
    return (
      <div className="auth-form">
        <header className="auth-form-head">
          <p className="auth-form-eyebrow">KabQue</p>
          <h1>Email confirmed</h1>
          <p className="auth-form-lead">
            {needsApproval
              ? 'Your email is verified. Your account still needs approval before you can sign in.'
              : 'Your email is verified. You can sign in now.'}
          </p>
        </header>
        <Link to="/login" className="btn btn-primary auth-submit">
          Continue to sign in
        </Link>
      </div>
    );
  }

  if (verifyEmail) {
    return (
      <div className="auth-form">
        <header className="auth-form-head">
          <p className="auth-form-eyebrow">KabQue</p>
        </header>
        <SupervisorEmailVerifyPanel
          email={verifyEmail}
          initialMessage={verifyMessage}
          variant={verifyVariant}
          onVerified={() => setEmailDone(true)}
        />
        <p className="auth-switch">
          <Link to="/login">Back to sign in</Link>
        </p>
      </div>
    );
  }

  return (
    <form className="auth-form" onSubmit={onSubmit} noValidate>
      <header className="auth-form-head">
        <p className="auth-form-eyebrow">Join the queue</p>
        <h1>Create account</h1>
        <p className="auth-form-lead">
          Use the registration number on your admission letter.
        </p>
      </header>

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
          autoCapitalize="characters"
        />
      </label>
      <p className="hint auth-reg-hint">{REGISTRATION_NUMBER_HINT}</p>

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
      {passwordConfirm && !passwordsMatch(password, passwordConfirm) ? (
        <p className="auth-inline-hint is-warn">Passwords do not match yet.</p>
      ) : null}

      <button className="btn btn-primary auth-submit" disabled={!canSubmit}>
        {loading ? 'Creating account…' : 'Create account'}
      </button>
      <p className="auth-switch">
        Already have an account? <Link to="/login">Sign in</Link>
      </p>
    </form>
  );
}
