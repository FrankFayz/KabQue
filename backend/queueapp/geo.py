from geopy.distance import geodesic
from django.conf import settings

from .models import CampusSettings


def is_on_campus(latitude: float, longitude: float) -> tuple[bool, float, float]:
    """
    Return (allowed, distance_meters, radius_meters).
    Uses CampusSettings if present, else env defaults.
    """
    campus = CampusSettings.objects.first()
    if campus:
        center = (float(campus.latitude), float(campus.longitude))
        radius = float(campus.radius_meters)
        enforce = campus.gps_enforcement
    else:
        center = (settings.CAMPUS_LATITUDE, settings.CAMPUS_LONGITUDE)
        radius = settings.CAMPUS_RADIUS_METERS
        enforce = settings.GPS_ENFORCEMENT

    distance = geodesic(center, (float(latitude), float(longitude))).meters
    if not enforce:
        return True, distance, radius
    return distance <= radius, distance, radius
