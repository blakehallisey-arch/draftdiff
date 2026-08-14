#!/bin/sh
# Writes one file: a `draftdiff` shim on your PATH that runs this checkout.
# Uninstall by deleting the file it prints. Nothing else is touched.
set -e

REPO=$(cd "$(dirname "$0")" && pwd)
BIN=${BIN:-$HOME/.local/bin}
mkdir -p "$BIN"

# PYTHONPATH rather than a virtualenv or a build step: the package is stdlib
# only, so there is nothing to install, only somewhere to import it from.
cat > "$BIN/draftdiff" <<SHIM
#!/bin/sh
PYTHONPATH="$REPO:\${PYTHONPATH}"
export PYTHONPATH
exec python3 -m draftdiff "\$@"
SHIM
chmod +x "$BIN/draftdiff"

echo "installed: $BIN/draftdiff"
echo "put $BIN on your PATH, then run: draftdiff --help"
