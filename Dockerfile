# syntax=docker/dockerfile:1.7

ARG BASE_IMAGE=lscr.io/linuxserver/webtop:ubuntu-xfce
ARG GOST_IMAGE=gogost/gost:3.2.6
ARG WINE_SOURCE_VERSION=11.18
ARG WINE_STAGING_VERSION=11.18

# Build the exact Wine/Staging revision used by this release with one narrow X11
# compatibility option. Keeping this in its own stage prevents compiler/toolchain
# packages from entering the runtime image.
FROM ubuntu:26.04 AS wine-builder
ARG WINE_SOURCE_VERSION
ARG WINE_STAGING_VERSION
ARG WINE_BUILD_JOBS=4
ENV DEBIAN_FRONTEND=noninteractive
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      ca-certificates curl xz-utils tar patch git python3 perl autoconf automake gettext \
      build-essential flex bison pkg-config gcc-mingw-w64 g++-mingw-w64 \
      libx11-dev libxext-dev libxrender-dev libxrandr-dev libxinerama-dev \
      libxcursor-dev libxi-dev libxcomposite-dev libxfixes-dev libxkbregistry-dev \
      libxxf86vm-dev libfreetype-dev libfontconfig1-dev libgl-dev libegl-dev \
      libvulkan-dev libgnutls28-dev libjpeg-dev libpng-dev libtiff-dev \
      libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev libasound2-dev libpulse-dev \
      libdbus-1-dev libudev-dev libusb-1.0-0-dev libkrb5-dev libpcap-dev; \
    rm -rf /var/lib/apt/lists/*
COPY patches/apply-wine-fusion.py /tmp/apply-wine-fusion.py
RUN --mount=type=cache,id=fusion-v31-wine-source,target=/var/cache/fusion-wine,sharing=locked \
    set -eux; \
    wine_tar="/var/cache/fusion-wine/wine-${WINE_SOURCE_VERSION}.tar.xz"; \
    staging_tar="/var/cache/fusion-wine/wine-staging-${WINE_STAGING_VERSION}.tar.gz"; \
    if [ ! -s "$wine_tar" ]; then \
      curl -fL --retry 8 --retry-all-errors --connect-timeout 20 --speed-limit 1024 --speed-time 60 \
        "https://dl.winehq.org/wine/source/11.x/wine-${WINE_SOURCE_VERSION}.tar.xz" -o "$wine_tar"; \
    fi; \
    if [ ! -s "$staging_tar" ]; then \
      curl -fL --retry 8 --retry-all-errors --connect-timeout 20 --speed-limit 1024 --speed-time 60 \
        "https://github.com/wine-staging/wine-staging/archive/refs/tags/v${WINE_STAGING_VERSION}.tar.gz" -o "$staging_tar"; \
    fi; \
    rm -rf /src /build/wine /wine-install; \
    mkdir -p /src /build/wine /wine-install; \
    tar -C /src -xf "$wine_tar"; \
    tar -C /src -xzf "$staging_tar"; \
    test -x "/src/wine-staging-${WINE_STAGING_VERSION}/staging/patchinstall.py"; \
    python3 "/src/wine-staging-${WINE_STAGING_VERSION}/staging/patchinstall.py" \
      --all -d "/src/wine-${WINE_SOURCE_VERSION}"; \
    python3 /tmp/apply-wine-fusion.py "/src/wine-${WINE_SOURCE_VERSION}"; \
    cd /build/wine; \
    "/src/wine-${WINE_SOURCE_VERSION}/configure" \
      --prefix=/opt/wine-fusion \
      --enable-archs=i386,x86_64; \
    make -j"${WINE_BUILD_JOBS}"; \
    make install DESTDIR=/wine-install; \
    test -x /wine-install/opt/wine-fusion/bin/wine; \
    find /wine-install/opt/wine-fusion -name 'winex11.drv*' -print | grep -q winex11.drv

FROM ${GOST_IMAGE} AS gost

# Preserve LinuxServer's patched GPU-aware Xvfb from its own Webtop base.
# The subsequent apt operations may replace /usr/bin/Xvfb with stock Ubuntu Xvfb,
# which cannot handle the -vfbdevice flag used by some Webtop/Selkies releases.
FROM ${BASE_IMAGE} AS webtop-xvfb

FROM ${BASE_IMAGE} AS runtime
USER root
ENV TZ=Etc/UTC \
    PATH=/opt/wine-fusion/bin:${PATH} \
    FUSION_WINE_BIN=/opt/wine-fusion/bin/wine \
    FUSION_WINDOW_MANAGED=Y \
    FUSION_UNMANAGE_OWNED_WINDOWS=N \
    FUSION_WINDOW_POLICY=Y \
    FUSION_WINDOW_DECORATED=Y \
    FUSION_USE_TAKE_FOCUS=N \
    FUSION_UI_API=OpenGL \
    FUSION_WEBVIEW2_DISABLE_GPU=0 \
    FUSION_WEBVIEW2_NO_SANDBOX=1 \
    FUSION_QTWEBENGINE_DISABLE_GPU=0 \
    FUSION_QTWEBENGINE_NO_SANDBOX=0
ARG WINE_PACKAGE_VERSION=11.18~resolute-1

# WineHQ's package is installed here only to pull the tested runtime dependency set.
# The package's Wine tree is removed in the same layer and replaced by our source-built
# Wine 11.18 Staging tree below, so the image does not carry two Wine installations.
RUN set -eu; \
    . /etc/os-release; \
    test "$ID" = ubuntu; \
    test "$VERSION_CODENAME" = resolute; \
    apt-get -o Acquire::Retries=5 -o Acquire::http::Timeout=60 -o Acquire::https::Timeout=60 update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      ca-certificates curl gnupg cabextract unzip xz-utils 7zip gettext file python3 \
      winbind mesa-utils vulkan-tools wget binutils zenity unrar-free openssl icoutils \
      libgl1-mesa-dri libvulkan1 mesa-vulkan-drivers xdg-utils desktop-file-utils \
      xauth dbus-x11 util-linux x11-utils \
      libgtk-3-0t64 libwebkit2gtk-4.1-0 libsecret-1-0 libmspack0t64 libopengl0 \
      libglu1-mesa libwayland-server0 libgstreamer1.0-0 libgstreamer-plugins-base1.0-0 \
      gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-libav \
      gstreamer1.0-gl gstreamer1.0-plugins-bad gstreamer1.0-nice; \
    install -d -m 0755 /etc/apt/keyrings; \
    curl -fL --retry 8 --retry-all-errors --connect-timeout 20 --speed-limit 1024 --speed-time 60 \
      https://dl.winehq.org/wine-builds/winehq.key -o /tmp/winehq.asc; \
    gpg --batch --yes --dearmor --output /etc/apt/keyrings/winehq-archive.gpg /tmp/winehq.asc; \
    chmod 0644 /etc/apt/keyrings/winehq-archive.gpg; \
    rm /tmp/winehq.asc; \
    printf '%s\n' \
      'Types: deb' \
      'URIs: https://dl.winehq.org/wine-builds/ubuntu' \
      'Suites: resolute' \
      'Components: main' \
      'Architectures: amd64' \
      'Signed-By: /etc/apt/keyrings/winehq-archive.gpg' \
      > /etc/apt/sources.list.d/winehq.sources; \
    apt-get -o Acquire::Retries=5 -o Acquire::http::Timeout=60 -o Acquire::https::Timeout=60 update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --install-recommends \
      "winehq-staging=$WINE_PACKAGE_VERSION"; \
    command -v xfwm4; command -v xfconf-query; \
    dpkg-query -W > /opt/fusion-package-versions.txt; \
    rm -rf /opt/wine-staging; \
    rm -rf /var/lib/apt/lists/*

# Restore the matched, patched Xvfb after *all* runtime apt operations.
# Preserve DRI3 support without requiring downstream users to disable GPU rendering.
COPY --from=webtop-xvfb /usr/bin/Xvfb /usr/bin/Xvfb
RUN set -eu; \
    launcher=/etc/s6-overlay/s6-rc.d/svc-xorg/run; \
    test -s "$launcher"; \
    xvfb_help="$(/usr/bin/Xvfb -help 2>&1 || true)"; \
    for flag in -vfbdevice -glamor; do \
      if grep -q -- "$flag" "$launcher"; then \
        if ! printf '%s\n' "$xvfb_help" | grep -q -- "$flag"; then \
          echo >&2 "ERROR: Webtop Xvfb launcher requires $flag, but /usr/bin/Xvfb does not support it"; \
          exit 1; \
        fi; \
      fi; \
    done

COPY --from=wine-builder /wine-install/opt/wine-fusion/ /opt/wine-fusion/
RUN set -eux; \
    /opt/wine-fusion/bin/wine --version | tee /opt/fusion-wine-version.txt; \
    find /opt/wine-fusion -name 'winex11.drv*' -print | grep -q winex11.drv

COPY --from=gost /bin/gost /usr/local/bin/gost
COPY vendor/ /opt/fusion-lab/vendor/
COPY bin/ /opt/fusion-lab/bin/
COPY proxy/bin/ /opt/fusion-lab/bin/
COPY slicers/bin/ /opt/fusion-lab/slicers/
COPY certs/printer-certs.py /opt/fusion-lab/slicers/printer-certs.py
COPY web/ /opt/fusion-lab/web/
COPY root/ /
COPY proxy/root/ /
COPY slicers/root/ /
COPY certs/75-printer-certs /custom-cont-init.d/75-printer-certs

RUN set -eu; \
    chmod +x /opt/fusion-lab/bin/* /opt/fusion-lab/slicers/slicer-run \
      /custom-cont-init.d/50-fusion /custom-cont-init.d/60-fusion-proxy \
      /custom-cont-init.d/70-slicers /custom-cont-init.d/75-printer-certs \
      /custom-services.d/fusion-proxy; \
    ln -sf /opt/fusion-lab/bin/fusion-run /usr/local/bin/fusion-run; \
    ln -sf /opt/fusion-lab/bin/fusion-restart /usr/local/bin/fusion-restart; \
    ln -sf /opt/fusion-lab/bin/fusion-install /usr/local/bin/fusion-install; \
    ln -sf /opt/fusion-lab/slicers/slicer-run /usr/local/bin/bambu-studio; \
    ln -sf /opt/fusion-lab/slicers/slicer-run /usr/local/bin/orca-slicer; \
    desktop-file-validate /usr/share/applications/autodesk-fusion.desktop; \
    desktop-file-validate /usr/share/applications/fusion-bambu-studio.desktop; \
    desktop-file-validate /usr/share/applications/fusion-orca-slicer.desktop; \
    update-desktop-database /usr/share/applications; \
    python3 /opt/fusion-lab/bin/install-selkies.py

# Build a clean unauthenticated Fusion prefix once, then copy it into the final image.
FROM runtime AS installer
ARG FUSION_INSTALLER_URL=https://dl.appstreaming.autodesk.com/production/installers/Fusion%20Admin%20Install.exe
ARG WEBVIEW_INSTALLER_URL=https://go.microsoft.com/fwlink/?linkid=2124701
ARG FUSION_SEED_REV=1
RUN --mount=type=cache,id=fusion-v3-downloads,target=/var/cache/fusion-downloads,sharing=locked \
    --mount=type=cache,id=fusion-v3-winetricks,target=/config/.cache/winetricks,sharing=locked \
    /opt/fusion-lab/bin/build-seed

FROM runtime AS final
ARG FUSION_SEED_REV=1
COPY --from=installer /opt/fusion-seed/ /opt/fusion-seed/

# Native slicers are installed directly into the final image, not as extension images.
RUN --mount=type=cache,id=fusion-v3-slicers,target=/var/cache/fusion-slicers,sharing=locked \
    python3 /opt/fusion-lab/slicers/install.py && \
    python3 /opt/fusion-lab/slicers/printer-certs.py --capture

LABEL org.opencontainers.image.title="Autodesk Fusion 360 + Selkies" \
      org.opencontainers.image.version="3.3.1" \
      org.opencontainers.image.description="Fusion/Wine with managed main window, universal auxiliary-window stacking policy, browser fixes, Selkies, slicers, proxy and printer CA support"
      org.opencontainers.image.authors="seva.kabrits@gmail.com"

# LinuxServer Webtop supplies /init. /config stays persistent and receives the factory seed on first start.
