import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:get/get.dart';
import 'package:town_pass/bean/activity.dart';
import 'package:town_pass/gen/assets.gen.dart';
import 'package:town_pass/util/tp_app_bar.dart';
import 'package:town_pass/util/tp_bottom_sheet.dart';
import 'package:town_pass/util/tp_button.dart';
import 'package:town_pass/util/tp_colors.dart';
import 'package:town_pass/util/tp_duration.dart';
import 'package:town_pass/util/tp_line.dart';
import 'package:town_pass/util/tp_route.dart';
import 'package:town_pass/util/tp_text.dart';

class ActivityDetailView extends StatelessWidget {
  const ActivityDetailView({super.key});

  ActivityItem? get activity =>
      Get.arguments is ActivityItem ? Get.arguments as ActivityItem : null;

  @override
  Widget build(BuildContext context) {
    if (activity == null) {
      return Scaffold(
        backgroundColor: TPColors.white,
        appBar: const TPAppBar(title: '活動訊息'),
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const TPText('找不到活動內容', style: TPTextStyles.h3SemiBold),
              const SizedBox(height: 8),
              TPText(
                '請從活動列表重新開啟',
                style: TPTextStyles.bodyRegular,
                color: TPColors.grayscale500,
              ),
              const SizedBox(height: 16),
              TPButton.secondary(
                text: '返回',
                onPressed: Get.back,
              ),
            ],
          ),
        ),
      );
    }

    final item = activity!;

    return Scaffold(
      backgroundColor: TPColors.white,
      appBar: const TPAppBar(title: '活動訊息'),
      body: Column(
        children: [
          CachedNetworkImage(imageUrl: item.imageUrl),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 8.0),
            child: TPText(
              item.title,
              style: TPTextStyles.h3SemiBold,
              color: TPColors.primary500,
            ),
          ),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16.0),
              child: Column(
                children: [
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 6),
                    child: _ActivityDurationWidget(
                      duration: TPDuration(
                        start: item.startDateTime,
                        end: item.endDateTime,
                      ),
                    ),
                  ),
                  const TPLine.horizontal(),
                  const SizedBox(height: 16),
                  Expanded(
                    child: SingleChildScrollView(
                      padding: const EdgeInsets.only(bottom: 16.0),
                      child: TPText(
                        item.content,
                        style: TPTextStyles.h3Regular,
                        color: TPColors.grayscale800,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
      bottomNavigationBar: switch (item.webUrl) {
        null => null,
        String() => TPBottomSheet(
            child: Column(
              children: [
                TPButton.primary(
                  text: '網址連結',
                  onPressed: () async => await TPRoute.openUri(
                    uri: item.webUrl ?? '',
                  ),
                ),
              ],
            ),
          ),
      },
    );
  }
}

class _ActivityDurationWidget extends StatelessWidget {
  final TPDuration duration;

  const _ActivityDurationWidget({
    required this.duration,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Assets.svg.iconCalender.svg(width: 24, height: 24),
        const SizedBox(width: 16),
        TPText(
          duration.format(),
          style: TPTextStyles.h3Regular,
          color: TPColors.grayscale800,
        ),
      ],
    );
  }
}
