/** East African dial codes for SMS (international / E.164). */
export const EAST_AFRICAN_COUNTRIES = [
  { iso: 'UG', name: 'Uganda', dial: '256', flag: '🇺🇬', min: 9, max: 9 },
  { iso: 'KE', name: 'Kenya', dial: '254', flag: '🇰🇪', min: 9, max: 9 },
  { iso: 'TZ', name: 'Tanzania', dial: '255', flag: '🇹🇿', min: 9, max: 9 },
  { iso: 'RW', name: 'Rwanda', dial: '250', flag: '🇷🇼', min: 9, max: 9 },
  { iso: 'BI', name: 'Burundi', dial: '257', flag: '🇧🇮', min: 8, max: 8 },
  { iso: 'SS', name: 'South Sudan', dial: '211', flag: '🇸🇸', min: 9, max: 9 },
  { iso: 'ET', name: 'Ethiopia', dial: '251', flag: '🇪🇹', min: 9, max: 9 },
  { iso: 'SO', name: 'Somalia', dial: '252', flag: '🇸🇴', min: 8, max: 9 },
  { iso: 'CD', name: 'DR Congo', dial: '243', flag: '🇨🇩', min: 9, max: 9 },
  { iso: 'DJ', name: 'Djibouti', dial: '253', flag: '🇩🇯', min: 8, max: 8 },
  { iso: 'ER', name: 'Eritrea', dial: '291', flag: '🇪🇷', min: 7, max: 7 },
];

const DEFAULT_DIAL = '256';

export function digitsOnly(value = '') {
  return String(value || '').replace(/\D/g, '');
}

/** Strip leading trunk zero from a national number. */
export function stripTrunkZero(national = '') {
  const digits = digitsOnly(national);
  if (digits.startsWith('0')) return digits.replace(/^0+/, '');
  return digits;
}

/**
 * Combine country dial code + national number into E.164 (+CC…).
 * Returns '' when national part is empty.
 */
export function toE164(dialCode, nationalNumber) {
  const dial = digitsOnly(dialCode) || DEFAULT_DIAL;
  let national = stripTrunkZero(nationalNumber);
  if (!national) return '';

  // If the user pasted a full international number into the local field
  if (national.startsWith(dial) && national.length > dial.length + 5) {
    national = national.slice(dial.length);
  }

  return `+${dial}${national}`;
}

/**
 * Split a stored phone into { dial, national } for the input UI.
 */
export function splitPhone(phone) {
  const raw = String(phone || '').trim();
  if (!raw) {
    return { dial: DEFAULT_DIAL, national: '' };
  }

  let digits = digitsOnly(raw);
  if (raw.startsWith('00')) {
    digits = digits.slice(2);
  }

  const match = EAST_AFRICAN_COUNTRIES.find((c) => digits.startsWith(c.dial));
  if (match) {
    return {
      dial: match.dial,
      national: digits.slice(match.dial.length),
    };
  }

  // Legacy local UG numbers saved as 07…
  if (digits.startsWith('0') && digits.length >= 9) {
    return { dial: DEFAULT_DIAL, national: digits.replace(/^0+/, '') };
  }

  return { dial: DEFAULT_DIAL, national: digits };
}

/**
 * Match backend validate_east_africa_phone — full national length required.
 */
export function validateEastAfricaPhone(phone) {
  const value = String(phone || '').trim();
  if (!value) {
    return {
      ok: false,
      error: 'Telephone number is required for SMS notifications.',
    };
  }
  if (!value.startsWith('+')) {
    return {
      ok: false,
      error: 'Phone must include a country code (select Uganda, Kenya, etc.).',
    };
  }

  const digits = value.slice(1);
  const country = EAST_AFRICAN_COUNTRIES.find((c) => digits.startsWith(c.dial));
  if (!country) {
    return {
      ok: false,
      error:
        'Use an East African country code (Uganda +256, Kenya +254, Tanzania +255, etc.).',
    };
  }

  let national = digits.slice(country.dial.length);
  if (national.startsWith('0')) {
    national = national.replace(/^0+/, '');
  }

  const min = country.min ?? 9;
  const max = country.max ?? 9;
  if (!/^\d+$/.test(national) || national.length < min || national.length > max) {
    const example = country.dial === '256' ? '7XXXXXXXX' : 'XXXXXXXXX';
    return {
      ok: false,
      error: `Enter a valid ${country.name} mobile number (${min}${
        max !== min ? `–${max}` : ''
      } digits after +${country.dial}, e.g. ${example}).`,
    };
  }

  return { ok: true, value: `+${country.dial}${national}` };
}

export function isValidE164(phone) {
  return validateEastAfricaPhone(phone).ok;
}
