import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import 'package:get/get.dart';
import '../../service/background_notification_service.dart';
import '../../service/construction_alert_service.dart';
import '../web_message_handler/tp_web_message_handler.dart';

/// 處理來自 WebView 的 watch 訊息（啟動背景監控）
class WatchMessageHandler extends TPWebMessageHandler {
  @override
  String get name => 'watch';

  @override
  Future<void> handle({
    required Object? message,
    required WebUri? sourceOrigin,
    required bool isMainFrame,
    required Function(WebMessage replyWebMessage)? onReply,
  }) async {
    print('[WatchMessageHandler] Received watch message');
    try {
      // 啟動 AlarmManager 週期檢查（15 分鐘）
      await BackgroundNotificationService.startPeriodicCheck();
      
      // 立即執行一次檢查
      await BackgroundNotificationService.executeImmediately();

      // 啟動即時 GPS 監控
      final alertService = Get.isRegistered<ConstructionAlertService>()
          ? Get.find<ConstructionAlertService>()
          : null;
      await alertService?.startRealtimeWatch();
      
      print('[WatchMessageHandler] AlarmManager started (15 min interval)');
      onReply?.call(replyWebMessage(data: true));
    } catch (e) {
      print('[WatchMessageHandler] Error: $e');
      onReply?.call(replyWebMessage(data: false));
    }
  }
}

/// 處理來自 WebView 的 unwatch 訊息（停止背景監控）
class UnwatchMessageHandler extends TPWebMessageHandler {
  @override
  String get name => 'unwatch';

  @override
  Future<void> handle({
    required Object? message,
    required WebUri? sourceOrigin,
    required bool isMainFrame,
    required Function(WebMessage replyWebMessage)? onReply,
  }) async {
    print('[UnwatchMessageHandler] Received unwatch message');
    try {
      // 停止 AlarmManager 週期檢查
      await BackgroundNotificationService.stopPeriodicCheck();

      final alertService = Get.isRegistered<ConstructionAlertService>()
          ? Get.find<ConstructionAlertService>()
          : null;
      await alertService?.stopRealtimeWatch();
      
      print('[UnwatchMessageHandler] AlarmManager stopped');
      onReply?.call(replyWebMessage(data: true));
    } catch (e) {
      print('[UnwatchMessageHandler] Error: $e');
      onReply?.call(replyWebMessage(data: false));
    }
  }
}
