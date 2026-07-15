/** Kabale University student registration number (client-side check). */

// YEAR/A/PROGRAMME/SERIAL/F  or  YEAR/A/PROGRAMME/SERIAL/G/F
const KABALE_REG_RE =
  /^(\d{4})\/A\/([A-Z]{1,24})\/(\d{1,10})(?:\/G)?\/F$/;

export const REGISTRATION_NUMBER_HINT =
  'Kabale format: 2026/A/BBA/3000/F or 2026/A/BBA/3000/G/F (government-sponsored).';

export function normalizeRegistrationNumber(value) {
  let raw = String(value || '')
    .trim()
    .toUpperCase();
  if (!raw) return '';
  raw = raw.replace(/\s*\/\s*/g, '/').replace(/\s+/g, '');
  return raw;
}

/**
 * @returns {{ ok: true, value: string } | { ok: false, error: string }}
 */
export function validateKabaleRegistrationNumber(value) {
  const reg = normalizeRegistrationNumber(value);
  if (!reg) {
    return { ok: false, error: 'Registration number is required.' };
  }
  const match = KABALE_REG_RE.exec(reg);
  if (!match) {
    return {
      ok: false,
      error:
        'Invalid registration number. Use YEAR/A/PROGRAMME/SERIAL/F or …/G/F (e.g. 2026/A/BBA/3000/F).',
    };
  }
  const year = Number(match[1]);
  if (year < 2000 || year > 2100) {
    return {
      ok: false,
      error: 'Registration year looks invalid. Check your admission letter.',
    };
  }
  return { ok: true, value: reg };
}
