import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import 'package:get/get.dart';
import 'package:town_pass/service/background_notification_service.dart';
import 'package:town_pass/service/construction_alert_service.dart';
import 'package:town_pass/util/web_message_handler/tp_web_message_handler.dart';

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
      await BackgroundNotificationService.startPeriodicCheck();
      await BackgroundNotificationService.executeImmediately();

      final alertService = Get.isRegistered<ConstructionAlertService>()
          ? Get.find<ConstructionAlertService>()
          : null;
      await alertService?.startRealtimeWatch();

      print('[WatchMessageHandler] Background detection started');
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
      await BackgroundNotificationService.stopPeriodicCheck();

      final alertService = Get.isRegistered<ConstructionAlertService>()
          ? Get.find<ConstructionAlertService>()
          : null;
      await alertService?.stopRealtimeWatch();

      print('[UnwatchMessageHandler] Background detection stopped');
      onReply?.call(replyWebMessage(data: true));
    } catch (e) {
      print('[UnwatchMessageHandler] Error: $e');
      onReply?.call(replyWebMessage(data: false));
    }
  }
}
