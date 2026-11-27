#!/bin/sh
# Synthetic Linux experiment ONLY, not a production sandbox or trusted runner.
# It cannot run an arbitrary source project and never touches source/ or vanilla/.
set -eu
if [ "${1-}" != "--synthetic-only" ]; then
  echo 'Use --synthetic-only. This experiment is not a runner for user exports.' >&2
  exit 2
fi
REPO=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
FIX="$REPO/tests/fixtures/isolated-vite"
BROWSER=${PLAYWRIGHT_CHROMIUM_EXECUTABLE:-"$REPO/.cache/browser-runtime/chromium"}
BROWSER_LIBS=${PLAYWRIGHT_CHROMIUM_LIB:-"$REPO/.cache/browser-runtime/lib"}
PW=${PLAYWRIGHT_DRIVER_PACKAGE:-"$REPO/.venv/lib/python3.11/site-packages/playwright/driver/package"}
[ "$(uname -s)" = Linux ] && [ "$(uname -m)" = x86_64 ] || { echo 'Requires Linux x86_64' >&2; exit 1; }
for cmd in npm node unshare ip mount python3 setpriv; do command -v "$cmd" >/dev/null || { echo "Missing $cmd" >&2; exit 1; }; done
[ -x /usr/sbin/chroot ] && [ -f "$BROWSER" ] && [ -d "$BROWSER_LIBS" ] && [ -f "$PW/index.js" ] || { echo 'Missing chroot, Chromium, libraries or Playwright driver package' >&2; exit 1; }
mkdir -p "$REPO/.cache"
TMP=$(mktemp -d "$REPO/.cache/vite-spike-XXXXXXXX")
trap 'rm -rf -- "$TMP"' EXIT HUP INT TERM
mkdir -p "$TMP/install" "$TMP/root/bin" "$TMP/root/usr/bin" "$TMP/root/lib/x86_64-linux-gnu" "$TMP/root/lib64" "$TMP/root/app" "$TMP/root/tmp" "$TMP/root/dev" "$TMP/root/proc" "$TMP/root/lib/browser" "$TMP/root/etc" "$TMP/root/usr/share/fonts/truetype" "$TMP/root/var/cache/fontconfig"
chmod 1777 "$TMP/root/tmp"
cp "$FIX/package.json" "$FIX/package-lock.json" "$TMP/install/"
(cd "$TMP/install" && npm_config_cache="$TMP/npm-cache" npm ci --ignore-scripts --no-audit --no-fund)
cp "$(command -v node)" "$TMP/root/bin/node"
cp "$(command -v setpriv)" "$TMP/root/usr/bin/setpriv"
for f in /lib/x86_64-linux-gnu/libdl.so.2 /lib/x86_64-linux-gnu/libstdc++.so.6 /lib/x86_64-linux-gnu/libm.so.6 /lib/x86_64-linux-gnu/libgcc_s.so.1 /lib/x86_64-linux-gnu/libpthread.so.0 /lib/x86_64-linux-gnu/libc.so.6 /lib/x86_64-linux-gnu/libcap-ng.so.0 /lib/x86_64-linux-gnu/librt.so.1 /lib/x86_64-linux-gnu/libexpat.so.1 /lib64/ld-linux-x86-64.so.2; do cp -L "$f" "$TMP/root$f"; done
cp -a "$TMP/install/node_modules" "$TMP/root/app/"
cp -a "$FIX/a" "$FIX/b" "$FIX/harness.cjs" "$TMP/root/app/"
cp -a "$PW" "$TMP/root/app/playwright"
cp "$BROWSER" "$TMP/root/bin/chromium"
cp -a "$BROWSER_LIBS/." "$TMP/root/lib/browser/"
cp -aL /etc/fonts "$TMP/root/etc/"
cp -a /usr/share/fonts/truetype/dejavu "$TMP/root/usr/share/fonts/truetype/"
touch "$TMP/root/dev/null" "$TMP/root/dev/urandom" "$TMP/root/dev/random"
# Host listener demonstrates that the private namespace has a separate loopback.
python3 - "$TMP/root" <<'PY'
import socket, subprocess, sys
root=sys.argv[1]
sock=socket.socket(); sock.bind(('127.0.0.1',0)); sock.listen()
try:
    cmd='mount --make-rprivate / && ip link set lo up && mount --bind /dev/null "$1/dev/null" && mount --bind /dev/urandom "$1/dev/urandom" && mount --bind /dev/random "$1/dev/random" && mount -t proc -o nosuid,nodev,noexec,ro proc "$1/proc" && exec env -i PATH=/bin HOME=/tmp LD_LIBRARY_PATH=/lib/browser HOST_TEST_PORT="$2" /usr/sbin/chroot "$1" /usr/bin/setpriv --bounding-set=-all --inh-caps=-all --ambient-caps=-all --no-new-privs /bin/node /app/harness.cjs'
    subprocess.run(['unshare','--user','--map-root-user','--mount','--net','--pid','--fork','sh','-c',cmd,'sh',root,str(sock.getsockname()[1])],check=True,timeout=45)
finally: sock.close()
PY
