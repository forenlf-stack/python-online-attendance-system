"""Circular geofence: spherical Haversine distance, in meters."""
import math

EARTH_RADIUS_METERS = 6371000  # Mean spherical Earth radius for this course project.


def finite_number(value, label, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError(f"{label}必须是有效数值")
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        raise ValueError(f"{label}必须是有效数值") from None
    if not math.isfinite(number):
        raise ValueError(f"{label}必须是有限数值")
    if minimum is not None and number < minimum:
        raise ValueError(f"{label}不能小于 {minimum}")
    if maximum is not None and number > maximum:
        raise ValueError(f"{label}不能大于 {maximum}")
    return number


def coordinates(latitude, longitude):
    return (finite_number(latitude, "纬度", -90, 90),
            finite_number(longitude, "经度", -180, 180))


def calculate_distance(lat1, lon1, lat2, lon2):
    lat1, lon1 = coordinates(lat1, lon1)
    lat2, lon2 = coordinates(lat2, lon2)
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (math.sin(delta_phi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2)
    return 2 * EARTH_RADIUS_METERS * math.asin(math.sqrt(max(0.0, min(1.0, a))))
