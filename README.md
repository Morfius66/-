# Android-приложение Xservis

Нативное Android-приложение для подключения к Xservis через Hiddify, V2RayTun или Clash.

## Возможности

- одна кнопка `Подключиться`;
- сетевые проверки с классификацией блокировки;
- запрос `https://xservis.pro/api/connect/auto-config`;
- отправка технической телеметрии в `https://xservis.pro/api/telemetry/network-scan`;
- резервный переход на ссылку подписки;
- импорт профиля через Android-ссылки с именем профиля `Xservis`.

## Сборка

```bash
export ANDROID_HOME=/path/to/android-sdk
./gradlew :app:assembleDebug
```

Отладочный APK будет в `app/build/outputs/apk/debug/app-debug.apk`.
