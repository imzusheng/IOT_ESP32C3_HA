# MQTT 订阅失败问题修复 - 最终总结

## 修复摘要

为解决设备在 MQTT 连接后立即出现订阅失败并反复重连的问题,进行以下修复:

1. 修复底层`umqtt_lock.py`中 SUBSCRIBE 报文构造:

   - 新增`pid`计数器,遵循 MQTT 协议的 Packet Identifier 规范
   - 正确计算并编码 SUBSCRIBE 的剩余长度
   - 规范化 SUBACK 解析流程
   - 统一 topic 为 bytes

2. 优化上层`_setup_mqtt_config_channel`订阅流程:
   - 增加防重入保护,避免重复订阅
   - 每个订阅之间加入`time.sleep_ms(50)`短延迟,避免连续阻塞对底层 socket 造成压力
   - 保持回调幂等设置

## 验证

- 通过`python build.py -c`编译验证成功,无语法错误
- 预计在实际设备上将避免`EBADF`与`UNKNOWN(-1)`错误,订阅成功率提升

## 改动文件列表

- `app/lib/umqtt_lock.py`
- `app/net/network_manager.py`

## 后续建议

- 如果仍有偶发现象,可将延迟微调至`80-120ms`
- 增加订阅失败的重试逻辑(带指数退避)
- 在`MqttController._restore_subscriptions`中引入小延迟可进一步增强稳定性
