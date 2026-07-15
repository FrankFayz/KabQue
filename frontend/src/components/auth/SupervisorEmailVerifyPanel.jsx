import { useState } from 'react';
import { api } from '../../api';
import Alert from '../ui/Alert';

/**
 * Signup email OTP panel. Copy stays role-neutral in the UI.
 */
export default function SupervisorEmailVerifyPanel({
  email,
  initialMessage = '',
  onVerified,
  variant = 'supervisor',
}) {
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [info, setInfo] = useState(initialMessage);
  const [busy, setBusy] = useState(false);
  const [resendBusy, setResendBusy] = useState(false);

  async function onVerify(e) {
    e.preventDefault();
    setError('');
    setInfo('');
    const trimmed = code.trim();
    if (!trimmed) {
      setError('Enter the verification code from your email.');
      return;
    }
    setBusy(true);
    try {
      const data = await api('/auth/verify-supervisor-email/', {
        method: 'POST',
        auth: false,
        body: { email, code: trimmed },
      });
      setInfo(data.message || 'Email verified.');
      onVerified?.(data);
    } catch (err) {
      setError(err.message || 'Could not verify that code.');
    } finally {
      setBusy(false);
    }
  }

  async function onResend() {
    setError('');
    setInfo('');
    setResendBusy(true);
    try {
      const data = await api('/auth/resend-supervisor-code/', {
        method: 'POST',
        auth: false,
        body: { email },
      });
      setInfo(data.message || 'A new code was sent.');
    } catch (err) {
      setError(err.message || 'Could not resend the code.');
    } finally {
      setResendBusy(false);
    }
  }

  return (
    <div className="supervisor-verify">
      <p className="supervisor-verify-kicker">Email verification</p>
      <h2>Confirm your email</h2>
      <p className="muted">
        We sent a 6-digit code to <strong>{email}</strong>. Enter it below to
        continue
        {variant === 'main_admin' ? '.' : '. Approval may still be required after this.'}
      </p>

      <Alert>{error}</Alert>
      <Alert variant="info">{!error ? info : ''}</Alert>

      <form className="stack-form" onSubmit={onVerify}>
        <label>
          Verification code
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
        <button className="btn btn-primary auth-submit" disabled={busy || code.length < 6}>
          {busy ? 'Verifying…' : 'Verify email'}
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
    </div>
  );
}
