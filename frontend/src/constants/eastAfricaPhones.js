/** East African dial codes for SMS (international / E.164). */
export const EAST_AFRICAN_COUNTRIES = [
  { iso: 'UG', name: 'Uganda', dial: '256', flag: '🇺🇬' },
  { iso: 'KE', name: 'Kenya', dial: '254', flag: '🇰🇪' },
  { iso: 'TZ', name: 'Tanzania', dial: '255', flag: '🇹🇿' },
  { iso: 'RW', name: 'Rwanda', dial: '250', flag: '🇷🇼' },
  { iso: 'BI', name: 'Burundi', dial: '257', flag: '🇧🇮' },
  { iso: 'SS', name: 'South Sudan', dial: '211', flag: '🇸🇸' },
  { iso: 'ET', name: 'Ethiopia', dial: '251', flag: '🇪🇹' },
  { iso: 'SO', name: 'Somalia', dial: '252', flag: '🇸🇴' },
  { iso: 'CD', name: 'DR Congo', dial: '243', flag: '🇨🇩' },
  { iso: 'DJ', name: 'Djibouti', dial: '253', flag: '🇩🇯' },
  { iso: 'ER', name: 'Eritrea', dial: '291', flag: '🇪🇷' },
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

export function isValidE164(phone) {
  const value = String(phone || '').trim();
  if (!/^\+\d{10,15}$/.test(value)) return false;
  const digits = value.slice(1);
  return EAST_AFRICAN_COUNTRIES.some((c) => digits.startsWith(c.dial));
}
