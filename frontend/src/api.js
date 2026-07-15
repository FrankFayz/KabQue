const configured = (import.meta.env.VITE_API_URL || '').trim().replace(/\/$/, '');

// Never call the Vercel frontend host for API — always use Render in production.
const API_URL =
  configured && /^https?:\/\//i.test(configured)
    ? configured
    : import.meta.env.PROD
      ? 'https://kabque.onrender.com/api'
      : '/api';

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

function humanizeHttpError(status, fallback = 'Request failed') {
  if (status === 502 || status === 503 || status === 504) {
    return 'KabQue API is unavailable. Try again in a moment.';
  }
  if (status >= 500) {
    return 'Server error. Please refresh and try again.';
  }
  if (status === 404) {
    return 'Service endpoint not found. Please try again or refresh the page.';
  }
  return fallback;
}

function errorFromPayload(data, fallback = 'Request failed', status = 0) {
  if (status >= 500) {
    return humanizeHttpError(status, fallback);
  }
  if (data == null) return fallback;
  if (typeof data === 'string') {
    const text = data.trim();
    if (looksLikeHtml(text) || /NOT_FOUND/i.test(text) || /Code:\s*NOT_FOUND/i.test(text)) {
      return humanizeHttpError(status || 500, fallback);
    }
    return text || fallback;
  }

  const vercelCode = data?.error?.code || data?.code;
  if (vercelCode === 'NOT_FOUND' || data?.error === 'NOT_FOUND') {
    return 'Service endpoint not found. Please try again or refresh the page.';
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
    const detailText = String(detail);
    if (looksLikeHtml(detailText) || /NOT_FOUND/i.test(detailText) || /Server Error \(500\)/i.test(detailText)) {
      return humanizeHttpError(status || 500, fallback);
    }
    return detailText;
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
      if (parts.length) {
        const joined = parts.join(' ');
        if (looksLikeHtml(joined) || /NOT_FOUND/i.test(joined) || /Server Error \(500\)/i.test(joined)) {
          return humanizeHttpError(status || 500, fallback);
        }
        return joined;
      }
    } catch {
      return fallback;
    }
  }

  return fallback;
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
    throw new Error(
      'Cannot reach KabQue API. Make sure Django is running and VITE_API_URL points to the backend.'
    );
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
    const err = new Error(
      errorFromPayload(
        data,
        humanizeHttpError(res.status, 'Request failed'),
        res.status
      )
    );
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
      reject(new Error('Geolocation is not supported by this browser.'));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) =>
        resolve({
          latitude: pos.coords.latitude,
          longitude: pos.coords.longitude,
          accuracy: pos.coords.accuracy,
        }),
      (err) => reject(new Error(err.message || 'Unable to read GPS location.')),
      { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 }
    );
  });
}

// Prefer captureCampusLocation from geo/campusLocation.js for join-queue.
