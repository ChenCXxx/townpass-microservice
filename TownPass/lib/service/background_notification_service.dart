import 'dart:async';
import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:android_alarm_manager_plus/android_alarm_manager_plus.dart';
import 'package:http/http.dart' as http;
import 'package:town_pass/util/geo_distance.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'notification_service.dart';

/// 背景通知服務（使用 Android AlarmManager 實現週期檢查）
/// 可在 App 關閉時持續運作
class BackgroundNotificationService {
  static const int _alarmId = 0;
  static final String _baseUrl =
      dotenv.env['API_BASE'] ?? 'https://townpass.chencx.cc';

  /// 初始化服務
  static Future<void> initialize() async {
    await AndroidAlarmManager.initialize();
    print('[BackgroundNotificationService] AlarmManager initialized');
  }

  /// 啟動週期性檢查（15 分鐘一次）
  static Future<void> startPeriodicCheck() async {
    print('[BackgroundNotificationService] Starting periodic check (15 minutes)');
    
    // 取消舊的鬧鐘
    await AndroidAlarmManager.cancel(_alarmId);
    
    // 設定新的週期鬧鐘：15 分鐘 = 15 * 60 * 1000 ms
    final success = await AndroidAlarmManager.periodic(
      const Duration(minutes: 15),
      _alarmId,
      _checkAndNotifyCallback,
      exact: true,
      wakeup: true,
      rescheduleOnReboot: true,
    );
    
    if (success) {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setBool('background_notification_enabled', true);
      print('[BackgroundNotificationService] Periodic alarm set successfully');
    } else {
      print('[BackgroundNotificationService] Failed to set periodic alarm');
    }
  }

  /// 停止週期性檢查
  static Future<void> stopPeriodicCheck() async {
    print('[BackgroundNotificationService] Stopping periodic check');
    await AndroidAlarmManager.cancel(_alarmId);
    
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('background_notification_enabled', false);
  }

  /// 立即執行一次檢查（供測試或前景呼叫）
  static Future<void> executeImmediately() async {
    print('[BackgroundNotificationService] Execute check immediately');
    await _checkAndNotify();
  }

  /// AlarmManager 回調函數（必須是頂層函數或靜態方法）
  @pragma('vm:entry-point')
  static Future<void> _checkAndNotifyCallback() async {
    print('[AlarmCallback] Triggered at ${DateTime.now()}');
    await _checkAndNotify();
  }

  /// 檢查邏輯：讀取收藏與通知設定，查詢 API，發送施工警報
  static Future<void> _checkAndNotify() async {
    print('[BackgroundTask] Starting check...');

    final prefs = await SharedPreferences.getInstance();
    final favoritesJson = prefs.getString('mapFavorites') ?? '[]';
    final notificationsJson = prefs.getString('placeNotifications') ?? '{}';

    List<dynamic> favorites = [];
    Map<String, dynamic> notifications = {};

    try {
      favorites = jsonDecode(favoritesJson);
    } catch (e) {
      print('[BackgroundTask] Failed to decode favorites: $e');
      return;
    }

    try {
      notifications = jsonDecode(notificationsJson);
    } catch (e) {
      print('[BackgroundTask] Failed to decode notifications: $e');
    }

    if (favorites.isEmpty) {
      print('[BackgroundTask] No favorites found');
      return;
    }

    // 檢查每個有啟用通知的收藏
    for (final fav in favorites) {
      final placeId = fav['id'];
      if (placeId == null) continue;

      final enabled = notifications[placeId] == true;
      if (!enabled) {
        print('[BackgroundTask] Notifications disabled for $placeId');
        continue;
      }

      final placeName = fav['name'] ?? '收藏地點';
      final lng = fav['lng'];
      final lat = fav['lat'];
      
      if (lng == null || lat == null) {
        print('[BackgroundTask] Missing coordinates for $placeName');
        continue;
      }

      // 從 API 查詢附近施工資訊
      try {
        final constructionCount = await _fetchNearbyConstructions(lng, lat);
        
        if (constructionCount > 0) {
          await NotificationService.showNotification(
            title: '$placeName 附近施工資訊',
            content: '此收藏 1 公里內有 $constructionCount 個施工地點',
          );
          print('[BackgroundTask] Notification sent for $placeName (construction: $constructionCount)');
        } else {
          print('[BackgroundTask] No constructions near $placeName');
        }
      } catch (e) {
        print('[BackgroundTask] Error checking $placeName: $e');
      }
    }

    print('[BackgroundTask] Check completed');
  }

  /// 查詢附近施工資訊
  static Future<int> _fetchNearbyConstructions(double lng, double lat) async {
    try {
      final url = Uri.parse('$_baseUrl/api/construction/geojson');
      final response = await http.get(url).timeout(const Duration(seconds: 10));
      
      if (response.statusCode != 200) {
        print('[BackgroundTask] API error: ${response.statusCode}');
        return 0;
      }

      final data = jsonDecode(utf8.decode(response.bodyBytes));
      final features = data['features'] as List? ?? [];
      
      int count = 0;
      for (final feature in features) {
        if (feature is! Map<String, dynamic>) continue;
        
        final geometry = feature['geometry'];
        if (geometry == null || geometry['coordinates'] == null) continue;
        
        final coords = geometry['coordinates'];
        if (coords is! List || coords.length < 2) continue;
        
        final conLng = coords[0] as num?;
        final conLat = coords[1] as num?;
        if (conLng == null || conLat == null) continue;
        
        // 計算距離（簡單的經緯度距離）
        final distance = GeoDistance.haversineKm(
          lat,
          lng,
          conLat.toDouble(),
          conLng.toDouble(),
        );
        if (distance <= 1.0) {
          count++;
        }
      }
      
      return count;
    } catch (e) {
      print('[BackgroundTask] Failed to fetch constructions: $e');
      return 0;
    }
  }

}
