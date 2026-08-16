from geopy.distance import geodesic
from django.conf import settings

from .models import CampusSettings

# Join is rejected if reported accuracy is weaker than this (metres).
MAX_JOIN_ACCURACY_M = 500

# Production fence — Kikungiri Campus (never trust a leftover nationwide DB/env).
KABALE_KIKUNGIRI = (-1.272215, 29.988321)
DEFAULT_CAMPUS_RADIUS_M = 800
MAX_PRODUCTION_RADIUS_M = 2500
# If configured centre is farther than this from Kikungiri, force Kabale.
MAX_CENTRE_DRIFT_FROM_KABALE_M = 50_000


def resolve_campus_geofence() -> tuple[tuple[float, float], float, bool]:
    """
    Return ((lat, lon), radius_m, enforce).

    When nationwide testing is off, always enforce a Kabale-sized fence even if
    Render/Neon still hold old Uganda-wide coordinates.
    """
    # Keep DB row aligned with env (and clamp production values).
    campus = CampusSettings.get_solo()
    nationwide = bool(getattr(settings, "NATIONWIDE_GPS_TESTING", False))

    if nationwide:
        center = (float(campus.latitude), float(campus.longitude))
        radius = float(campus.radius_meters)
        enforce = bool(campus.gps_enforcement) and bool(
            getattr(settings, "GPS_ENFORCEMENT", True)
        )
        return center, radius, enforce

    lat = float(getattr(settings, "CAMPUS_LATITUDE", KABALE_KIKUNGIRI[0]))
    lon = float(getattr(settings, "CAMPUS_LONGITUDE", KABALE_KIKUNGIRI[1]))
    if geodesic(KABALE_KIKUNGIRI, (lat, lon)).meters > MAX_CENTRE_DRIFT_FROM_KABALE_M:
        lat, lon = KABALE_KIKUNGIRI

    radius = float(
        getattr(settings, "CAMPUS_RADIUS_METERS", DEFAULT_CAMPUS_RADIUS_M)
        or DEFAULT_CAMPUS_RADIUS_M
    )
    # Never allow a country-sized "campus" in production mode.
    radius = min(max(radius, 100.0), float(MAX_PRODUCTION_RADIUS_M))
    return (lat, lon), radius, True


def campus_center_and_radius():
    return resolve_campus_geofence()


def is_on_campus(latitude: float, longitude: float) -> tuple[bool, float, float]:
    """
    Return (allowed, distance_meters, radius_meters).
    """
    center, radius, enforce = resolve_campus_geofence()
    distance = geodesic(center, (float(latitude), float(longitude))).meters
    if not enforce:
        return True, distance, radius
    return distance <= radius, distance, radius


def validate_join_gps(
    latitude: float,
    longitude: float,
    *,
    accuracy: float | None = None,
    samples: list | None = None,
) -> tuple[float, float, float]:
    """
    Validate join location for campus + anti-spoof heuristics.

    Returns (distance_meters, radius_meters, accuracy_meters).
    Raises ValueError with a student-facing message on failure.
    """
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid GPS coordinates.") from exc

    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        raise ValueError("Invalid GPS coordinates.")

    if abs(lat) < 0.0001 and abs(lon) < 0.0001:
        raise ValueError(
            "Invalid GPS location detected. Turn off any fake-location apps and try again."
        )

    center, radius, enforce = resolve_campus_geofence()
    distance = geodesic(center, (lat, lon)).meters

    if not enforce:
        # Production path always sets enforce=True; this only applies to explicit QA.
        acc = float(accuracy) if accuracy is not None else 0.0
        return distance, radius, acc

    if accuracy is None:
        raise ValueError(
            "GPS accuracy was not reported. Use a device with location services enabled."
        )

    try:
        acc = float(accuracy)
    except (TypeError, ValueError) as exc:
        raise ValueError("GPS accuracy was not reported correctly.") from exc

    if acc <= 0:
        raise ValueError("GPS accuracy was not reported correctly.")

    if acc > MAX_JOIN_ACCURACY_M:
        raise ValueError(
            "GPS signal is too weak. Move outdoors on campus and try again."
        )

    if distance > radius:
        raise ValueError(
            "Join only from Kikungiri Campus. Move onto campus, then try again."
        )

    # Uncertainty ellipse: near the edge but fix is not confident enough.
    if distance + acc > radius:
        raise ValueError(
            "Almost there — wait for a clearer GPS fix on campus, then try again."
        )

    if samples and isinstance(samples, list) and len(samples) >= 2:
        points = []
        for item in samples[:6]:
            if not isinstance(item, dict):
                continue
            try:
                points.append((float(item["latitude"]), float(item["longitude"])))
            except (KeyError, TypeError, ValueError):
                continue
        max_spread = 0.0
        for i, p1 in enumerate(points):
            for p2 in points[i + 1 :]:
                max_spread = max(max_spread, geodesic(p1, p2).meters)
        if max_spread > 150:
            raise ValueError(
                "GPS jumped while checking. Stay still outdoors and try again."
            )

    return distance, radius, acc
