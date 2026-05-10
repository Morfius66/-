"""Watchdog: pings VLESS nodes and updates :class:`NodeRegistry`.

Blocked or down nodes are auto-excluded from the subscription so that
client apps' ``url-test`` group only sees alive servers; this is what
gives the user the experience of "internet never drops".
"""
