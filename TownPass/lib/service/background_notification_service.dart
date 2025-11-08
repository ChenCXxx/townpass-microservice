import 'dart:async';
import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:workmanager/workmanager.dart';
import 'notification_service.dart';

/// 背景任務的唯一名稱
const String _taskName = 'checkConstructionNearFavorites';

/// WorkManager 背景任務回調函式（必須是頂層函式或靜態方法）
@pragma('vm:entry-point')
void backgroundTaskDispatcher() {
  Workmanager().executeTask((task, inputData) async {
    try {
      await BackgroundNotificationService._checkAndNotify();
      return Future.value(true);
    } catch (e) {
      print('[BackgroundTask] Error: $e');
      return Future.value(false);
    }
  });
}

class BackgroundNotificationService {
  /// 初始化 WorkManager（僅在 Android 上有效）
  static Future<void> initialize() async {
    await Workmanager().initialize(
      backgroundTaskDispatcher,
      isInDebugMode: false, // 設為 true 可在開發時看到更多日誌
    );
  }

  /// 啟動週期性背景任務（每 5 分鐘）
  static Future<void> startPeriodicCheck() async {
    await Workmanager().registerPeriodicTask(
      _taskName,
      _taskName,
      frequency: const Duration(minutes: 15), // Android 最小週期為 15 分鐘，測試可用一次性任務
      constraints: Constraints(
        networkType: NetworkType.connected, // 需要網路才執行
      ),
      existingWorkPolicy: ExistingWorkPolicy.replace,
    );
    print('[BackgroundNotificationService] Periodic task registered');
  }

  /// 停止週期性背景任務
  static Future<void> stopPeriodicCheck() async {
    await Workmanager().cancelByUniqueName(_taskName);
    print('[BackgroundNotificationService] Periodic task cancelled');
  }

  /// 背景任務核心邏輯：檢查有啟用通知的收藏，並發送施工警報
  static Future<void> _checkAndNotify() async {
    print('[BackgroundTask] Starting check...');

    // 1. 讀取收藏與通知設定
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

    // 2. 取得目前位置（可選，若需要基於使用者目前位置的邏輯）
    // Position? currentPosition;
    // try {
    //   currentPosition = await Geolocator.getCurrentPosition(
    //     desiredAccuracy: LocationAccuracy.medium,
    //   ).timeout(const Duration(seconds: 10));
    // } catch (e) {
    //   print('[BackgroundTask] Failed to get location: $e');
    // }

    // 3. 逐一檢查每個有啟用通知的收藏
    for (final fav in favorites) {
      final placeId = fav['id'];
      if (placeId == null) continue;

      // 只處理有啟用通知的收藏
      final enabled = notifications[placeId] == true;
      if (!enabled) continue;

      final recommendations = fav['recommendations'] ?? [];
      if (recommendations is! List) continue;

      // 計算施工地點數量
      int constructionCount = 0;
      for (final rec in recommendations) {
        if (rec is Map<String, dynamic>) {
          final dsid = rec['dsid'];
          final props = rec['props'];
          if (dsid == 'construction' ||
              (props is Map && (props['AP_NAME'] != null || props['PURP'] != null))) {
            constructionCount++;
          }
        }
      }

      if (constructionCount > 0) {
        final placeName = fav['name'] ?? '收藏地點';
        await NotificationService.showNotification(
          title: '$placeName 附近施工資訊',
          content: '此收藏 1 公里內有 $constructionCount 個施工地點',
        );
        print('[BackgroundTask] Notification sent for $placeName (construction: $constructionCount)');
      }
    }

    print('[BackgroundTask] Check completed');
  }

  /// 供測試用：立即執行一次背景檢查（不需等 15 分鐘）
  static Future<void> executeImmediately() async {
    await Workmanager().registerOneOffTask(
      'checkConstructionNow',
      _taskName,
      constraints: Constraints(
        networkType: NetworkType.connected,
      ),
      existingWorkPolicy: ExistingWorkPolicy.replace,
    );
    print('[BackgroundNotificationService] One-off task registered');
  }
}
