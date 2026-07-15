const configured = (import.meta.env.VITE_API_URL || '').trim().replace(/\/$/, '');

// Never call the Vercel frontend host for API — always use Render in production.
const API_URL =
  configured && /^https?:\/\//i.test(configured)
    ? configured
    : import.meta.env.PROD
      ? 'https://kabque.onrender.com/api'
      : '/api';

const FRIENDLY_DEFAULT = 'Something went wrong. Please try again.';
const FRIENDLY_OFFLINE =
  'We could not connect right now. Check your internet and try again.';
const FRIENDLY_BUSY =
  'KabQue is busy right now. Please try again in a moment.';
const FRIENDLY_SESSION =
  'Your session expired. Please sign in again.';

function getToken() {
  return localStorage.getItem('kabque_access');
}

function getRefreshToken() {
  return localStorage.getItem('kabque_refresh');
}

export function setAuth(data) {
  if (data.access) localStorage.setItem('kabque_access', data.access);
  if (data.refresh) localStorage.setItem('kabque_refresh', data.refresh);
  if (data.user) localStorage.setItem('kabque_user', JSON.stringify(data.user));
}

export function clearAuth() {
  localStorage.removeItem('kabque_access');
  localStorage.removeItem('kabque_refresh');
  localStorage.removeItem('kabque_user');
}

export function getStoredUser() {
  try {
    return JSON.parse(localStorage.getItem('kabque_user') || 'null');
  } catch {
    return null;
  }
}

let refreshPromise = null;

