---
name: testing-trading-bot-ui
description: Test the Trading Bot Control webapp UI end-to-end. Use when verifying theme switching, dark/light mode, button interactions, or Telegram WebApp integration.
---

# Testing Trading Bot Control UI

## Overview
The Trading Bot Control is a static HTML webapp (no build step) using Tailwind CSS + Flowbite via CDN. It integrates with Telegram WebApp SDK for bot command dispatch.

## How to Test Locally

1. Open `index.html` directly in Chrome via `file:///path/to/repo/index.html`
2. No server or build step required — all dependencies load from CDN

## Key Test Areas

### Theme Switching
- Click the palette icon (top-right navbar) to open the Color Theme panel
- 7 themes available: Blue (default), Green, Purple, Red, Orange, Teal, Pink
- Verify: gradient header color changes, icon accent colors change
- Theme selection persists in localStorage (`selectedTheme` key)

### Dark/Light Mode
- Click the sun/moon icon (top-right navbar) to toggle
- Dark mode: body bg-gray-900, cards bg-gray-800
- Light mode: body bg-gray-50, cards bg-white
- Persists in localStorage (`darkMode` key: 'dark' or 'light')

### Button Interactions
- Each card button calls `sendData(command)` which routes to `Telegram.WebApp.sendData()`
- When Telegram SDK is loaded (even outside Telegram), console shows `[Telegram.WebView] > postEvent web_app_data_send {data: '<command>'}`
- Commands: start_bot, set_order_amount, set_timeframes, select_symbols, close_order, show_pnl, show_info, settings, show_logs
- If Telegram SDK is NOT available, a toast notification appears at bottom-center

### Persistence Test
- Set a non-default theme + toggle mode
- Reload page (F5)
- Verify theme and mode are restored from localStorage

## CI Notes
- The repo has a Jekyll CI workflow but no Jekyll config (`_config.yml`). CI will fail — this is a pre-existing issue unrelated to the HTML webapp.
- The HTML file is fully static and does not depend on Jekyll.

## Devin Secrets Needed
None — this is a static HTML file tested locally.
