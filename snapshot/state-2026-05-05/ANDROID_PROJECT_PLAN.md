# Android-приложение «X-Service» — план

## Спецификация от пользователя

> «Напиши программу X-Service, цвета — чёрный, бирюзовый, серебристый, серый, тёмно-серый. Программа сканирует сеть, одна кнопка — выявляет метод блокировки, генерируется конфигурация, подключение.»

## Стратегия: форк Hiddify-Next + ребренд + custom scanner

Hiddify-Next — это open-source Flutter-клиент с sing-box внутри. Поддерживает VLESS+Reality+XTLS, понимает Clash YAML и sing-box JSON, работает на Android/iOS/Windows/macOS/Linux. **GPL-3.0 лицензия** — форк разрешён.

Альтернатива (с нуля на Kotlin) = 3+ месяца. Форк = 2-3 недели.

## Объём работ

### 1. Форк и базовая сборка (1-2 дня)

```bash
git clone https://github.com/hiddify/hiddify-next.git x-service
cd x-service
git remote rm origin
git remote add origin https://github.com/Morfius66/x-service.git
flutter pub get
flutter build apk --release
```

Проверить что unmodified Hiddify-Next собирается и запускается.

### 2. Ребрендинг (1-2 дня)

| Что | Где | На что менять |
|-----|-----|---------------|
| Имя app | `android/app/src/main/AndroidManifest.xml` (`android:label`) | `X-Service` |
| Package | `android/app/build.gradle` (`applicationId`) | `pro.xservis.app` |
| Иконка | `android/app/src/main/res/mipmap-*/` | Чёрно-бирюзовая X |
| Splash | `assets/images/splash.png` | Чёрный + бирюзовый логотип |
| Главный цвет | `lib/core/theme/theme.dart` | `Color(0xFF00D4D4)` (бирюзовый) |
| Фон | там же | `Color(0xFF0A0A0A)` (чёрный) |
| Акценты | там же | `Color(0xFFC0C0C0)` (серебристый), `Color(0xFF606060)` (тёмно-серый), `Color(0xFF8C8C8C)` (серый) |
| Strings | `lib/l10n/app_ru.arb` | `Hiddify` → `X-Service` |
| Локализация | удалить все языки кроме `ru`, `en` | минимизирует размер APK |

Цвета в одном файле:
```dart
// lib/core/theme/colors.dart
class XSColors {
  static const black     = Color(0xFF0A0A0A);
  static const turquoise = Color(0xFF00D4D4);
  static const silver    = Color(0xFFC0C0C0);
  static const grey      = Color(0xFF8C8C8C);
  static const darkGrey  = Color(0xFF606060);
}
```

### 3. Network Scanner (5-7 дней) — главная новая фича

Новый экран `lib/features/scanner/scanner_page.dart`. Одна большая кнопка: **«Найти рабочий метод»**.

При нажатии запускается последовательность тестов:

#### Тест 1 — TCP-handshake к сервер:443 на разных SNI

```dart
Future<List<SniResult>> probeSnis(String server, List<String> snis) async {
  final results = <SniResult>[];
  for (final sni in snis) {
    final t0 = DateTime.now();
    try {
      final socket = await SecureSocket.connect(
        server, 443,
        host: sni, // SNI
        timeout: Duration(seconds: 5),
      );
      results.add(SniResult(sni: sni, latencyMs: DateTime.now().difference(t0).inMilliseconds, ok: true));
      await socket.close();
    } catch (e) {
      results.add(SniResult(sni: sni, ok: false, error: e.toString()));
    }
  }
  return results;
}
```

Тестируем с 10 разных SNI из whitelist. Каждый успешный = «этот SNI работает».

#### Тест 2 — TLS-fingerprint detection

Сравниваем latency `chrome` fingerprint vs `default openssl`:
- Если `chrome` работает а `default` нет → ISP режет VPN-fingerprints, нужен uTLS
- Если оба работают → DPI мягкий, обычного TLS хватит

(в Hiddify-Next sing-box ядро уже умеет разные fingerprints — просто прокидываем сравнение)

#### Тест 3 — Альтернативные порты

