import { useEffect, useState } from 'react';
import {
  EAST_AFRICAN_COUNTRIES,
  splitPhone,
  toE164,
} from '../../constants/eastAfricaPhones';

/**
 * East-Africa country dial selector + national number.
 * Emits full E.164 (+CC…) via onChange for SMS gateways.
 */
export default function PhoneInput({
  id = 'phone',
  value = '',
  onChange,
  disabled = false,
  required = false,
  placeholder = '7XXXXXXXX',
}) {
  const [dial, setDial] = useState(() => splitPhone(value).dial);
  const [national, setNational] = useState(() => splitPhone(value).national);

  useEffect(() => {
    const composed = toE164(dial, national);
    if ((value || '') === composed) return;
    const next = splitPhone(value || '');
    setDial(next.dial);
    setNational(next.national);
    // Only re-sync when the parent-controlled value changes externally
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  function emit(nextDial, nextNational) {
    onChange?.(toE164(nextDial, nextNational));
  }

  function handleDial(e) {
    const nextDial = e.target.value;
    setDial(nextDial);
    emit(nextDial, national);
  }

  function handleNational(e) {
    const raw = e.target.value.replace(/[^\d\s-]/g, '');
    setNational(raw);
    emit(dial, raw);
  }

  const preview = toE164(dial, national);
  const selected = EAST_AFRICAN_COUNTRIES.find((c) => c.dial === dial);

  return (
    <div className="phone-input">
      <div className="phone-input-row">
        <label className="phone-input-country" htmlFor={`${id}-country`}>
          <span className="phone-input-label">Country</span>
          <select
            id={`${id}-country`}
            value={dial}
            onChange={handleDial}
            disabled={disabled}
            aria-label="Country code"
            required={required}
            title={selected ? `${selected.name} (+${selected.dial})` : 'Country'}
          >
            {EAST_AFRICAN_COUNTRIES.map((c) => (
              <option key={c.iso} value={c.dial} title={`${c.name} (+${c.dial})`}>
                {c.name} +{c.dial}
              </option>
            ))}
          </select>
        </label>
        <label className="phone-input-national" htmlFor={id}>
          <span className="phone-input-label">Mobile number</span>
          <input
            id={id}
            type="tel"
            inputMode="numeric"
            autoComplete="tel-national"
            value={national}
            onChange={handleNational}
            placeholder={placeholder}
            disabled={disabled}
            required={required}
            aria-label="Phone number"
          />
        </label>
      </div>
      <p className="phone-input-preview">
        SMS will go to <strong>{preview || '—'}</strong>
      </p>
    </div>
  );
}
