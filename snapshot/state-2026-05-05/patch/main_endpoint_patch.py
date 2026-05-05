"""
Этот модуль не импортируется. Это образец нового тела функции subscription(),
которое патч-скрипт ПОДСТАВИТ в /opt/xservis/backend/app/main.py через regex.

Назначение: User-Agent routing + multi-region SNI + real userinfo.
"""

# === ИМПОРТЫ (добавляются в начало main.py) ===
# from .sub_renderer import Profile, render_subscription, format_userinfo

# === НОВОЕ ТЕЛО ENDPOINT (заменяет старое целиком) ===
NEW_ENDPOINT = r'''
@api.get("/api/sub/{sub_id}")
async def subscription(sub_id: str, request: Request):
    """Subscription endpoint с UA-routing + multi-region SNI + real userinfo.

    Форматы по User-Agent:
      Hiddify, Clash, Stash, mihomo → Clash YAML с url-test (auto-switch)
      sing-box, NekoBox, sfa        → sing-box JSON с urltest
      V2RayTun                      → base64-encoded VLESS lines
      Прочие (v2rayNG, Streisand, …) → plain VLESS lines
    """
    xui: XUIManager = request.app.state.xui
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(Subscription).where(
                Subscription.sub_id == sub_id,
                Subscription.status == SubStatus.ACTIVE,
            )
        )
        sub = res.scalar_one_or_none()
    if not sub:
        raise HTTPException(404, "subscription not found or inactive")

    snap = await xui.reality_snapshot(sub.inbound_id)
    server_names = list(snap.server_names) or ["www.microsoft.com"]
    short_id = snap.short_ids[len(snap.short_ids) // 2] if snap.short_ids else ""

    # ── Multi-region trick: дублируем главный inbound с разными SNI и fingerprint
    #    из списка settings.sni_candidates / snap.server_names. У разных провайдеров
    #    DPI-блокировки разные SNI (Beeline режет microsoft, MTS режет cloudflare),
    #    клиент с url-test группой сам выберет рабочий профиль.
    fingerprints_pool = ["chrome", "firefox", "ios"]

    profiles: list[Profile] = []

    # 1. Главный Reality inbound — несколько вариаций SNI × fingerprint
    sni_pool = server_names[:5]  # cap at 5
    for idx, sni in enumerate(sni_pool):
        fp = fingerprints_pool[idx % len(fingerprints_pool)]
        # Безопасное короткое имя для UI: оставляем буквы/цифры
        sni_short = "".join(c for c in sni.split(".")[0] if c.isalnum())[:10] or f"S{idx}"
        profiles.append(Profile(
            name=f"Xservis-RU-{sni_short}-{fp[:2].upper()}",
            server=settings.server_public_host,
            port=snap.port,
            uuid=str(sub.uuid),
            pbk=snap.public_key,
            sid=short_id,
            sni=sni,
            fingerprint=fp,
            flow=snap.flow or "xtls-rprx-vision",
            transport="tcp",
            region_hint="RU-Reality",
        ))

    # 2. XHTTP fallback inbound (для агрессивных DPI на мобильных операторах)
    if settings.geo_inbound_xhttp_fallback and settings.geo_inbound_xhttp_fallback != sub.inbound_id:
        try:
            xsnap = await xui.reality_snapshot(settings.geo_inbound_xhttp_fallback)
            xsni_pool = list(xsnap.server_names) or [server_names[0]]
            xshort = xsnap.short_ids[len(xsnap.short_ids) // 2] if xsnap.short_ids else ""
            for idx, xsni in enumerate(xsni_pool[:2]):
                fp = fingerprints_pool[idx % len(fingerprints_pool)]
                xsni_short = "".join(c for c in xsni.split(".")[0] if c.isalnum())[:10] or f"X{idx}"
                profiles.append(Profile(
                    name=f"Xservis-XHTTP-{xsni_short}",
                    server=settings.server_public_host,
                    port=xsnap.port,
                    uuid=str(sub.uuid),
                    pbk=xsnap.public_key,
                    sid=xshort,
                    sni=xsni,
                    fingerprint=fp,
                    flow="",
                    transport="xhttp",
                    xhttp_path="/",
                    xhttp_mode="auto",
                    region_hint="RU-XHTTP",
                ))
        except Exception:
            logger.exception("xhttp fallback profile build failed for sub %s", sub.id)

    # 3. Extra nodes (multi-region: FI, NL, RU-direct…)
    for node in settings.extra_nodes:
        try:
            transport = node.get("transport", "tcp")
            profiles.append(Profile(
                name=f"Xservis-{node.get('label', 'EXTRA')}",
                server=node["host"],
                port=int(node["port"]),
                uuid=str(node.get("uuid") or sub.uuid),
                pbk=node["pbk"],
                sid=node.get("sid", ""),
                sni=node["sni"],
                fingerprint=node.get("fp", "chrome"),
                flow=node.get("flow", "xtls-rprx-vision"),
                transport=transport,
                xhttp_path=node.get("path", "/"),
                xhttp_mode=node.get("mode", "auto"),
                region_hint=node.get("label", "EXTRA"),
            ))
        except Exception:
            logger.exception("extra_node profile build failed: %s", node)

    if not profiles:
        raise HTTPException(503, "no profiles available — check inbound config")

    # ── Real Subscription-Userinfo (используется/total/expire)
    used_up = 0
    used_down = 0
    total_quota = 0
    try:
        # 3X-UI v2.x API: /panel/api/inbounds/getClientTraffics/{email}
        # _request — internal но публично доступен; обёрнут try/except.
        j = await xui._request("GET", f"/panel/api/inbounds/getClientTraffics/{sub.email}")
        obj = j.get("obj") or {}
        used_up = int(obj.get("up") or 0)
        used_down = int(obj.get("down") or 0)
        total_quota = int(obj.get("total") or 0)  # 0 = unlimited
    except Exception:
        logger.exception("get_client_traffics failed for %s, falling back to zeros", sub.email)

    expire_ts = int(sub.expiry_at.timestamp())

    # ── Render по UA
    ua = request.headers.get("user-agent", "")
    body, content_type = render_subscription(profiles, ua, sub_name="Xservis")

    headers = {
        "Subscription-Userinfo": format_userinfo(used_up, used_down, total_quota, expire_ts),
        "Profile-Update-Interval": "12",
        "Profile-Title": "Xservis",
        "Profile-Web-Page-Url": f"https://{settings.public_domain or 'xservis.pro'}/app/",
        "Support-Url": "https://t.me/xservis_support",
        "Content-Type": content_type,
        "Content-Disposition": 'attachment; filename="Xservis"',
    }
    return PlainTextResponse(body, headers=headers)
'''
