# Xservis — Snapshot 2026-05-05

Полный слепок состояния проекта Xservis на момент завершения второй итерации subscription-патча. Подходит для возобновления работы в новой Devin-сессии или вручную.

## Что внутри

| Файл | Назначение |
|------|------------|
| [`README.md`](./README.md) | Этот файл — оглавление |
| [`PROJECT_STATE.md`](./PROJECT_STATE.md) | Текущее состояние, что сделано, что дальше, как продолжить |
| [`ANTI_DPI_STRATEGY.md`](./ANTI_DPI_STRATEGY.md) | Методы РКН/ТСПУ и контрмеры |
| [`ANDROID_PROJECT_PLAN.md`](./ANDROID_PROJECT_PLAN.md) | План Android-приложения «X-Service» (следующая фаза) |
| [`patch/sub_renderer.py`](./patch/sub_renderer.py) | Python-модуль рендеринга подписки в 4 формата |
| [`patch/xservis_patch.sh`](./patch/xservis_patch.sh) | Bash-патч (self-contained, deploy одной командой) |
| [`patch/main_endpoint_patch.py`](./patch/main_endpoint_patch.py) | Эталон endpoint'а (вставляется в `app/main.py`) |
| [`knowledge/xservis-subscription-spec.md`](./knowledge/xservis-subscription-spec.md) | Спецификация subscription endpoint v1.0 |
| [`knowledge/llm-council-skill.md`](./knowledge/llm-council-skill.md) | Skill «LLM Council» для брейншторма |
| [`logs/v3.1-success-output.md`](./logs/v3.1-success-output.md) | Реальный вывод успешного запуска v3.1 на VPS |
| [`screenshots/hiddify-error-singboxparser.png`](./screenshots/hiddify-error-singboxparser.png) | Ошибка Hiddify до перехода на base64 |

## Быстрый старт

```bash
# 1. Применить патч на VPS:
bash <(curl -fsSL https://xservis-patch-deploy-nhazyons.devinapps.com/xservis_patch.sh)

# 2. Откат:
bash /opt/xservis/backups/sub-v2-<TIMESTAMP>/rollback.sh
bash /opt/xservis/backups/sub-v2-<TIMESTAMP>/rollback.sh --original   # к самой первой версии
```

## Версия патча

**v4** — multi-SNI × 6 fingerprints = до 60 профилей в подписке для обхода DPI российских ISP.

## Дальнейшие шаги

См. [`PROJECT_STATE.md`](./PROJECT_STATE.md) — раздел «Что дальше».
