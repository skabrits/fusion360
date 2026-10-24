# Autodesk Fusion 360 in Docker

Run Autodesk Fusion 360 in a Docker container and use it directly from your web browser.

The image provides a complete XFCE desktop streamed through Selkies, with Fusion 360 running under a customized Wine Staging environment.

Consider visiting [source repo](https://github.com/skabrits/fusion360) for more details. Project is published under MIT license.

> This is an unofficial community image. It is not affiliated with or supported by Autodesk.

## What's included

- Autodesk Fusion 360
- Wine 11.18 Staging with Fusion-specific window handling fixes
- XFCE desktop
- Selkies browser-based remote desktop
- Autodesk Identity Manager / browser sign-in support
- Bambu Studio
- OrcaSlicer
- Optional Intel/AMD GPU acceleration
- Optional HTTP/HTTPS/SOCKS5 upstream proxy
- Persistent Fusion configuration and Autodesk login
- Fusion desktop launcher
- `fusion-restart` recovery command

The Fusion installation is already prepared inside the image, so Fusion does not need to be downloaded again every time the container starts.

---

## Requirements

- x86-64 Linux host
- Docker Engine
- Docker Compose v2
- Recommended: at least 8 GB RAM
- Modern Chromium/Chrome/Edge browser

The image currently targets:

```text
linux/amd64
```

---

# Quick start

Create `compose.yaml`:

```yaml
services:
  fusion:
    image: skabrits/fusion360:3.3.1
    container_name: fusion360
    platform: linux/amd64

    environment:
      PUID: 1000
      PGID: 1000
      TZ: Etc/UTC

      CUSTOM_USER: fusion
      PASSWORD: change-me

      TITLE: Autodesk Fusion
      FUSION_AUTOSTART: "1"

    ports:
      - "3081:3001"

    volumes:
      - fusion360_config:/config

    shm_size: 2gb
    mem_limit: 8g
    memswap_limit: 8g

    restart: unless-stopped

volumes:
  fusion360_config:
```

Change:

```yaml
PASSWORD: change-me
```

to a real password.

Then start the container:

```bash
docker compose up -d
```

Open:

```text
https://SERVER_IP:3081
```

Login to the web desktop with:

```text
Username: fusion
Password: the value of PASSWORD
```

Your browser may warn about the self-signed HTTPS certificate. This is expected unless you put the container behind your own reverse proxy.

---

# First Fusion login

Fusion starts automatically by default.

On the first run:

1. Click **Sign In** in Fusion.
2. Autodesk authentication opens in the browser.
3. Sign in with your Autodesk account.
4. Return to Fusion after authentication completes.

Your Autodesk profile and Fusion configuration are stored in:

```text
/config
```

and therefore survive container restarts and image upgrades.

Fusion still requires a valid Autodesk account and appropriate Autodesk license.

---

# Persistent data

Always keep `/config` persistent:

```yaml
volumes:
  - fusion360_config:/config
```

Do not delete this volume unless you intentionally want to reset Fusion completely.

For example, avoid:

```bash
docker compose down -v
```

when upgrading.

Normal upgrade:

```bash
docker compose pull
docker compose up -d
```

---

# GPU acceleration

## Intel / AMD

Pass `/dev/dri` into the container:

```yaml
services:
  fusion:
    devices:
      - /dev/dri:/dev/dri

    group_add:
      - video
      - render
```

A complete example:

```yaml
services:
  fusion:
    image: skabrits/fusion360:3.3.1
    platform: linux/amd64

    environment:
      PUID: 1000
      PGID: 1000
      CUSTOM_USER: fusion
      PASSWORD: change-me
      FUSION_AUTOSTART: "1"

    ports:
      - "3081:3001"

    volumes:
      - fusion360_config:/config

    devices:
      - /dev/dri:/dev/dri

    group_add:
      - video
      - render

    shm_size: 2gb
    mem_limit: 8g

    restart: unless-stopped

volumes:
  fusion360_config:
```

NVIDIA requires NVIDIA Container Toolkit configuration on the host and is not configured automatically by this image.

---

# Starting and restarting Fusion

Normally Fusion can be started from the **Autodesk Fusion** icon on the XFCE desktop.

From a terminal inside the container:

```bash
fusion-run
```

If Fusion or one of its Wine helper processes becomes stuck:

```bash
fusion-restart
```

This performs a clean Wine-prefix restart and launches Fusion again.

You can also use the **Restart Fusion** action from the desktop launcher.

---

# Bambu Studio and OrcaSlicer

Both slicers are included in the same desktop.

They can be started from the XFCE desktop/menu or from a terminal:

```bash
bambu-studio
```

```bash
orca-slicer
```

By default their networking is kept separate from the optional Fusion proxy so local printer communication continues to work normally.

---

# Optional upstream proxy

Fusion can use an HTTP, HTTPS or SOCKS5 proxy.

Example:

```yaml
environment:
  FUSION_PROXY_URL: "http://user:password@proxy.example.com:8080"
```

HTTPS proxy:

```yaml
FUSION_PROXY_URL: "https://user:password@proxy.example.com:8080"
```

SOCKS5:

```yaml
FUSION_PROXY_URL: "socks5://user:password@proxy.example.com:1080"
```

Leave it empty for a normal direct connection:

```yaml
FUSION_PROXY_URL: ""
```

The image runs an internal local proxy forwarder for Fusion when this option is enabled.

---

# Useful environment variables

| Variable | Default | Description |
|---|---|---|
| `PUID` | `1000` | User ID for persistent files |
| `PGID` | `1000` | Group ID for persistent files |
| `TZ` | `Etc/UTC` | Container timezone |
| `CUSTOM_USER` | `fusion` | Web desktop username |
| `PASSWORD` | required | Web desktop password |
| `FUSION_AUTOSTART` | `1` | Start Fusion automatically |
| `FUSION_PROXY_URL` | empty | Optional HTTP/HTTPS/SOCKS5 proxy |
| `SLICERS_USE_PROXY` | `0` | Route slicer HTTP traffic through the Fusion proxy |
| `SLICERS_SOFTWARE_RENDERING` | `0` | Force software rendering for slicers |

The default web port inside the container is:

```text
3001
```

The examples expose it as:

```text
3081
```

---

# Logs

Container logs:

```bash
docker logs fusion360
```

Follow logs:

```bash
docker logs -f fusion360
```

Fusion launcher/session log:

```bash
docker exec fusion360 \
  tail -n 200 /config/.autodesk_fusion/logs/session.log
```

Fusion application log:

```bash
docker exec fusion360 \
  tail -n 200 /config/.autodesk_fusion/logs/fusion.log
```

---

# Known limitations

Fusion 360 does not officially support Linux or Wine.

This image contains several Wine/X11 compatibility fixes to make Fusion usable inside an XFCE/Selkies desktop, but occasional UI or rendering issues may still occur.

In particular:

- Autodesk can update Fusion at any time and break Wine compatibility.
- Some keyboard shortcuts reserved by the host OS/browser cannot be forwarded.
- GPU behavior depends on the host driver and container configuration.
- NVIDIA requires additional host configuration.
- Browser fullscreen and dynamic remote-desktop resizing may behave differently depending on the client browser.

If Fusion becomes stuck, try:

```bash
fusion-restart
```

before deleting `/config`.

---

# Security

The image does **not** contain:

- Autodesk credentials
- Autodesk account cookies
- license bypasses
- proxy credentials
- private printer certificates

Your Fusion account state is created at runtime and stored in the persistent `/config` volume.

For Internet-facing installations, it is recommended to place the container behind a properly configured HTTPS reverse proxy.

---

# Disclaimer

Autodesk and Fusion 360 are trademarks of Autodesk, Inc.

This project is unofficial and is not affiliated with, endorsed by, or supported by Autodesk.

Fusion 360 remains proprietary Autodesk software and requires a valid Autodesk account and license. This image does not bypass Autodesk authentication or licensing.
