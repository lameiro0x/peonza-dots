#!/bin/sh
# Linux-side checks, run FROM THE MAC against the stage box (`ssh arch`, the user's
# Arch laptop). Read-only for that box: the repo is copied to ~/tmp/ryce-pc and
# everything runs from ~/.cache/ryce-verify in a private runtime dir.
#
#   sh check-arch.sh            all checks + bar and sidebar screenshots into out/
#   sh check-arch.sh quick      skip screenshots
#
# The box's login shell is fish: every remote command is a script run by /bin/sh.
set -u
HOST="${RYCE_STAGE_HOST:-arch}"
# Parallel makers each use their own remote copy: RYCE_REMOTE_DIR=tmp/ryce-pc-<slice>.
RDIR="${RYCE_REMOTE_DIR:-tmp/ryce-pc}"
TAG=$(basename "$RDIR")
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$HERE/out"
ssh "$HOST" "mkdir -p $RDIR" || { echo "ssh to $HOST failed"; exit 1; }
rsync -a --delete --exclude inspiracion --exclude .git --exclude out --exclude __pycache__ \
  "$HERE/" "$HOST:$RDIR/" || { echo "rsync to $HOST failed"; exit 1; }

cat > "$HERE/out/.remote-check.sh" <<'EOF'
#!/bin/sh
cd "$HOME/$1" || exit 1
TAG=$(basename "$1"); shift
fail=0
step() { printf '\n== %s\n' "$1"; }
step "harness"; sh tools/stage/harness.sh | tail -4 || fail=1
step "agentd tests on real Linux /proc"
if [ -d agentd/tests ]; then PYTHONPATH=agentd python3 -m unittest discover -s agentd/tests 2>&1 | tail -3 || fail=1; else echo SKIP; fi
step "agentd --once on stage fixtures (no dispatch, private runtime dir)"
# Hermetic: fixtures + a private runtime dir, so the live session on this box is never queried.
if [ -d agentd/agentd ]; then t=$(mktemp -d); mkdir -p "$t/rt"; XDG_RUNTIME_DIR="$t/rt" PYTHONPATH=agentd timeout 20 python3 -m agentd --once --no-dispatch --fixtures agentd/tests/fixtures/stage --outdir "$t/out"; echo "exit=$? files=$(ls "$t/out" | tr '\n' ' ')"; python3 contracts/check_roster.py "$t/out/roster.json" || fail=1; rm -rf "$t"; else echo SKIP; fi
step "Hyprland 0.57.1 --verify-config"
if [ -f hypr/hyprland.lua ]; then sh tools/stage/verify-config.sh hypr/hyprland.lua || fail=1; else echo SKIP; fi
step "systemd units"
if ls systemd/user/*.service >/dev/null 2>&1; then
  # %h-relative ExecStart targets do not exist on this box: only syntax errors count.
  systemd-analyze --user verify systemd/user/*.service systemd/user/*.target systemd/user/*.slice 2>&1 | grep -v -E 'Command .* is not executable|No such file or directory|Failed to prepare filename' | head -20
else echo SKIP; fi
step "GTK3 CSS gate"
if [ -f waybar/tests/gtk3_css_gate.py ]; then
  R="$HOME/.cache/ryce-verify/root"; PYV=$(python3 -c 'import sys; print(f"python{sys.version_info[0]}.{sys.version_info[1]}")')
  PYTHONPATH="$R/usr/lib/$PYV/site-packages" GI_TYPELIB_PATH="$R/usr/lib/girepository-1.0:/usr/lib/girepository-1.0" LD_LIBRARY_PATH="$R/usr/lib" \
    python3 waybar/tests/gtk3_css_gate.py waybar/style.css || fail=1
else echo SKIP; fi
step "qmllint"
if [ -d quickshell/ryce ] && [ -x "$HOME/.cache/ryce-verify/root/usr/lib/qt6/bin/qmllint" ]; then
  LD_LIBRARY_PATH="$HOME/.cache/ryce-verify/root/usr/lib" "$HOME/.cache/ryce-verify/root/usr/lib/qt6/bin/qmllint" \
    -I "$HOME/.cache/ryce-verify/root/usr/lib/qt6/qml" --unqualified disable --import disable quickshell/ryce/*.qml 2>&1 | tail -20
else echo SKIP; fi
if [ "${1:-}" != quick ]; then
  step "scenes"
  # Integration: the bar and the sidebar fed by agentd's REAL output (stage fixtures).
  RYCE_AGENTD=fixtures sh tools/stage/scene.sh bar "/tmp/$TAG-scene-bar.png"
  [ -f quickshell/ryce/shell.qml ] && RYCE_AGENTD=fixtures sh tools/stage/scene.sh sidebar "/tmp/$TAG-scene-sidebar.png"
  [ -f hypr/hyprlock.conf ] && sh tools/stage/scene.sh lock "/tmp/$TAG-scene-lock.png"
fi
echo; [ $fail = 0 ] && echo "check-arch: ok" || echo "check-arch: FAILED"
exit $fail
EOF
scp -q "$HERE/out/.remote-check.sh" "$HOST:/tmp/$TAG-remote-check.sh"
ssh "$HOST" "/bin/sh /tmp/$TAG-remote-check.sh $RDIR ${1:-}"
rc=$?
for s in bar sidebar lock; do scp -q "$HOST:/tmp/$TAG-scene-$s.png" "$HERE/out/$TAG-scene-$s.png" 2>/dev/null && echo "pulled out/$TAG-scene-$s.png"; done
exit $rc
