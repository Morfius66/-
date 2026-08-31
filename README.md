# Self-Hosted WireGuard VPN Stack

This repository contains everything you need to stand up a small WireGuard-based VPN for personal use or to share secure access with a few trusted peers. The stack is designed to run on any Linux host or VPS and relies on Docker Compose to keep the deployment reproducible and easy to maintain.

## Features

- **Containerised WireGuard server** powered by the [linuxserver/wireguard](https://hub.docker.com/r/linuxserver/wireguard) image
- **Peer management script** to add, list, and remove VPN clients without touching the configuration manually
- **Declarative configuration** committed as templates so secrets can stay outside of version control
- **Environment-driven settings** allowing you to describe the public endpoint, internal subnet, DNS, and more in one place

## Repository layout

```
.
├── config/
│   └── wg0.conf.example       # Sample server configuration used as a starting point
├── scripts/
│   └── manage_wireguard.py    # CLI helper for manipulating the WireGuard configuration
├── docker-compose.yml         # Docker Compose stack to run WireGuard
├── .env.example               # Example environment variables consumed by the Compose stack
└── README.md                  # You are here
```

## Getting started

### 1. Install prerequisites

- Docker Engine 20.10+
- Docker Compose V2 (usually bundled with modern Docker installations)
- WireGuard tooling (`wg`, `wg-quick`) on the host so you can generate keys if required

### 2. Configure environment variables

Copy the example environment file and adjust it to match your deployment. The file intentionally excludes any secrets so it is safe to commit your customised version if you keep real keys elsewhere.

```bash
cp .env.example .env
nano .env
```

Important variables:

| Variable | Description |
| --- | --- |
| `SERVERURL` | Public IP or DNS name clients will use to reach your server |
| `SERVERPORT` | UDP port exposed for WireGuard traffic |
| `INTERNAL_SUBNET` | Internal network the VPN will use (CIDR notation) |
| `PEERDNS` | Upstream DNS resolver advertised to peers |
| `TZ` | Time zone used by the container |

### 3. Prepare a server configuration

Edit `config/wg0.conf.example` or duplicate it to `config/wg0.conf` and set the actual private key for your server interface. The file ships with placeholders (`SERVER_PRIVATE_KEY`, etc.) to make customisation straightforward. It is recommended to keep the real config out of version control—add it to `.gitignore` so secrets stay local.

You can generate a private key with:

```bash
wg genkey
```

### 4. Launch the stack

Start the VPN server with Docker Compose. The first start will create the configuration directory structure used by the container.

```bash
docker compose up -d
```

Check container logs for any issues:

```bash
docker compose logs -f wireguard
```

### 5. Manage peers

Use the helper script to manage VPN clients without editing configuration files manually.

Add a peer:

```bash
python scripts/manage_wireguard.py add \
  --config config/wg0.conf \
  --name laptop \
  --public-key CLIENT_PUBLIC_KEY \
  --allowed-ips 10.13.13.2/32
```

List peers:

```bash
python scripts/manage_wireguard.py list --config config/wg0.conf
```

Remove a peer by name:

```bash
python scripts/manage_wireguard.py remove --config config/wg0.conf --name laptop
```

When you add a peer, the script updates the server configuration and prints a ready-to-use client configuration block you can drop into a new `wg-quick` profile.

### 6. Distribute client profiles

For each peer, supply them with the client configuration produced by the script (or adapt the output to your needs). Make sure to provide the matching private key for the client along with any preshared key you choose to use.

## Development workflow

- Keep sensitive keys out of the repository. Copy `.env.example` to `.env` and add `.env` to your personal global gitignore if necessary.
- Use `python -m compileall scripts` before committing changes to ensure the helper script has no syntax errors.
- Update the example configuration and README if you add new workflow steps or environment variables.

## License

This project is released under the MIT License. Feel free to adapt it for your own infrastructure or extend it with additional tooling.
