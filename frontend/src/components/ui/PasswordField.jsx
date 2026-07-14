import { useId, useState } from 'react';

function EyeOpenIcon() {
  return (
    <svg
      className="password-field-icon"
      viewBox="0 0 24 24"
      width="20"
      height="20"
      aria-hidden="true"
      focusable="false"
    >
      <path
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M2.2 12S5.6 5.5 12 5.5 21.8 12 21.8 12 18.4 18.5 12 18.5 2.2 12 2.2 12z"
      />
      <circle
        cx="12"
        cy="12"
        r="3.1"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
      />
    </svg>
  );
}

function EyeOffIcon() {
  return (
    <svg
      className="password-field-icon"
      viewBox="0 0 24 24"
      width="20"
      height="20"
      aria-hidden="true"
      focusable="false"
    >
      <path
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M3.2 3.2l17.6 17.6"
      />
      <path
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M9.88 9.9A3.1 3.1 0 0 0 12 15.1c.72 0 1.38-.25 1.9-.66"
      />
      <path
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M6.6 6.72C4.55 8.05 3.1 10.05 2.2 12c0 0 3.4 6.5 9.8 6.5 1.72 0 3.25-.4 4.55-1.02"
      />
      <path
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M17.55 14.9c1.4-1.12 2.55-2.55 3.25-3.4 0 0-3.4-6.5-9.8-6.5-1.05 0-2.05.2-2.95.5"
      />
    </svg>
  );
}

export default function PasswordField({
  label = 'Password',
  value,
  onChange,
  autoComplete = 'current-password',
  required = false,
  minLength,
  id: idProp,
  name,
}) {
  const autoId = useId();
  const id = idProp || autoId;
  const [visible, setVisible] = useState(false);

  return (
    <label className="password-field" htmlFor={id}>
      {label}
      <span className="password-field-control">
        <input
          id={id}
          name={name}
          type={visible ? 'text' : 'password'}
          value={value}
          onChange={onChange}
          autoComplete={autoComplete}
          required={required}
          minLength={minLength}
          spellCheck={false}
        />
        <button
          type="button"
          className="password-field-toggle"
          onClick={() => setVisible((v) => !v)}
          aria-label={visible ? 'Hide password' : 'Show password'}
          aria-pressed={visible}
        >
          {visible ? <EyeOffIcon /> : <EyeOpenIcon />}
        </button>
      </span>
    </label>
  );
}
