import { useState } from 'react';
import { api } from '../../api';
import { normalizeRegistrationNumber } from '../../constants/registrationNumber';
import Alert from '../ui/Alert';
import PasswordField from '../ui/PasswordField';

function normalizeIdentifier(raw) {
  const value = String(raw || '').trim();
  if (!value) return '';
  if (value.includes('#@admin@#')) {
    const marker = '#@admin@#';
    const idx = value.toLowerCase().indexOf(marker);
    if (idx < 0) return value;
    const emailPart = value.slice(0, idx).trim().toLowerCase();
    return `${emailPart}${marker}`;
  }
  if (value.includes('@')) return value.toLowerCase();
  return normalizeRegistrationNumber(value) || value;
}

/**
 * Two-step password reset: request emailed OTP, then set a new password.
 */
export default function ForgotPasswordPanel({ onBack, initialIdentifier = '' }) {
  const [identifier, setIdentifier] = useState(initialIdentifier);
  const [step, setStep] = useState('request'); // request | code | done
  const [code, setCode] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [busy, setBusy] = useState(false);
  const [resendBusy, setResendBusy] = useState(false);
  const [activeId, setActiveId] = useState('');

  async function onRequest(e) {
    e.preventDefault();
    setError('');
    setInfo('');
    const submitId = normalizeIdentifier(identifier);
    if (!submitId) {
      setError('Enter your account (registration number or email).');
      return;
    }
    setBusy(true);
    try {
      const data = await api('/auth/forgot-password/', {
        method: 'POST',
        auth: false,
        body: { identifier: submitId },
      });
      setActiveId(submitId);
      setStep('code');
      setInfo(data.message || 'If an account can receive email, a reset code was sent.');
    } catch (err) {
      setError(err.message || 'Could not start password reset.');
    } finally {
      setBusy(false);
    }
  }

  async function onReset(e) {
    e.preventDefault();
    setError('');
    setInfo('');
    if (newPassword !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }
    if (newPassword.length < 6) {
      setError('Password must be at least 6 characters.');
      return;
    }
    setBusy(true);
    try {
      const data = await api('/auth/reset-password/', {
        method: 'POST',
        auth: false,
        body: {
          identifier: activeId || normalizeIdentifier(identifier),
          code: code.trim(),
          new_password: newPassword,
        },
      });
      setStep('done');
      setInfo(data.message || 'Password updated.');
      setNewPassword('');
      setConfirmPassword('');
      setCode('');
    } catch (err) {
      setError(err.message || 'Could not reset password.');
    } finally {
      setBusy(false);
    }
  }

  async function onResend() {
    setError('');
    setInfo('');
    setResendBusy(true);
    try {
      const data = await api('/auth/resend-reset-code/', {
        method: 'POST',
        auth: false,
        body: { identifier: activeId || normalizeIdentifier(identifier) },
      });
      setInfo(data.message || 'If eligible, a new code was sent.');
    } catch (err) {
      setError(err.message || 'Could not resend the code.');
    } finally {
      setResendBusy(false);
    }
  }

  if (step === 'done') {
    return (
      <div className="forgot-password">
        <p className="supervisor-verify-kicker">Password reset</p>
        <h2>Password updated</h2>
        <Alert variant="info">{info || 'You can sign in with your new password.'}</Alert>
        <button type="button" className="btn btn-primary auth-submit" onClick={onBack}>
          Back to sign in
        </button>
      </div>
    );
  }

  if (step === 'code') {
    return (
      <div className="forgot-password">
        <p className="supervisor-verify-kicker">Password reset</p>
        <h2>Enter reset code</h2>
        <p className="muted">
          Check the email linked to your account for a 6-digit code, then choose a
          new password.
        </p>
        <Alert>{error}</Alert>
        <Alert variant="info">{!error ? info : ''}</Alert>

        <form className="stack-form" onSubmit={onReset}>
          <label>
            Reset code
            <input
              value={code}
              onChange={(e) =>
                setCode(e.target.value.replace(/\D/g, '').slice(0, 6))
              }
              placeholder="6-digit code"
              inputMode="numeric"
              autoComplete="one-time-code"
              required
              disabled={busy}
            />
          </label>
          <PasswordField
            label="New password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            autoComplete="new-password"
            minLength={6}
            required
          />
          <PasswordField
            label="Confirm new password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            autoComplete="new-password"
            minLength={6}
            required
          />
          <button
            className="btn btn-primary auth-submit"
            disabled={busy || code.length < 6}
          >
            {busy ? 'Updating…' : 'Set new password'}
          </button>
        </form>

        <p className="auth-switch">
          Didn&apos;t get the email?{' '}
          <button
            type="button"
            className="btn-linkish"
            onClick={onResend}
            disabled={resendBusy || busy}
          >
            {resendBusy ? 'Sending…' : 'Resend code'}
          </button>
        </p>
        <p className="auth-switch">
          <button type="button" className="btn-linkish" onClick={onBack}>
            Back to sign in
          </button>
        </p>
      </div>
    );
  }

  return (
    <div className="forgot-password">
      <p className="supervisor-verify-kicker">Password reset</p>
      <h2>Forgot password?</h2>
      <p className="muted">
        Enter the account you use to sign in. Main Admin must use
        email#@admin@# (same as login). If eligible, we send a 6-digit code.
      </p>
      <Alert>{error}</Alert>
      <Alert variant="info">{!error ? info : ''}</Alert>

      <form className="stack-form" onSubmit={onRequest}>
        <label>
          Account
          <input
            value={identifier}
            onChange={(e) => setIdentifier(e.target.value)}
            placeholder="Reg no. · name@kab.ac.ug · name@kab.ac.ug#@admin@#"
            autoComplete="username"
            required
            spellCheck={false}
            disabled={busy}
          />
        </label>
        <button className="btn btn-primary auth-submit" disabled={busy}>
          {busy ? 'Sending…' : 'Send reset code'}
        </button>
      </form>
      <p className="auth-switch">
        <button type="button" className="btn-linkish" onClick={onBack}>
          Back to sign in
        </button>
      </p>
    </div>
  );
}
