import 'dart:math' show asin, cos, sin, sqrt;

/// Helper for calculating approximate distances between two lat/lng points.
class GeoDistance {
  static const double _earthRadiusKm = 6371.0;

  static double haversineKm(
    double lat1,
    double lon1,
    double lat2,
    double lon2,
  ) {
    final dLat = _toRadians(lat2 - lat1);
    final dLon = _toRadians(lon2 - lon1);
    final rLat1 = _toRadians(lat1);
    final rLat2 = _toRadians(lat2);

    final a = sin(dLat / 2) * sin(dLat / 2) +
        cos(rLat1) * cos(rLat2) * sin(dLon / 2) * sin(dLon / 2);

    final c = 2 * asin(sqrt(a));
    return _earthRadiusKm * c;
  }

  static double _toRadians(double degrees) =>
      degrees * 3.141592653589793 / 180.0;
}
