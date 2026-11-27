#!/bin/sh
# Three separate network/root/PID namespaces with synthetic HTTP relays.
# This is an experiment, not a production runner or acceptance evidence.
set -eu
if [ "$#" -ne 1 ] || [ "$1" != "--synthetic-only" ]; then
  echo 'Use --synthetic-only. This experiment cannot run user exports.' >&2
  exit 2
fi
SANDBOX=1
HOLD=${SPLIT_FIXTURE_HOLD:-0}
case "$HOLD" in 0|1) ;; *) echo 'Invalid synthetic hold mode' >&2; exit 2 ;; esac
if ! command -v cc >/dev/null; then echo "Missing C compiler for synthetic sandbox experiment" >&2; exit 1; fi
REPO=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
FIX="$REPO/tests/fixtures/isolated-vite"
BROWSER=${PLAYWRIGHT_CHROMIUM_EXECUTABLE:-"$REPO/.cache/browser-runtime/chromium"}
BROWSER_LIBS=${PLAYWRIGHT_CHROMIUM_LIB:-"$REPO/.cache/browser-runtime/lib"}
PW=${PLAYWRIGHT_DRIVER_PACKAGE:-"$REPO/.venv/lib/python3.11/site-packages/playwright/driver/package"}
[ "$(uname -s)" = Linux ] && [ "$(uname -m)" = x86_64 ] || { echo 'Requires Linux x86_64' >&2; exit 1; }
for cmd in node unshare nsenter ip mount python3 setpriv prlimit; do command -v "$cmd" >/dev/null || { echo "Missing $cmd" >&2; exit 1; }; done
[ -x /usr/sbin/chroot ] && [ -f "$BROWSER" ] && [ -d "$BROWSER_LIBS" ] && [ -f "$PW/index.js" ] || { echo 'Missing chroot, Chromium, libraries or Playwright driver package' >&2; exit 1; }
mkdir -p "$REPO/.cache"
TMP=$(mktemp -d "$REPO/.cache/split-vite-XXXXXXXX")
trap 'rm -rf -- "$TMP"' EXIT HUP INT TERM
printf 'SYNTHETIC_ROOT %s\n' "$TMP"
mkdir -p "$TMP/install/.work" "$TMP/roots"
cp "$FIX/package.json" "$TMP/install/"
# Registry artifacts are integrity-checked and unpacked without npm/scripts.
cp "$FIX/pnpm-generated-lock.yaml" "$TMP/install/pnpm-lock.yaml"
PYTHON=${SPIKE_PYTHON:-"$REPO/.venv/bin/python"}
[ -x "$PYTHON" ] || { echo 'Missing Python with locked PyYAML' >&2; exit 1; }
PYTHONPATH="$REPO" "$PYTHON" - "$TMP/install" <<'PYPNPM'
import sys
from pathlib import Path
from tools import locked_pnpm, pnpm_tree
source=Path(sys.argv[1]).absolute(); work=source/'.work'
locked_pnpm.cache_tarballs(source,allow_network=True,selected_platform=True)
result=pnpm_tree.prepare(source,'.',work/'pnpm-deps/fixture')
if pnpm_tree.inspect(source,result['record'],result['sha256'])['freshness']!='current': raise ValueError('Synthetic tree drift')
print('PREPARED_PNPM_SYNTHETIC_NO_SCRIPTS packages='+str(result['packages'])+' sha256='+result['tree_snapshot'],flush=True)
PYPNPM
DEPS="$TMP/install/.work/pnpm-deps/fixture/node_modules"
for name in a b browser relay-a relay-b; do
  root="$TMP/roots/$name"
  mkdir -p "$root/bin" "$root/usr/bin" "$root/lib/x86_64-linux-gnu" "$root/lib64" "$root/lib/browser" "$root/app" "$root/tmp" "$root/dev" "$root/proc"
  chmod 1777 "$root/tmp"
  cp "$(command -v node)" "$root/bin/node"
  cp "$(command -v setpriv)" "$root/usr/bin/setpriv"
  cp "$(command -v unshare)" "$root/usr/bin/unshare"
  for f in /lib/x86_64-linux-gnu/libdl.so.2 /lib/x86_64-linux-gnu/libstdc++.so.6 /lib/x86_64-linux-gnu/libm.so.6 /lib/x86_64-linux-gnu/libgcc_s.so.1 /lib/x86_64-linux-gnu/libpthread.so.0 /lib/x86_64-linux-gnu/libc.so.6 /lib/x86_64-linux-gnu/libcap-ng.so.0 /lib/x86_64-linux-gnu/librt.so.1 /lib/x86_64-linux-gnu/libexpat.so.1 /lib64/ld-linux-x86-64.so.2; do cp -L "$f" "$root$f"; done
  touch "$root/dev/null" "$root/dev/urandom" "$root/dev/random"
  cp "$FIX/network-limits.cjs" "$root/app/"