async function refreshAccessToken() {
  const refresh = getRefreshToken();
  if (!refresh) return null;

  if (!refreshPromise) {
    const attemptedRefresh = refresh;
    refreshPromise = (async () => {
      let res;
      try {
        res = await fetch(`${API_URL}/auth/refresh/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh: attemptedRefresh }),
          cache: 'no-store',
        });
      } catch {
        return null;
      }

      // User may have signed in again while this refresh was in flight — keep the new session.
      if (getRefreshToken() && getRefreshToken() !== attemptedRefresh) {
        return getToken();
      }

      if (!res.ok) {
        // Only wipe storage if it is still the same expired session we tried to refresh.
        if (getRefreshToken() === attemptedRefresh) {
          clearAuth();
        }
        return null;
      }

      const data = await res.json().catch(() => null);
      if (!data) return null;

      if (getRefreshToken() && getRefreshToken() !== attemptedRefresh) {
        return getToken();
      }

      if (data.access) {
        localStorage.setItem('kabque_access', data.access);
      }
      if (data.refresh) {
        localStorage.setItem('kabque_refresh', data.refresh);
      }
      return data.access || null;
    })().finally(() => {
      refreshPromise = null;
    });
  }

  return refreshPromise;
}

function looksLikeHtml(text) {
  const t = String(text || '').trim().toLowerCase();
  return (
    t.startsWith('<!doctype') ||
    t.startsWith('<html') ||
    t.includes('<h1>server error') ||
    t.includes('server error (500)')
  );
}

/** True when the text looks like a stack dump / infra noise, not a person-safe message. */
function looksTechnical(text) {
  const t = String(text || '');
  if (!t.trim()) return true;
  if (looksLikeHtml(t)) return true;
  return (
    /traceback \(most recent call last\)/i.test(t) ||
    /<\/?[a-z][\s\S]*>/i.test(t) ||
    /\b(IntegrityError|OperationalError|ProgrammingError|DoesNotExist|TypeError|ValueError|KeyError|AttributeError|ValidationError)\b/i.test(
      t
    ) ||
    /\b(psycopg2|django\.db|django\.core|celery|gunicorn|uvicorn|rest_framework)\b/i.test(
      t
    ) ||
    /\b(NOT_FOUND|Code:\s*NOT_FOUND|INTERNAL_SERVER_ERROR|BAD_GATEWAY)\b/i.test(t) ||
    /\b(VITE_API_URL|ECONNREFUSED|ENOTFOUND|ETIMEDOUT|CORS|JWT)\b/i.test(t) ||
    /\b(SMTP|SSLError|socket\.gaierror|Connection refused)\b/i.test(t) ||
    /File ".+", line \d+/i.test(t) ||
    /at [\w.$]+ \(.+:\d+:\d+\)/.test(t) ||
    /Unexpected token|JSON\.parse|SyntaxError/i.test(t) ||
    /ErrorDetail\b|undefined is not|is not a function|Cannot read propert/i.test(t) ||
    /[{}\[\]`]/.test(t) ||
    /\b[a-z]+_[a-z0-9_]+\b/i.test(t) || // snake_case API codes / field names
    /\bhttps?:\/\//i.test(t) ||
    /\bstatus[_ ]?code\b/i.test(t) ||
    /\b(null|undefined|NaN)\b/.test(t)
  );
}

/** Safe enough to show a student or desk staff member. */
function looksUserSafe(text) {
  const t = String(text || '').trim();
  if (!t || t.length > 220) return false;
  if (looksTechnical(t)) return false;
  if (/^[A-Z0-9_]{6,}$/.test(t)) return false;
  // At least two readable words (allows punctuation / dashes between them)
  const words = t.split(/\s+/).filter((w) => /[A-Za-z]{2,}/.test(w));
  return words.length >= 2;
}

function humanizeHttpError(status, fallback = FRIENDLY_DEFAULT, { auth = true } = {}) {
  if (status === 401) {
    return auth
      ? FRIENDLY_SESSION
      : 'Could not sign in. Check your details and try again.';
  }
  if (status === 403) {
    return 'You do not have permission for that action.';
  }
  if (status === 404) {
    return 'We could not find what you asked for. Refresh the page and try again.';
  }
  if (status === 429) {
    return 'Too many attempts. Please wait a moment, then try again.';
  }
  if (status === 502 || status === 503 || status === 504) {
    return FRIENDLY_BUSY;
  }
  if (status >= 500) {
    return 'Something went wrong on our side. Please refresh and try again.';
  }
  return fallback;
}

/**
 * Phrase map: technical / abrupt API text → calm user copy.
 * Order matters — first match wins.
 */
const FRIENDLY_PHRASES = [
  [
    /invalid credentials\.?/i,
    'That account or password does not match. Check and try again.',
  ],
  [
    /that account or password does not match/i,
    'That account or password does not match. Check and try again.',
  ],
  [
    /authentication credentials were not provided/i,
    'Please sign in again to continue.',
  ],
  [
    /given token not valid|token is invalid|token_not_valid|token_expired|token not valid/i,
    FRIENDLY_SESSION,
  ],
  [
    /cannot reach kabque api|vite_api_url|django is running/i,
    FRIENDLY_OFFLINE,
  ],
  [/failed to fetch|networkerror|load failed|network request failed/i, FRIENDLY_OFFLINE],
  [/kabque api is unavailable/i, FRIENDLY_BUSY],
  [/server error\.?\s*please refresh/i, 'Something went wrong on our side. Please refresh and try again.'],
  [
    /service endpoint not found|request failed/i,
    FRIENDLY_DEFAULT,
  ],
  [
    /could not send (verification )?email\s*:?.*/i,
    'We could not send the email just now. Check the address or try again shortly.',
  ],
  [
    /could not send.*(?:sms|message)\s*:?.*/i,
    'We could not send that message just now. Please try again shortly.',
  ],
  [/this field may not be blank|this field is required/i, 'Please fill in all required fields.'],
  [/ensure this field has at least/i, 'Please check the information you entered.'],
  [/enter a valid email address/i, 'Please enter a valid email address.'],
  [/already belongs to another account/i, 'That email or phone is already used by another account. Try different contact details.'],
  [/telephone number is required/i, 'Telephone number is required for SMS notifications.'],
  [/enter a valid .* mobile number/i, 'Enter a complete mobile number with country code (e.g. Uganda 7XXXXXXXX).'],
  [/a valid number is required|a valid integer is required|must be a valid/i, 'Please check the information you entered.'],
  [
    /a user with that username already exists|user with this .+ already exists/i,
    'That account is already registered. Try signing in instead.',
  ],
  [
    /unique constraint|duplicate key|already exists/i,
    'That information is already in use. Try a different value.',
  ],
  [
    /no student profile/i,
    'Your student profile is incomplete. Finish signup, then try again.',
  ],
  [/student access only|queue admin|main admin only/i, 'You do not have permission for that page.'],
  [/queue_entry_id is required|queue entry id/i, 'Please select a student and try again.'],
  [
    /queue entry not found/i,
    'That queue record was not found. Refresh and try again.',
  ],
  [/batch not found/i, 'That batch was not found. Refresh and try again.'],
  [/user not found|no account found/i, 'We could not find that account.'],
  [/invalid or expired reset code|invalid or expired/i, 'That code is invalid or has expired. Request a new one.'],
  [/unable to create account/i, 'We could not create your account right now. Please try again.'],
  [/you are already in the queue/i, 'You are already in the queue.'],
  [/you are not in the queue/i, 'You are not in the queue right now.'],
  [/this queue result is already final/i, 'This visit is already finished and cannot be changed.'],
  [/this entry cannot be rescheduled/i, 'This student cannot be rescheduled right now.'],
  [/invalid secret code/i, 'That secret code does not match any fresher. Check and try again.'],
  [/has not been notified yet/i, 'Notify this student first, then verify their code.'],
  [/no students could be notified/i, 'No students could be notified. Try again.'],
  [
    /geolocation is not supported/i,
    'This device cannot share location. Try another phone or browser.',
  ],
  [
    /unable to read gps|unable to read gps location/i,
    'We could not read your GPS. Allow location and try outdoors.',
  ],
  [
    /outside the (campus|allowed)|not on campus|too far from campus/i,
    'You must be on campus to join the queue. Move closer and try again.',
  ],
  [
    /gps accuracy|location accuracy|accuracy (is )?too (low|high|poor)/i,
    'GPS accuracy is too weak. Move outdoors and try again.',
  ],
  [
    /sign in succeeded but no user/i,
    'Sign-in almost worked, but we could not load your account. Please try again.',
  ],
  [/you are already in the queue/i, 'You are already in the queue.'],
  [
    /already approved at the desk|cannot join the queue again/i,
    'Your desk visit is complete. You cannot join the queue again.',
  ],
  [
    /documents were not accepted|not accepted on this attempt/i,
    'Your desk visit is complete. You cannot join the queue again.',
  ],
  [/account has been locked|account_locked/i, 'This account has been locked. Contact Main Admin.'],
  [
    /cannot (lock|delete|remove|modify) your own|your own account/i,
    'You cannot change your own account here. Ask another Main Admin.',
  ],
  [
    /last (active )?main admin|only main admin/i,
    'Keep at least one Main Admin who can sign in. Add another first, then try again.',
  ],
  [/permission denied|not authenticated|is_authenticated/i, 'Please sign in again to continue.'],
  [/method ["']?\w+["']? not allowed/i, FRIENDLY_DEFAULT],
  [/csrf|forbidden \(403\)/i, 'You do not have permission for that action.'],
];

/**
 * Turn any raw API / browser error into calm text safe to show students & staff.
 */
export function friendlyUserMessage(raw, fallback = FRIENDLY_DEFAULT) {
  let text = '';
  if (raw == null || raw === '') {
    text = '';
  } else if (typeof raw === 'string') {
    text = raw.trim();
  } else if (raw instanceof Error) {
    text = String(raw.message || '').trim();
  } else if (typeof raw === 'object') {
    text = extractRawMessage(raw, '').trim();
  } else {
    text = String(raw).trim();
  }

  if (!text) {
    return fallback || FRIENDLY_DEFAULT;
  }

  for (const [pattern, message] of FRIENDLY_PHRASES) {
    if (pattern.test(text)) return message;
  }

  // Strip "Could not …: technical residual" style prefixes when the rest is noisy
  const colonSplit = text.match(/^([^:]{8,80}):\s*(.+)$/);
  if (colonSplit && looksTechnical(colonSplit[2])) {
    const head = colonSplit[1].trim();
    if (looksUserSafe(`${head}. Please try again.`)) {
      return `${head}. Please try again.`;
    }
    return fallback || FRIENDLY_DEFAULT;
  }

  if (looksUserSafe(text)) {
    return text;
  }

  return fallback || FRIENDLY_DEFAULT;
}

/** Use in catch blocks: userError(err, 'Could not save.') */
export function userError(err, fallback = FRIENDLY_DEFAULT) {
  if (err == null || err === '') return fallback;
  if (typeof err === 'string') return friendlyUserMessage(err, fallback);
  if (err instanceof Error) {
    return friendlyUserMessage(err.message || err.data || err, fallback);
  }
  if (typeof err === 'object') {
    if (err.message) return friendlyUserMessage(err.message, fallback);
    if (err.data) return friendlyUserMessage(extractRawMessage(err.data, ''), fallback);
    return friendlyUserMessage(extractRawMessage(err, ''), fallback);
  }
  return friendlyUserMessage(err, fallback);
}

const SKIP_ERROR_KEYS = new Set([
  'code',
  'messages',
  'status_code',
  'status',
  'pending_email_verification',
  'pending_approval',
  'account_locked',
  'email_verified',
  'sms_configured',
  'sms_failed',
  'sms_errors',
  'user',
  'profile',
  'access',
  'refresh',
]);

const FIELD_ERROR_LABELS = {
  full_name: 'Name',
  email: 'Email',
  phone: 'Telephone',
  faculty: 'Faculty',
  programme: 'Programme',
  registration_number: 'Registration number',
  identifier: 'Account',
  password: 'Password',
  non_field_errors: 'Form',
};

function flattenFieldErrors(value) {
  if (value == null) return [];
  if (Array.isArray(value)) return value.flatMap(flattenFieldErrors);
  if (typeof value === 'object') {
    return Object.entries(value).flatMap(([key, val]) => {
      const nested = flattenFieldErrors(val);
      if (!nested.length) return [];
      const label = FIELD_ERROR_LABELS[key] || key.replaceAll('_', ' ');
      return nested.map((msg) => (label ? `${label}: ${msg}` : msg));
    });
  }
  const text = String(value).trim();
  return text ? [text] : [];
}

function extractRawMessage(data, fallback = FRIENDLY_DEFAULT) {
  if (data == null) return fallback;
  if (typeof data === 'string') {
    const text = data.trim();
    if (!text || looksLikeHtml(text) || /NOT_FOUND/i.test(text)) return fallback;
    return text;
  }

  const vercelCode = data?.error?.code || data?.code;
  if (vercelCode === 'NOT_FOUND' || data?.error === 'NOT_FOUND') {
    return fallback;
  }

  const detail = data.detail;
  if (detail != null) {
    if (Array.isArray(detail)) return detail.flat().map(String).join(' ') || fallback;
    if (typeof detail === 'object') {
      const fromDetail = flattenFieldErrors(detail).join(' ');
      if (fromDetail) return fromDetail;
      try {
        return Object.values(detail).flat().map(String).join(' ') || fallback;
      } catch {
        return fallback;
      }
    }
    return String(detail);
  }

  const loc = data.location;
  if (Array.isArray(loc)) return loc.map(String).join(' ') || fallback;
  if (typeof loc === 'string' && loc) return loc;

  if (Array.isArray(data.non_field_errors) && data.non_field_errors.length) {
    return data.non_field_errors.map(String).join(' ');
  }

  if (typeof data === 'object') {
    try {
      const fieldParts = [];
      for (const [key, val] of Object.entries(data)) {
        if (SKIP_ERROR_KEYS.has(key)) continue;
        if (val == null || val === '' || typeof val === 'boolean' || typeof val === 'number') {
          continue;
        }
        if (Array.isArray(val)) {
          const joined = val.map(String).filter(Boolean).join(' ');
          if (joined) {
            const label = FIELD_ERROR_LABELS[key];
            fieldParts.push(label ? `${label}: ${joined}` : joined);
          }
        } else if (typeof val === 'string') {
          const label = FIELD_ERROR_LABELS[key];
          fieldParts.push(label ? `${label}: ${val}` : val);
        } else if (typeof val === 'object') {
          const nested = flattenFieldErrors(val).join(' ');
          if (nested) fieldParts.push(nested);
        }
      }
      if (fieldParts.length) return fieldParts.join(' ');
    } catch {
      return fallback;
    }
  }

  return fallback;
}

function errorFromPayload(data, status = 0, { auth = true } = {}) {
  const statusFallback = humanizeHttpError(status, FRIENDLY_DEFAULT, { auth });
  if (status >= 500 || status === 502 || status === 503 || status === 504) {
    return statusFallback;
  }

  const raw = extractRawMessage(data, '');
  if (raw) {
    const friendly = friendlyUserMessage(raw, statusFallback);
    // Never leak a technical raw string — friendlyUserMessage already gates this
    if (friendly) return friendly;
  }

  if (status === 401) return statusFallback;
  return statusFallback;
}

async function request(path, { method = 'GET', body, auth = true, _retried = false } = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (auth) {
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  let res;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
      cache: 'no-store',
    });
  } catch {
    throw new Error(FRIENDLY_OFFLINE);
  }

  let data = null;
  const text = await res.text();
  if (looksLikeHtml(text)) {
    data = null;
  } else {
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = text ? { detail: text } : null;
    }
  }

  if (res.status === 401 && auth && !_retried) {
    const newAccess = await refreshAccessToken();
    if (newAccess) {
      return request(path, { method, body, auth, _retried: true });
    }
  }

  if (!res.ok) {
    const err = new Error(errorFromPayload(data, res.status, { auth }));
    err.status = res.status;
    err.data = data;
    throw err;
  }

  return data;
}

export async function api(path, options = {}) {
  return request(path, options);
}

export function getCurrentPosition() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(
        new Error('This device cannot share location. Try another phone or browser.')
      );
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) =>
        resolve({
          latitude: pos.coords.latitude,
          longitude: pos.coords.longitude,
          accuracy: pos.coords.accuracy,
        }),
      (err) => {
        const map = {
          1: 'Location permission denied. Allow GPS for KabQue and try again.',
          2: 'GPS signal is weak. Move outdoors or wait for a stronger fix.',
          3: 'GPS timed out. Move to open sky and try again.',
        };
        reject(
          new Error(
            map[err?.code] ||
              'We could not read your GPS. Allow location and try outdoors.'
          )
        );
      },
      { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 }
    );
  });
}

// Prefer captureCampusLocation from geo/campusLocation.js for join-queue.
