import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import '../../service/background_notification_service.dart';
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
      // 啟動週期性背景任務
      await BackgroundNotificationService.startPeriodicCheck();
      
      // 測試用：立即執行一次
      await BackgroundNotificationService.executeImmediately();
      
      print('[WatchMessageHandler] Background notification service started');
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
      // 停止週期性背景任務
      await BackgroundNotificationService.stopPeriodicCheck();
      
      print('[UnwatchMessageHandler] Background notification service stopped');
      onReply?.call(replyWebMessage(data: true));
    } catch (e) {
      print('[UnwatchMessageHandler] Error: $e');
      onReply?.call(replyWebMessage(data: false));
    }
  }
}
