/**
 * Campus GPS capture with basic anti-spoof checks (browser Geolocation limits apply).
 * Mock location apps can still cheat — these heuristics raise the bar cleanly.
 */

const MAX_ACCURACY_M = 80;
const SAMPLE_COUNT = 3;
const SAMPLE_GAP_MS = 850;
const MAX_SAMPLE_SPREAD_M = 50;
const MAX_FIX_AGE_MS = 8_000;

function toRad(deg) {
  return (deg * Math.PI) / 180;
}

/** Rough metres between two WGS84 points (Haversine). */
export function distanceMeters(a, b) {
  const R = 6371000;
  const dLat = toRad(b.latitude - a.latitude);
  const dLon = toRad(b.longitude - a.longitude);
  const lat1 = toRad(a.latitude);
  const lat2 = toRad(b.latitude);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(h)));
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function readOneFix(options) {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error('Geolocation is not supported on this device.'));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve(pos),
      (err) => {
        const map = {
          1: 'Location permission denied. Allow GPS for KabQue and try again.',
          2: 'GPS signal unavailable. Move outdoors or wait for a stronger fix.',
          3: 'GPS timed out. Move to open sky and try again.',
        };
        reject(new Error(map[err?.code] || err?.message || 'Unable to read GPS.'));
      },
      options
    );
  });
}

function assessFix(pos) {
  const { latitude, longitude, accuracy } = pos.coords;
  const age = Math.max(0, Date.now() - pos.timestamp);

  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
    return { ok: false, error: 'Invalid GPS coordinates received.' };
  }
  if (Math.abs(latitude) < 0.0001 && Math.abs(longitude) < 0.0001) {
    return { ok: false, error: 'Invalid GPS location. Turn off any fake-location apps.' };
  }
  if (!Number.isFinite(accuracy) || accuracy <= 0) {
    return {
      ok: false,
      error: 'GPS accuracy missing. Wait for a real fix, then try again.',
    };
  }
  if (accuracy > MAX_ACCURACY_M) {
    return {
      ok: false,
      error: `GPS accuracy is too weak (~${Math.round(accuracy)}m). Move outdoors and try again (need under ${MAX_ACCURACY_M}m).`,
    };
  }
  if (age > MAX_FIX_AGE_MS) {
    return {
      ok: false,
      error: 'GPS fix is stale. Wait a moment and join again with a fresh location.',
    };
  }

  return {
    ok: true,
    sample: {
      latitude,
      longitude,
      accuracy,
      altitude: Number.isFinite(pos.coords.altitude) ? pos.coords.altitude : null,
      altitudeAccuracy: Number.isFinite(pos.coords.altitudeAccuracy)
        ? pos.coords.altitudeAccuracy
        : null,
      speed: Number.isFinite(pos.coords.speed) ? pos.coords.speed : null,
      heading: Number.isFinite(pos.coords.heading) ? pos.coords.heading : null,
      captured_at: pos.timestamp,
      age_ms: age,
    },
  };
}

/**
 * Collect several fresh high-accuracy samples and return a verified payload for join-queue.
 * @param {{ onPhase?: (phase: string) => void }} [opts]
 */
export async function captureCampusLocation(opts = {}) {
  const { onPhase } = opts;
  onPhase?.('locating');

  const geoOpts = {
    enableHighAccuracy: true,
    timeout: 22_000,
    maximumAge: 0,
  };

  const samples = [];
  for (let i = 0; i < SAMPLE_COUNT; i += 1) {
    if (i > 0) await sleep(SAMPLE_GAP_MS);
    onPhase?.(i === 0 ? 'locating' : 'sampling');
    const pos = await readOneFix(geoOpts);
    const checked = assessFix(pos);
    if (!checked.ok) {
      throw new Error(checked.error);
    }
    samples.push(checked.sample);
  }

  // Consistency: spread between samples should be small for a standing student
  let maxSpread = 0;
  for (let i = 0; i < samples.length; i += 1) {
    for (let j = i + 1; j < samples.length; j += 1) {
      maxSpread = Math.max(maxSpread, distanceMeters(samples[i], samples[j]));
    }
  }
  if (maxSpread > MAX_SAMPLE_SPREAD_M) {
    throw new Error(
      'GPS jumped between readings. Stay still outdoors, turn off fake-location apps, and try again.'
    );
  }

  // Prefer the sample with best (lowest) accuracy
  const best = samples.reduce((a, b) => (a.accuracy <= b.accuracy ? a : b));

  onPhase?.('confirming');

  return {
    latitude: best.latitude,
    longitude: best.longitude,
    accuracy: best.accuracy,
    altitude: best.altitude,
    altitude_accuracy: best.altitudeAccuracy,
    speed: best.speed,
    heading: best.heading,
    captured_at: best.captured_at,
    sample_count: samples.length,
    sample_spread_m: Math.round(maxSpread * 10) / 10,
    samples: samples.map((s) => ({
      latitude: s.latitude,
      longitude: s.longitude,
      accuracy: s.accuracy,
      captured_at: s.captured_at,
    })),
  };
}
