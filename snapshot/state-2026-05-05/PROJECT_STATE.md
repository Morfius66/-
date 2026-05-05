# PROJECT STATE — 2026-05-05

## Кратко

Xservis backend (FastAPI, Docker) + Telegram Mini App + 3X-UI panel. Цель — продавать VPN-подписки россиянам, обходя любую блокировку РКН/ТСПУ. Пользователь нажимает одну кнопку в Mini App, получает рабочую конфигурацию, авто-импорт в V2RayTun или Hiddify, авто-выбор быстрейшей ноды.

## Что сделано

### Phase 1 — VPS Subscription Patch ✅

**Цель:** один subscription endpoint `/api/sub/{sub_id}` отдаёт правильный формат для каждого VPN-клиента и максимум вариантов SNI/fingerprint для обхода DPI.

| Версия | Что добавлено | Статус |
|--------|---------------|--------|
| v1 | awk-based payload extraction | ❌ Не работал в `bash <(curl ...)` |
| v2 | heredoc-based payload + 4 формата (Clash YAML / sing-box JSON / base64-VLESS / plain VLESS) | ✅ Работал, но Hiddify падал с `[SingboxParser] Incorrect Json Format` |
| v3 | Двойной backup (timestamp + golden) + автогенерируемый `rollback.sh` с `--original` флагом | ✅ Откат одной командой |
| v3.1 | Hiddify → base64-VLESS (вместо Clash YAML) — обход парсера Hiddify-Next, который сначала пробует SingboxParser | ✅ V2RayTun + Hiddify импортируются успешно (см. [`logs/v3.1-success-output.md`](./logs/v3.1-success-output.md)) |
| v4 | Декартова матрица **до 10 SNI × 6 fingerprints = до 60 профилей** в одной подписке. Ждёт запуска юзером. | ⏳ В разработке |

**Технические детали:**
- Subscription endpoint: `app/main.py` строка 3344, маркер `XSERVIS_SUB_V2`
- Новый модуль: `app/sub_renderer.py` (414 строк)
- Backup-папки: `/opt/xservis/backups/sub-v2-<TIMESTAMP>` + `/opt/xservis/backups/sub-v2-original` (золотой)
- Deploy URL: `https://xservis-patch-deploy-nhazyons.devinapps.com/xservis_patch.sh`
- Реальные usage-байты: подтягиваются из 3X-UI API `/panel/api/inbounds/getClientTraffics/{email}`

### WebApp — НЕ тронут

Все файлы `webapp/index.html`, `webapp/admin/index.html`, `webapp/import.html` остались как были. Юзер явно потребовал не менять дизайн. Скрипт работает только с backend.

## Что дальше

### Phase 1.x — VPS doработки (если потребуются)

- [ ] Юзер запускает v4 на VPS, проверяет 60 профилей в подписке
- [ ] Юзер расширяет `serverNames` в Reality inbound (10 SNI вместо 1) — **только тогда** v4 даст 60 профилей
- [ ] (опционально) Создать в 3X-UI второй inbound `VLESS+XHTTP` на 443 как fallback для регионов где Reality режется
- [ ] (опционально) Создать второй inbound на нестандартном порту (8443/2096) если 443 в чьём-то регионе режется целиком

### Phase 2 — Android-приложение «X-Service»

См. [`ANDROID_PROJECT_PLAN.md`](./ANDROID_PROJECT_PLAN.md). В отдельной Devin-сессии.

## Как продолжить в новой сессии

1. Открыть **новую сессию Devin** (или продолжить эту)
2. Начать с команды:
   ```
   Прочитай snapshot из репо Morfius66/Xservis ветка snapshot/state-2026-05-05.
   Файл PROJECT_STATE.md содержит контекст. Продолжаем с пункта «Что дальше».
   ```
3. Проверить статус v4 — запускал ли юзер на VPS?
4. Если v4 сработал и юзер хочет 60 профилей — попросить расширить `serverNames` в 3X-UI
5. Дальше — Android (см. план)

## Критические переменные/пути на VPS

| Что | Где |
|-----|-----|
| Backend FastAPI | `/opt/xservis/backend/` |
| WebApp (read-only) | `/opt/xservis/webapp/` |
| 3X-UI БД | `/etc/x-ui/x-ui.db` |
| 3X-UI panel | `https://<VPS_IP>:38669/<RANDOM_PATH>/` |
| Backup-папка | `/opt/xservis/backups/` |
| Backend log | `docker logs xservis-backend` |
| Postgres | `xservis-postgres-1` |

## Известные ограничения / антипаттерны

- ❌ Нельзя слать в Hiddify Clash YAML — Hiddify-Next пробует SingboxParser первым, падает на `mixed-port:`.
- ❌ Reality НЕ принимает произвольный SNI — клиент должен слать ровно тот, что в `serverNames` сервера.
- ❌ Нельзя класть имя профиля в URL — нужен заголовок `Profile-Title: Xservis`.
- ❌ Нельзя делать `auto-detect-interface: false` в Clash YAML — VPN не работает на роуминге Wi-Fi↔LTE.
- ❌ Нельзя класть один профиль в `proxy-groups[type=url-test]` — нужно минимум 2 для сравнения latency.

## Контакты

- **Бот поддержки:** `@xservis_support` в Telegram
- **Юзер:** Грос (grasss061@gmail.com)
- **Devin session:** https://app.devin.ai/sessions/8f78b72a202545bd8609f415c3f81da5

## Версия snapshot

`state-2026-05-05` — ветка `devin/<TS>-snapshot-state-2026-05-05` в [`Morfius66/Xservis`](https://github.com/Morfius66/Xservis).
