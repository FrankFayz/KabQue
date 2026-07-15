from geopy.distance import geodesic
from django.conf import settings

from .models import CampusSettings

# Join is rejected if reported accuracy is weaker than this (metres).
MAX_JOIN_ACCURACY_M = 80


def campus_center_and_radius():
    CampusSettings.ensure_lifetime_columns()
    campus = CampusSettings.objects.first()
    if campus:
        center = (float(campus.latitude), float(campus.longitude))
        radius = float(campus.radius_meters)
        enforce = bool(campus.gps_enforcement)
    else:
        center = (settings.CAMPUS_LATITUDE, settings.CAMPUS_LONGITUDE)
        radius = float(settings.CAMPUS_RADIUS_METERS)
        enforce = bool(settings.GPS_ENFORCEMENT)
    return center, radius, enforce


def is_on_campus(latitude: float, longitude: float) -> tuple[bool, float, float]:
    """
    Return (allowed, distance_meters, radius_meters).
    Uses CampusSettings if present, else env defaults.
    """
    center, radius, enforce = campus_center_and_radius()
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

    # Null Island / empty fix
    if abs(lat) < 0.0001 and abs(lon) < 0.0001:
        raise ValueError(
            "Invalid GPS location detected. Turn off any fake-location apps and try again."
        )

    center, radius, enforce = campus_center_and_radius()
    distance = geodesic(center, (lat, lon)).meters

    if not enforce:
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
            f"GPS accuracy is too weak (~{int(acc)}m). Move outdoors and try again "
            f"(need under {MAX_JOIN_ACCURACY_M}m)."
        )

    # Uncertainty ellipse: if the fix could still be outside campus, reject
    if distance + acc > radius:
        raise ValueError(
            "Your location is not confidently inside the campus zone. "
            f"Move closer to campus and wait for a stronger GPS fix "
            f"(~{int(distance)}m from centre, accuracy ±{int(acc)}m, "
            f"allowed {int(radius)}m)."
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
        if max_spread > 55:
            raise ValueError(
                "GPS readings jumped too far between samples. Stay still outdoors, "
                "turn off fake-location apps, and try again."
            )

    if distance > radius:
        raise ValueError(
            "You must be on Kikungiri Campus to join the queue. "
            f"Turn on GPS and try again. "
            f"(About {int(distance)}m outside the allowed area; "
            f"allowed radius: {int(radius)}m.)"
        )

    return distance, radius, acc
