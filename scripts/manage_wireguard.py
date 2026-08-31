#!/usr/bin/env python3
"""Utility helpers for managing WireGuard peer configuration.

The script manipulates the server-side configuration file (e.g. `config/wg0.conf`)
by appending, listing, or removing `[Peer]` blocks. Peer names are tracked via a
`# Peer: <name>` comment immediately before the corresponding section.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

PEER_NAME_PREFIX = "# Peer:"


@dataclass
class PeerBlock:
    """Representation of a peer block inside a WireGuard config file."""

    name: Optional[str]
    public_key: Optional[str]
    allowed_ips: Optional[str]
    start: int
    end: int


def read_lines(path: Path) -> List[str]:
    if not path.exists():
        raise FileNotFoundError(
            f"Configuration file '{path}' does not exist. Create it first or copy "
            "config/wg0.conf.example as a starting point."
        )
    return path.read_text().splitlines(keepends=True)


def write_lines(path: Path, lines: Iterable[str]) -> None:
    path.write_text("".join(lines))


def parse_peer_blocks(lines: List[str]) -> List[PeerBlock]:
    peers: List[PeerBlock] = []
    pending_name: Optional[str] = None
    comment_index: Optional[int] = None
    i = 0

    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith(PEER_NAME_PREFIX):
            pending_name = stripped.split(":", 1)[1].strip() or None
            comment_index = i
            i += 1
            continue

        if stripped == "[Peer]":
            start_index = comment_index if comment_index is not None else i
            public_key: Optional[str] = None
            allowed_ips: Optional[str] = None
            j = i + 1
            while j < len(lines):
                next_stripped = lines[j].strip()
                if next_stripped.startswith("[") and next_stripped.endswith("]"):
                    break
                if next_stripped.lower().startswith("publickey"):
                    public_key = next_stripped.split("=", 1)[1].strip()
                if next_stripped.lower().startswith("allowedips"):
                    allowed_ips = next_stripped.split("=", 1)[1].strip()
                j += 1
            peers.append(
                PeerBlock(
                    name=pending_name,
                    public_key=public_key,
                    allowed_ips=allowed_ips,
                    start=start_index,
                    end=j,
                )
            )
            pending_name = None
            comment_index = None
            i = j
            continue

        # If we encountered any other line the pending comment should not persist.
        comment_index = None
        pending_name = None
        i += 1

    return peers


def list_peers(path: Path) -> int:
    lines = read_lines(path)
    peers = parse_peer_blocks(lines)

    if not peers:
        print("No peers found in configuration.")
        return 0

    for idx, peer in enumerate(peers, start=1):
        label = peer.name or f"(unnamed-{idx})"
        print(f"{idx}. {label}")
        if peer.public_key:
            print(f"   PublicKey: {peer.public_key}")
        if peer.allowed_ips:
            print(f"   AllowedIPs: {peer.allowed_ips}")
    return 0


def ensure_unique_peer(peers: List[PeerBlock], name: Optional[str], public_key: str) -> None:
    for peer in peers:
        if name and peer.name and peer.name == name:
            raise ValueError(f"Peer with name '{name}' already exists.")
        if peer.public_key and peer.public_key == public_key:
            raise ValueError(
                "A peer with the provided public key already exists. Public keys must be unique."
            )


def add_peer(
    path: Path,
    name: Optional[str],
    public_key: str,
    allowed_ips: str,
    preshared_key: Optional[str],
    keepalive: Optional[int],
    endpoint: Optional[str],
    client_dns: Optional[str],
    server_public_key: Optional[str],
    client_allowed_ips: str,
) -> int:
    lines = read_lines(path)
    peers = parse_peer_blocks(lines)
    ensure_unique_peer(peers, name, public_key)

    if lines and not lines[-1].endswith("\n"):
        lines[-1] = lines[-1] + "\n"
    if lines and lines[-1].strip():
        lines.append("\n")

    if name:
        lines.append(f"# Peer: {name}\n")
    lines.append("[Peer]\n")
    lines.append(f"PublicKey = {public_key}\n")
    if preshared_key:
        lines.append(f"PresharedKey = {preshared_key}\n")
    lines.append(f"AllowedIPs = {allowed_ips}\n")
    if keepalive is not None:
        lines.append(f"PersistentKeepalive = {keepalive}\n")
    if endpoint:
        lines.append(f"Endpoint = {endpoint}\n")

    write_lines(path, lines)

    client_config = build_client_config(
        name=name,
        allowed_ips=allowed_ips,
        dns=client_dns,
        server_public_key=server_public_key,
        endpoint=endpoint,
        preshared_key=preshared_key,
        keepalive=keepalive,
        client_allowed_ips=client_allowed_ips,
    )

    print("Peer added successfully. Distribute the following client configuration:")
    print()
    print(client_config)
    return 0


def build_client_config(
    *,
    name: Optional[str],
    allowed_ips: str,
    dns: Optional[str],
    server_public_key: Optional[str],
    endpoint: Optional[str],
    preshared_key: Optional[str],
    keepalive: Optional[int],
    client_allowed_ips: str,
) -> str:
    label = name or "peer"
    dns_line = f"DNS = {dns}\n" if dns else ""
    preshared_line = f"PresharedKey = {preshared_key}\n" if preshared_key else ""
    keepalive_line = f"PersistentKeepalive = {keepalive}\n" if keepalive is not None else ""
    endpoint_line = f"Endpoint = {endpoint}\n" if endpoint else "Endpoint = <server-endpoint:port>\n"
    server_key = server_public_key or "SERVER_PUBLIC_KEY"

    client = [
        f"# {label} client configuration",
        "[Interface]",
        "PrivateKey = <client-private-key>",
        f"Address = {allowed_ips}",
    ]
    if dns_line:
        client.append(dns_line.rstrip())

    client.extend(
        [
            "",
            "[Peer]",
            f"PublicKey = {server_key}",
            endpoint_line.rstrip(),
            f"AllowedIPs = {client_allowed_ips}",
        ]
    )

    if preshared_line:
        client.append(preshared_line.rstrip())
    if keepalive_line:
        client.append(keepalive_line.rstrip())

    return "\n".join(client)


def remove_peer(path: Path, name: Optional[str], public_key: Optional[str]) -> int:
    if not name and not public_key:
        raise ValueError("Provide either a peer name or a public key to remove.")

    lines = read_lines(path)
    peers = parse_peer_blocks(lines)

    match: Optional[PeerBlock] = None
    for peer in peers:
        if name and peer.name == name:
            match = peer
            break
        if public_key and peer.public_key == public_key:
            match = peer
            break

    if match is None:
        identifier = name or public_key
        raise ValueError(f"Peer '{identifier}' not found in configuration.")

    del lines[match.start : match.end]

    # Remove any trailing blank lines that exceed two to keep the file tidy.
    while len(lines) >= 2 and not lines[-1].strip() and not lines[-2].strip():
        lines.pop()

    write_lines(path, lines)
    print("Peer removed successfully.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage WireGuard peer configuration blocks.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--config",
        type=Path,
        default=Path("config/wg0.conf"),
        help="Path to the WireGuard configuration file to manage.",
    )

    subparsers.add_parser("list", parents=[common], help="List peers present in the configuration.")

    add_parser = subparsers.add_parser("add", parents=[common], help="Append a new peer to the configuration.")
    add_parser.add_argument("--name", help="Friendly name stored as a comment before the peer block.")
    add_parser.add_argument("--public-key", required=True, help="Peer public key to add.")
    add_parser.add_argument("--allowed-ips", required=True, help="Comma-separated list of AllowedIPs for the peer.")
    add_parser.add_argument(
        "--preshared-key",
        help="Optional preshared key shared with the peer.",
    )
    add_parser.add_argument(
        "--keepalive",
        type=int,
        help="Optional PersistentKeepalive value (in seconds).",
    )
    add_parser.add_argument(
        "--endpoint",
        help="Optional endpoint (host:port) stored in the peer block.",
    )
    add_parser.add_argument(
        "--client-dns",
        help="DNS server advertised in the generated client configuration snippet.",
    )
    add_parser.add_argument(
        "--server-public-key",
        help="Server public key to embed in the generated client configuration."
        " If omitted a placeholder is used.",
    )
    add_parser.add_argument(
        "--client-allowed-ips",
        default="0.0.0.0/0, ::/0",
        help="AllowedIPs value to use on the client configuration (default: %(default)s).",
    )

    remove_parser = subparsers.add_parser(
        "remove", parents=[common], help="Remove a peer block by name or public key."
    )
    remove_parser.add_argument("--name", help="Name of the peer to remove.")
    remove_parser.add_argument("--public-key", help="Public key of the peer to remove.")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "list":
            return list_peers(args.config)
        if args.command == "add":
            return add_peer(
                path=args.config,
                name=args.name,
                public_key=args.public_key,
                allowed_ips=args.allowed_ips,
                preshared_key=args.preshared_key,
                keepalive=args.keepalive,
                endpoint=args.endpoint,
                client_dns=args.client_dns,
                server_public_key=args.server_public_key,
                client_allowed_ips=args.client_allowed_ips,
            )
        if args.command == "remove":
            return remove_peer(args.config, args.name, args.public_key)
    except FileNotFoundError as exc:
        parser.error(str(exc))
    except ValueError as exc:
        parser.error(str(exc))

    parser.error("Unhandled command.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