done
cc -O2 -Wall -Wextra -Werror "$FIX/rlimit-probe.c" -o "$TMP/roots/a/usr/bin/fixture-rlimit-probe"
for name in a b; do
  root="$TMP/roots/$name"
  cp -a "$DEPS" "$root/app/"
  cp -a "$FIX/$name" "$root/app/site"
  cp "$FIX/network-server.cjs" "$root/app/"
  printf '%s\n' "synthetic secret $name" > "$root/app/secret-$name.txt"
done
root="$TMP/roots/browser"
cc -O2 -Wall -Wextra -Werror "$FIX/pivot-helper.c" -o "$root/usr/bin/pivot-helper"
cp -a "$PW" "$root/app/playwright"
cp "$FIX/network-browser.cjs" "$root/app/"
cp "$BROWSER" "$root/bin/chromium"
cp -a "$BROWSER_LIBS/." "$root/lib/browser/"
mkdir -p "$root/etc" "$root/usr/share/fonts/truetype" "$root/var/cache/fontconfig"
cp -aL /etc/fonts "$root/etc/"
cp -a /usr/share/fonts/truetype/dejavu "$root/usr/share/fonts/truetype/"
for name in a b; do
  root="$TMP/roots/relay-$name"
  mkdir -p "$root/bridge" "$TMP/bridge/$name" "$TMP/roots/browser/bridge/$name"
  cp "$FIX/network-relay.cjs" "$FIX/network-http-gate.cjs" "$root/app/"
done
# Listener remains on the host network; child probes must not be able to connect.
python3 - "$TMP/roots" "$FIX/network-controller.py" "$SANDBOX" "$HOLD" "$PYTHON" <<'PY'
import socket, subprocess, sys
roots,controller,sandbox,hold,controller_python=sys.argv[1:]
sock=socket.socket(); sock.bind(('127.0.0.1',0)); sock.listen()
port=sock.getsockname()[1]
if port in (4311,4312): raise SystemExit('host test port overlaps fixture')
try:
    script='''mount --make-rprivate / && ip link set lo up &&
      mount -t proc -o nosuid,nodev,noexec proc /proc &&
      for root in "$1/a" "$1/b" "$1/browser" "$1/relay-a" "$1/relay-b"; do
        mount --bind /dev/null "$root/dev/null" &&
        mount --bind /dev/urandom "$root/dev/urandom" &&
        mount --bind /dev/random "$root/dev/random" || exit 1
      done &&
      for name in a b; do
        mount --bind "$1/../bridge/$name" "$1/relay-$name/bridge" &&
        mount --bind "$1/../bridge/$name" "$1/browser/bridge/$name" || exit 1
      done &&
      exec "$6" "$2" "$1" "$3" "$4" "$5"'''
    subprocess.run(['unshare','--user','--map-root-user','--mount','--net','--pid','--fork','--kill-child',
                    '/bin/sh','-c',script,'fixture',roots,controller,str(port),sandbox,hold,controller_python],check=True,timeout=90,close_fds=True)
finally: sock.close()
PY
