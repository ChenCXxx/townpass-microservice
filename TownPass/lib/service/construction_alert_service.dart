import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_tts/flutter_tts.dart';
import 'package:geolocator/geolocator.dart';
import 'package:get/get.dart';
import 'package:http/http.dart' as http;
import 'package:town_pass/service/notification_service.dart';
import 'package:town_pass/util/geo_distance.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';

class ConstructionAlertService extends GetxService {
  static final String _baseUrl =
      dotenv.env['API_BASE'] ?? 'https://townpass.chencx.cc';
  static const Duration _refreshInterval = Duration(minutes: 10);
  static const Duration _dedupeWindow = Duration(minutes: 5);
  static const Duration _voiceCooldown = Duration(minutes: 2);
  static const double _alertRadiusKm = 0.3; // ~300m

  final FlutterTts _tts = FlutterTts();

  StreamSubscription<Position>? _positionSubscription;
  Timer? _refreshTimer;
  List<dynamic> _features = [];
  final Map<String, DateTime> _recentAnnouncements = {};
  final Map<String, DateTime> _voiceHistory = {};

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
    print('[ConstructionAlertService] Feature cache length: ${_features.length}');
    _refreshTimer?.cancel();
    _refreshTimer = Timer.periodic(_refreshInterval, (_) async {
      await _loadConstructionData();
      print('[ConstructionAlertService] Feature cache refreshed: ${_features.length}');
    });

    final locationSettings = _buildLocationSettings();

    _positionSubscription = Geolocator.getPositionStream(locationSettings: locationSettings).listen(
      _handlePositionUpdate,
      onError: (error) => print('[ConstructionAlertService] Position stream error: $error'),
      onDone: () => print('[ConstructionAlertService] Position stream closed'),
    );

    print('[ConstructionAlertService] Real-time monitoring started');
  }

  Future<void> stopRealtimeWatch() async {
    await _positionSubscription?.cancel();
    _positionSubscription = null;

    _refreshTimer?.cancel();
    _refreshTimer = null;

    _recentAnnouncements.clear();
    _voiceHistory.clear();
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

      final body = jsonDecode(utf8.decode(response.bodyBytes));
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
      print('[ConstructionAlertService] Position ignored: feature cache empty');
      return;
    }

    print('[ConstructionAlertService] Position update '
        '(${position.latitude}, ${position.longitude}) accuracy=${position.accuracy}');

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

      final distanceMeters = distanceKm * 1000;
      final props = feature['properties'] as Map<String, dynamic>? ?? {};
      final name = props['AP_NAME'] ??
          props['場地名稱'] ??
          props['ROAD'] ??
          props['ROAD_NAME'] ??
          '施工地點';

      // print('[ConstructionAlertService] → $name '
      //     '${distanceMeters.toStringAsFixed(1)}m');

      if (distanceKm > _alertRadiusKm) continue;

      final id = _featureId(props, lat, lon);
      if (!_shouldNotify(id)) {
        print('[ConstructionAlertService] Skip $name (dedupe window)');
        continue;
      }

      hits.add(
        _ConstructionHit(
          id: id,
          name: name.toString(),
          distanceMeters: distanceMeters,
        ),
      );
    }

    if (hits.isEmpty) {
      print('[ConstructionAlertService] No hits within ${_alertRadiusKm * 1000}m');
      return;
    }

    hits.sort((a, b) => a.distanceMeters.compareTo(b.distanceMeters));
    print('[ConstructionAlertService] Hits in range: ${hits.length}');
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

    print('[ConstructionAlertService] Notify: $content');

    await NotificationService.showNotification(
      title: '前方施工提醒',
      content: '$content，請注意行車安全',
    );

    final speakTargets = hits.where((hit) {
      final last = _voiceHistory[hit.id];
      return last == null || now.difference(last) > _voiceCooldown;
    }).toList();

    if (speakTargets.isEmpty) {
      print('[ConstructionAlertService] Skip TTS, all targets in cooldown');
      return;
    }

    final speakNames = speakTargets.map((hit) => hit.name).join('、');
    print('[ConstructionAlertService] TTS speak start for $speakNames');
    await _tts.stop();
    await _tts.speak('前方$speakNames有施工，請放慢速度注意安全');
    for (final hit in speakTargets) {
      _voiceHistory[hit.id] = now;
    }
    print('[ConstructionAlertService] TTS speak done');
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
