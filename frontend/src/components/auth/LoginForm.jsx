import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api, setAuth } from '../../api';
import { homePathFor } from '../../authRoles';
import Alert from '../ui/Alert';
import PasswordField from '../ui/PasswordField';

export default function LoginForm() {
  const navigate = useNavigate();
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function onSubmit(e) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const data = await api('/auth/login/', {
        method: 'POST',
        body: { identifier: identifier.trim(), password },
        auth: false,
      });
      setAuth(data);
      if (!data?.user) {
        setError('Sign in succeeded but no user was returned. Try again.');
        return;
      }
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
      <h1>Sign in</h1>
      <Alert>{error}</Alert>
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
        autoComplete="current-password"
        required
      />
      <button className="btn btn-primary auth-submit" disabled={loading}>
        {loading ? 'Signing in…' : 'Sign in'}
      </button>
      <p className="auth-switch">
        New here? <Link to="/register">Create an account</Link>
      </p>
    </form>
  );
}
