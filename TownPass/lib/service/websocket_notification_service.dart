import 'dart:async';
import 'dart:convert';
import 'package:get/get.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'package:town_pass/service/account_service.dart';
import 'package:town_pass/service/notification_service.dart';

class WebSocketNotificationService extends GetxService {
  static final String _baseUrl =
      dotenv.env['API_BASE'] ?? 'https://townpass.chencx.cc';
  
  WebSocketChannel? _channel;
  StreamSubscription? _subscription;
  Timer? _heartbeatTimer;
  bool _isConnected = false;
  bool _isConnecting = false;
  
  bool get isConnected => _isConnected;
  
  Future<WebSocketNotificationService> init() async {
    return this;
  }
  
  /// 連接到 WebSocket 伺服器
  Future<void> connect() async {
    if (_isConnecting || _isConnected) {
      print('[WebSocketNotificationService] Already connected or connecting');
      return;
    }
    
    final account = Get.find<AccountService>().account;
    if (account?.id == null) {
      print('[WebSocketNotificationService] No account ID, cannot connect');
      return;
    }
    
    final externalId = account!.id!;
    _isConnecting = true;
    
    try {
      // 構建 WebSocket URL
      final wsUrl = _baseUrl.replaceFirst('https://', 'wss://').replaceFirst('http://', 'ws://');
      final uri = Uri.parse('$wsUrl/ws/notifications?external_id=$externalId');
      
      print('[WebSocketNotificationService] Connecting to $uri');
      
      _channel = WebSocketChannel.connect(uri);
      _isConnected = true;
      _isConnecting = false;
      
      print('[WebSocketNotificationService] Connected successfully');
      
      // 開始監聽訊息
      _subscription = _channel!.stream.listen(
        _handleMessage,
        onError: _handleError,
        onDone: _handleDisconnect,
        cancelOnError: false,
      );
      
      // 啟動心跳定時器（每30秒發送一次ping）
      _heartbeatTimer = Timer.periodic(const Duration(seconds: 30), (_) {
        _sendPing();
      });
      
    } catch (e) {
      _isConnecting = false;
      _isConnected = false;
      print('[WebSocketNotificationService] Connection failed: $e');
      
      // 5秒後重試
      Future.delayed(const Duration(seconds: 5), () {
        if (!_isConnected && !_isConnecting) {
          connect();
        }
      });
    }
  }
  
  /// 斷開連接
  Future<void> disconnect() async {
    print('[WebSocketNotificationService] Disconnecting...');
    
    _heartbeatTimer?.cancel();
    _heartbeatTimer = null;
    
    await _subscription?.cancel();
    _subscription = null;
    
    await _channel?.sink.close();
    _channel = null;
    
    _isConnected = false;
    _isConnecting = false;
    
    print('[WebSocketNotificationService] Disconnected');
  }
  
  /// 處理接收到的訊息
  void _handleMessage(dynamic message) {
    try {
      final data = jsonDecode(message as String);
      final type = data['type'] as String?;
      
      print('[WebSocketNotificationService] Received message: $type');
      
      if (type == 'connected') {
        print('[WebSocketNotificationService] Connection confirmed: ${data['message']}');
      } else if (type == 'construction_alert') {
        _handleConstructionAlert(data);
      } else if (type == 'pong') {
        // 心跳響應，無需處理
      } else {
        print('[WebSocketNotificationService] Unknown message type: $type');
      }
    } catch (e) {
      print('[WebSocketNotificationService] Error parsing message: $e');
    }
  }
  
  /// 處理施工警報
  void _handleConstructionAlert(Map<String, dynamic> data) {
    final alerts = data['alerts'] as List<dynamic>?;
    if (alerts == null || alerts.isEmpty) {
      return;
    }
    
    print('[WebSocketNotificationService] Received ${alerts.length} construction alerts');
    
    // 構建通知內容
    final alertMessages = <String>[];
    for (final alert in alerts) {
      final favoriteName = alert['favorite_name'] as String? ?? '收藏地點';
      final constructionName = alert['construction_name'] as String? ?? '施工地點';
      final distance = alert['distance_meters'] as int? ?? 0;
      final road = alert['construction_road'] as String?;
      
      String message = '$favoriteName 附近有施工：$constructionName';
      if (road != null && road.isNotEmpty) {
        message += '（$road）';
      }
      if (distance > 0) {
        message += '，距離約 ${distance} 公尺';
      }
      
      alertMessages.add(message);
    }
    
    // 發送通知
    final content = alertMessages.length == 1
        ? alertMessages.first
        : '${alertMessages.take(3).join('；')}${alertMessages.length > 3 ? '等 ${alertMessages.length} 處施工' : ''}';
    
    NotificationService.showNotification(
      title: '收藏地點施工提醒',
      content: '$content，請注意行車安全',
    );
    
    print('[WebSocketNotificationService] Notification sent: $content');
  }
  
  /// 處理錯誤
  void _handleError(dynamic error) {
    print('[WebSocketNotificationService] Error: $error');
    _isConnected = false;
    
    // 嘗試重連
    Future.delayed(const Duration(seconds: 5), () {
      if (!_isConnected && !_isConnecting) {
        connect();
      }
    });
  }
  
  /// 處理斷開連接
  void _handleDisconnect() {
    print('[WebSocketNotificationService] Connection closed');
    _isConnected = false;
    
    // 嘗試重連
    Future.delayed(const Duration(seconds: 5), () {
      if (!_isConnected && !_isConnecting) {
        connect();
      }
    });
  }
  
  /// 發送心跳（ping）
  void _sendPing() {
    if (_channel != null && _isConnected) {
      try {
        _channel!.sink.add(jsonEncode({'type': 'ping'}));
      } catch (e) {
        print('[WebSocketNotificationService] Failed to send ping: $e');
      }
    }
  }
  
  @override
  void onClose() {
    disconnect();
    super.onClose();
  }
}

