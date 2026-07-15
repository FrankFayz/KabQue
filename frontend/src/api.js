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
    refreshPromise = (async () => {
      const res = await fetch(`${API_URL}/auth/refresh/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh }),
        cache: 'no-store',
      });
      if (!res.ok) {
        clearAuth();
        return null;
      }
      const data = await res.json();
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
    /\b(IntegrityError|OperationalError|ProgrammingError|DoesNotExist|TypeError|ValueError|KeyError)\b/i.test(
      t
    ) ||
    /\b(psycopg2|django\.db|django\.core|celery|gunicorn|uvicorn)\b/i.test(t) ||
    /\b(NOT_FOUND|Code:\s*NOT_FOUND|INTERNAL_SERVER_ERROR)\b/i.test(t) ||
    /\b(VITE_API_URL|ECONNREFUSED|ENOTFOUND|ETIMEDOUT|CORS)\b/i.test(t) ||
    /\b(SMTP|SSLError|socket\.gaierror|Connection refused)\b/i.test(t) ||
    /File ".+", line \d+/i.test(t) ||
    /at [\w.$]+ \(.+:\d+:\d+\)/.test(t) ||
    /Unexpected token|JSON\.parse|SyntaxError/i.test(t)
  );
}

function humanizeHttpError(status, fallback = FRIENDLY_DEFAULT) {
  if (status === 401) return FRIENDLY_SESSION;
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
    /authentication credentials were not provided/i,
    'Please sign in again to continue.',
  ],
  [
    /given token not valid|token is invalid|token_not_valid|token_expired/i,
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
  [/student access only/i, 'This page is for students only.'],
  [/queue_entry_id is required/i, 'Please select a student and try again.'],
  [
    /queue entry not found/i,
    'That queue record was not found. Refresh and try again.',
  ],
  [/batch not found/i, 'That batch was not found. Refresh and try again.'],
  [/user not found/i, 'We could not find that account.'],
  [
    /geolocation is not supported/i,
    'This device cannot share location. Try another phone or browser.',
  ],
  [
    /unable to read gps|unable to read gps location/i,
    'We could not read your GPS. Allow location and try outdoors.',
  ],
  [
    /sign in succeeded but no user/i,
    'Sign-in almost worked, but we could not load your account. Please try again.',
  ],
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
  } else {
    text = String(raw).trim();
  }

  if (!text || looksTechnical(text)) {
    return fallback || FRIENDLY_DEFAULT;
  }

  for (const [pattern, message] of FRIENDLY_PHRASES) {
    if (pattern.test(text)) return message;
  }

  // Strip "Could not …: technical residual" style prefixes when the rest is noisy
  const colonSplit = text.match(/^([^:]{8,80}):\s*(.+)$/);
  if (colonSplit && looksTechnical(colonSplit[2])) {
    return `${colonSplit[1].trim()}. Please try again.`;
  }

  // Cap extremely long dumps
  if (text.length > 280) {
    return fallback || FRIENDLY_DEFAULT;
  }

  return text;
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

  if (typeof data === 'object') {
    try {
      const parts = Object.values(data)
        .flat()
        .filter((v) => v != null && v !== '')
        .map(String);
      if (parts.length) return parts.join(' ');
    } catch {
      return fallback;
    }
  }

  return fallback;
}

function errorFromPayload(data, status = 0) {
  const statusFallback = humanizeHttpError(status, FRIENDLY_DEFAULT);
  if (status >= 500 || status === 502 || status === 503 || status === 504) {
    return statusFallback;
  }
  if (status === 401) return FRIENDLY_SESSION;

  const raw = extractRawMessage(data, statusFallback);
  if (looksLikeHtml(raw) || looksTechnical(raw) || /NOT_FOUND/i.test(raw) || /Server Error \(500\)/i.test(raw)) {
    return statusFallback;
  }
  return friendlyUserMessage(raw, statusFallback);
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
    const err = new Error(errorFromPayload(data, res.status));
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