Проверяем подключение к `<server>:8443`, `<server>:2096`, `<server>:80`:
- Если 443 открыт — стандарт
- Если 443 режется но 8443 открыт — рекомендуем backup-inbound на 8443

#### Тест 4 — DNS-leak / DNS-blocking

Резолвим `youtube.com`, `instagram.com`, `whatsapp.com` через системный DNS vs через DoH:
- Разные ответы → ISP блокирует через DNS, нужен Encrypted DNS

#### Тест 5 — QUIC/UDP

Пробуем UDP-handshake к серверу:443:
- Не отвечает → UDP/443 режется (нормально для России), используем TCP
- Отвечает → можно QUIC (редкий случай)

### 4. Auto-Config generator (2-3 дня)

После scanner'а — алгоритм выбора:
1. Если есть рабочий SNI с low-latency → используем VLESS+Reality на 443 с этим SNI
2. Если все SNI на 443 высокая latency → используем XHTTP на 443
3. Если 443 целиком блокируется → используем backup на 8443
4. Если ни один не работает → показываем «требуется поддержка @xservis_support»

Вызываем backend `GET /api/sub/{sub_id}` с правильным User-Agent, получаем готовый конфиг, импортируем в sing-box ядро (уже встроено в Hiddify-Next).

### 5. Auto-Connect (1 день)

После скан-конфиг — автоматически жмём «Connect» в sing-box. У Hiddify-Next API уже есть, просто прокидываем.

### 6. UI/UX flow (2-3 дня)

```
┌──────────────────────────┐
│      X-Service           │ ← бирюзовая X на чёрном
│                          │
│   ╔════════════════╗     │
│   ║                ║     │
│   ║   ⚡ Scan      ║ ← одна большая кнопка, бирюзовая
│   ║                ║     │
│   ╚════════════════╝     │
│                          │
│   [статус подключения]   │ ← серый текст
└──────────────────────────┘
```

При сканировании:
```
┌──────────────────────────┐
│  Сканирую сеть…          │
│                          │
│  ✓ TCP/443 открыт        │
│  ✓ SNI vk.com работает   │
│  ⏳ Тестирую uTLS Chrome  │
│  ✗ UDP/443 заблокирован  │
│                          │
│  [прогресс-бар 60%]      │
└──────────────────────────┘
```

После:
```
┌──────────────────────────┐
│  Подключено              │ ← бирюзовый чек
│                          │
│  Метод: VLESS+Reality    │
│  SNI:  vk.com            │
│  Сервер: 89 мс           │
│                          │
│   [Disconnect]           │
└──────────────────────────┘
```

### 7. Сборка и подпись APK (1 день)

```bash
flutter build apk --release --flavor production
```

Подпись release-key (из 1Password / vault).

### 8. Раздача (1 день)

- Залить APK на `https://xservis.pro/download/x-service.apk`
- Добавить в Mini App кнопку «Скачать Android-приложение»
- Опционально — Google Play (но сложнее с VPN-приложением, могут забанить)

## Итого

**Сроки:** 14-21 день (Flutter dev + Android testing + APK signing).

**Зависимости:**
- Существующий backend (есть, работает)
- Подписка через `/api/sub/{sub_id}` (есть, работает)
- 3X-UI inbounds: Reality + XHTTP fallback (минимум 2 inbound)

**Что нужно от юзера:**
- Финальный логотип X-Service в SVG
- Подтверждение прав на форк Hiddify-Next (GPL-3.0 — нужно публиковать source code своего форка, либо договориться с авторами)
- Google Play developer account ($25), если планируется store-релиз

## Когда стартуем

После того как:
1. Phase 1 (VPS subscription patch) полностью оттестирован пользователями (минимум 1 неделя)
2. Подтверждено что 60-profile подписка стабильно работает у юзеров с разными ISP
3. Юзер открывает новую Devin-сессию специально под Android-проект

## Альтернатива (если нет ресурса)

- Просто рекомендовать **Hiddify-Next** или **V2RayTun** официально (без ребрендинга), интегрировать deep-link import из Mini App. Это уже работает в текущем patch'е — юзеры могут пользоваться готовыми клиентами.
- Свой Android-клиент — это про **бренд** и **дополнительный funnel**, но не про функциональность (она у Hiddify-Next/V2RayTun уже есть).
