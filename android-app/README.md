# K&C Android MVP

Первая Android-оболочка K&C на Jetpack Compose.

Уже есть:
- вкладки VPN / Чаты / Профиль;
- VPN / Proxy;
- Proxy: VK / MAX / AUTO;
- VPN — зелёный, Proxy — голубой;
- компактные TX/RX, RTT, DTLS, Internet, Conns, Reconnects, Uptime, Pool;
- подключение/отключение;
- тёмный минималистичный интерфейс.

Это UI/MVP. Реальный Android VPN/Proxy-движок через VpnService, WireGuard/TURN и интеграции VK/MAX подключаются следующим этапом.
