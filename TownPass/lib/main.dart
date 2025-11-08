import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:get/get.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'package:town_pass/gen/assets.gen.dart';
import 'package:town_pass/service/account_service.dart';
import 'package:town_pass/service/device_service.dart';
import 'package:town_pass/service/geo_locator_service.dart';
import 'package:town_pass/service/notification_service.dart';
import 'package:town_pass/service/package_service.dart';
import 'package:town_pass/service/shared_preferences_service.dart';
import 'package:town_pass/service/subscription_service.dart';
import 'package:town_pass/service/construction_alert_service.dart';
import 'package:town_pass/service/websocket_notification_service.dart';
import 'package:town_pass/service/background_notification_service.dart';
import 'package:town_pass/util/tp_colors.dart';
import 'package:town_pass/util/tp_route.dart';

const _transparentStatusBar = SystemUiOverlayStyle(
  statusBarColor: Colors.transparent,
);

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await dotenv.load(fileName: ".env");
  // FlutterNativeSplash.preserve(
  //   widgetsBinding: WidgetsFlutterBinding.ensureInitialized(),
  // );

  await BackgroundNotificationService.initialize();
  await initServices();

  SystemChrome.setSystemUIOverlayStyle(_transparentStatusBar);

  runApp(const MyApp());
}

Future<void> initServices() async {
  await Get.putAsync<AccountService>(() async => await AccountService().init());
  await Get.putAsync<DeviceService>(() async => await DeviceService().init());
  await Get.putAsync<PackageService>(() async => await PackageService().init());
  await Get.putAsync<SharedPreferencesService>(() async => await SharedPreferencesService().init());
  await Get.putAsync<GeoLocatorService>(() async => await GeoLocatorService().init());
  await Get.putAsync<NotificationService>(() async => await NotificationService().init());
  await Get.putAsync<ConstructionAlertService>(() async => await ConstructionAlertService().init());
  await Get.putAsync<WebSocketNotificationService>(() async => await WebSocketNotificationService().init());

  Get.put<SubscriptionService>(SubscriptionService());
  
  // 初始化後連接 WebSocket
  final wsService = Get.find<WebSocketNotificationService>();
  wsService.connect();
}

class MyApp extends StatefulWidget {
  const MyApp({super.key});

  @override
  State<MyApp> createState() => _MyAppState();
}

class _MyAppState extends State<MyApp> with WidgetsBindingObserver {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    super.didChangeAppLifecycleState(state);
    
    // 獲取 WebSocket 服務
    if (Get.isRegistered<WebSocketNotificationService>()) {
      final wsService = Get.find<WebSocketNotificationService>();
      
      switch (state) {
        case AppLifecycleState.resumed:
          // 應用恢復到前景，確保連接
          print('[MyApp] App resumed, checking WebSocket connection');
          if (!wsService.isConnected) {
            print('[MyApp] WebSocket not connected, reconnecting...');
            wsService.connect();
          }
          break;
        case AppLifecycleState.paused:
          // 應用進入背景，保持連接（不關閉）
          print('[MyApp] App paused, keeping WebSocket connection alive');
          break;
        case AppLifecycleState.inactive:
          // 應用處於非活動狀態
          print('[MyApp] App inactive');
          break;
        case AppLifecycleState.detached:
          // 應用即將終止
          print('[MyApp] App detached');
          break;
        case AppLifecycleState.hidden:
          // 應用隱藏（某些平台）
          print('[MyApp] App hidden');
          break;
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return GetMaterialApp(
      title: 'Town Pass',
      theme: ThemeData(
        useMaterial3: true,
        scaffoldBackgroundColor: TPColors.grayscale50,
        bottomNavigationBarTheme: const BottomNavigationBarThemeData(
          backgroundColor: TPColors.white,
        ),
        colorScheme: ColorScheme.fromSeed(seedColor: TPColors.primary500),
        appBarTheme: const AppBarTheme(
          centerTitle: true,
          elevation: 0.0,
          iconTheme: IconThemeData(size: 56),
          actionsIconTheme: IconThemeData(size: 56),
        ),
        actionIconTheme: ActionIconThemeData(
          backButtonIconBuilder: (_) => Semantics(
            excludeSemantics: true,
            child: Assets.svg.iconArrowLeft.svg(width: 24, height: 24),
          ),
        ),
      ),
      debugShowCheckedModeBanner: false,
      initialRoute: TPRoute.main,
      onInit: () {
        NotificationService.requestPermission();
      },
      getPages: TPRoute.page,
    );
  }
}
