import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_tts/flutter_tts.dart';
import 'package:geolocator/geolocator.dart';
import 'package:get/get.dart';
import 'package:http/http.dart' as http;
import 'package:town_pass/service/notification_service.dart';
import 'package:town_pass/util/geo_distance.dart';

class ConstructionAlertService extends GetxService {
  static const String _baseUrl = 'https://townpass.chencx.cc';
  static const Duration _refreshInterval = Duration(minutes: 10);
  static const Duration _dedupeWindow = Duration(minutes: 5);
  static const Duration _voiceCooldown = Duration(minutes: 2);
  static const double _alertRadiusKm = 0.3; // ~300m

  final FlutterTts _tts = FlutterTts();

  StreamSubscription<Position>? _positionSubscription;
  Timer? _refreshTimer;
  List<dynamic> _features = [];
  DateTime? _lastSpokenAt;
  final Map<String, DateTime> _recentAnnouncements = {};

  bool get isRunning => _positionSubscription != null;

  Future<ConstructionAlertService> init() async {
    await _configureTts();
    return this;
  }

  Future<void> startRealtimeWatch() async {
    if (isRunning) {
      print('[ConstructionAlertService] Already running');
      return;
    }

    try {
      await _ensurePermissions();
    } catch (e) {
      print('[ConstructionAlertService] Permission issue: $e');
      rethrow;
    }

    await _loadConstructionData();
    _refreshTimer?.cancel();
    _refreshTimer = Timer.periodic(_refreshInterval, (_) => _loadConstructionData());

    final locationSettings = _buildLocationSettings();

    _positionSubscription = Geolocator.getPositionStream(locationSettings: locationSettings).listen(
      _handlePositionUpdate,
      onError: (error) => print('[ConstructionAlertService] Position stream error: $error'),
    );

    print('[ConstructionAlertService] Real-time monitoring started');
  }

  Future<void> stopRealtimeWatch() async {
    await _positionSubscription?.cancel();
    _positionSubscription = null;

    _refreshTimer?.cancel();
    _refreshTimer = null;

    _recentAnnouncements.clear();
    _lastSpokenAt = null;
    await _tts.stop();
    print('[ConstructionAlertService] Real-time monitoring stopped');
  }

  Future<void> _configureTts() async {
    await _tts.setLanguage('zh-TW');
    await _tts.setSpeechRate(0.45);
    await _tts.awaitSpeakCompletion(true);
  }

  Future<void> _ensurePermissions() async {
    final serviceEnabled = await Geolocator.isLocationServiceEnabled();
    if (!serviceEnabled) {
      throw '定位服務未啟用';
    }

    LocationPermission permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }

    if (permission == LocationPermission.deniedForever) {
      throw '定位權限被永久拒絕，請至設定頁開啟';
    }

    final serviceStatus = await Geolocator.isLocationServiceEnabled();
    if (!serviceStatus) {
      throw '定位服務未啟用';
    }
  }

  Future<void> _loadConstructionData() async {
    try {
      final response = await http
          .get(Uri.parse('$_baseUrl/api/construction/geojson'))
          .timeout(const Duration(seconds: 15));

      if (response.statusCode != 200) {
        print('[ConstructionAlertService] Failed to fetch geojson: ${response.statusCode}');
        return;
      }

      final body = jsonDecode(response.body);
      final features = body['features'];
      if (features is List) {
        _features = features;
        print('[ConstructionAlertService] Loaded ${features.length} features');
      }
    } catch (e) {
      print('[ConstructionAlertService] Error loading geojson: $e');
    }
  }

  void _handlePositionUpdate(Position position) {
    if (_features.isEmpty) {
      return;
    }

    final hits = <_ConstructionHit>[];
    for (final feature in _features) {
      if (feature is! Map<String, dynamic>) continue;

      final geometry = feature['geometry'] as Map<String, dynamic>? ?? {};
      final coords = geometry['coordinates'];
      if (coords is! List || coords.length < 2) continue;

      final lon = (coords[0] as num?)?.toDouble();
      final lat = (coords[1] as num?)?.toDouble();
      if (lon == null || lat == null) continue;

      final distanceKm = GeoDistance.haversineKm(
        position.latitude,
        position.longitude,
        lat,
        lon,
      );

      if (distanceKm > _alertRadiusKm) continue;

      final props = feature['properties'] as Map<String, dynamic>? ?? {};
      final id = _featureId(props, lat, lon);
      if (!_shouldNotify(id)) continue;

      final name = props['AP_NAME'] ??
          props['場地名稱'] ??
          props['ROAD'] ??
          props['ROAD_NAME'] ??
          '施工地點';

      hits.add(
        _ConstructionHit(
          id: id,
          name: name.toString(),
          distanceMeters: distanceKm * 1000,
        ),
      );
    }

    if (hits.isEmpty) return;

    hits.sort((a, b) => a.distanceMeters.compareTo(b.distanceMeters));
    _sendAlerts(hits);
  }

  bool _shouldNotify(String featureId) {
    final last = _recentAnnouncements[featureId];
    if (last == null) {
      return true;
    }
    if (DateTime.now().difference(last) > _dedupeWindow) {
      return true;
    }
    return false;
  }

  Future<void> _sendAlerts(List<_ConstructionHit> hits) async {
    final now = DateTime.now();
    for (final hit in hits) {
      _recentAnnouncements[hit.id] = now;
    }

    final topNames = hits.take(3).map((hit) => hit.name).join('、');
    final content = hits.length == 1
        ? '${hits.first.name} 約 ${(hits.first.distanceMeters).toStringAsFixed(0)} 公尺'
        : '$topNames 等 ${hits.length} 處';

    await NotificationService.showNotification(
      title: '前方施工提醒',
      content: '$content，請注意行車安全',
    );

    if (_lastSpokenAt == null || now.difference(_lastSpokenAt!) > _voiceCooldown) {
      await _tts.stop();
      await _tts.speak('前方$topNames有施工，請放慢速度注意安全');
      _lastSpokenAt = now;
    }
  }

  LocationSettings _buildLocationSettings() {
    if (Platform.isAndroid) {
      return AndroidSettings(
        accuracy: LocationAccuracy.best,
        distanceFilter: 15,
        foregroundNotificationConfig: const ForegroundNotificationConfig(
          enableWakeLock: true,
          notificationTitle: 'TownPass 背景定位',
          notificationText: '偵測附近施工中，請保持 App 在背景運作',
          notificationChannelName: 'TownPass Background',
          setOngoing: true,
          notificationIcon: AndroidResource(
            name: 'ic_launcher',
            defType: 'mipmap',
          ),
        ),
      );
    }

    if (Platform.isIOS) {
      return AppleSettings(
        accuracy: LocationAccuracy.best,
        activityType: ActivityType.otherNavigation,
        pauseLocationUpdatesAutomatically: true,
        showBackgroundLocationIndicator: true,
      );
    }

    return const LocationSettings(
      accuracy: LocationAccuracy.best,
      distanceFilter: 15,
    );
  }

  String _featureId(Map<String, dynamic> props, double lat, double lon) {
    return props['AC_NO']?.toString() ??
        props['AP_NO']?.toString() ??
        '${lat.toStringAsFixed(5)}_${lon.toStringAsFixed(5)}';
  }
}

class _ConstructionHit {
  _ConstructionHit({
    required this.id,
    required this.name,
    required this.distanceMeters,
  });

  final String id;
  final String name;
  final double distanceMeters;
}
