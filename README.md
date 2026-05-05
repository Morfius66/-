# Xservis Android

Native Android приложение для подключения к Xservis через Hiddify, V2RayTun или Clash.

## Возможности

- одна кнопка `Подключиться`;
- сетевые probes с классификацией блокировки;
- запрос `https://xservis.pro/api/connect/auto-config`;
- отправка технической telemetry в `https://xservis.pro/api/telemetry/network-scan`;
- fallback на subscription URL;
- Android deep-link import с именем профиля `Xservis`.

## Сборка

```bash
export ANDROID_HOME=/path/to/android-sdk
./gradlew :app:assembleDebug
```

Debug APK будет в `app/build/outputs/apk/debug/app-debug.apk`.
