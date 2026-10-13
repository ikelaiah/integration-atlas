#!/usr/bin/env bash
set -euo pipefail

usage() {
  printf 'Usage: %s OUTPUT_DIRECTORY SOURCE_ROOT [SOURCE_ROOT ...]\n' "$0" >&2
}

if [ "$#" -lt 2 ]; then
  usage
  exit 2
fi

bundle=$(mkdir -p -- "$1" && cd -- "$1" && pwd -P)
shift
source_roots=()
for root_input in "$@"; do
  root=$(cd -- "$root_input" 2>/dev/null && pwd -P) || {
    printf 'ERROR: source root is not a readable directory: %s\n' "$root_input" >&2
    exit 2
  }
  case "$bundle/" in
    "$root/"*)
      printf 'ERROR: output directory must not be inside a source root: %s\n' "$root" >&2
      exit 2
      ;;
  esac
  source_roots+=("$root")
done

mkdir -p "$bundle/linux/cron.d" "$bundle/linux/crontabs" "$bundle/source"

fqdn=$(hostname -f 2>/dev/null || hostname)
environment=${ATLAS_ENVIRONMENT:-production}
cat > "$bundle/server.json" <<JSON
{
  "hostname": "$(hostname | sed 's/\\/\\\\/g; s/"/\\"/g)",
  "fqdn": "$(printf '%s' "$fqdn" | sed 's/\\/\\\\/g; s/"/\\"/g')",
  "os": "linux",
  "environment": "$(printf '%s' "$environment" | sed 's/\\/\\\\/g; s/"/\\"/g')"
}
JSON

# Export cron definitions. Access to other accounts' crontabs may require root.
if [ -r /etc/crontab ]; then
  cp -- /etc/crontab "$bundle/linux/cron.d/system-crontab"
else
  printf 'WARN: cannot read /etc/crontab\n' >&2
fi
if [ -d /etc/cron.d ]; then
  find /etc/cron.d -maxdepth 1 -type f -exec cp -- '{}' "$bundle/linux/cron.d/" \; 2>/dev/null ||
    printf 'WARN: some /etc/cron.d files could not be read\n' >&2
fi
while IFS=: read -r user _; do
  target="$bundle/linux/crontabs/$user"
  if crontab -l -u "$user" > "$target" 2>/dev/null; then
    [ -s "$target" ] || rm -f -- "$target"
  else
    rm -f -- "$target"
  fi
done < /etc/passwd

# Copy only text formats understood by Atlas, preserving each source root's paths.
root_index=0
for root in "${source_roots[@]}"; do
  root_index=$((root_index + 1))
  root_name=$(printf '%s' "$root" | sed 's#^/##; s#[/ :]#_#g')
  destination="$bundle/source/$(printf '%02d' "$root_index")-$root_name"
  mkdir -p -- "$destination"

  find "$root" \
    \( -type d \( -name .git -o -name .hg -o -name .svn -o -name .venv -o -name venv \
       -o -name node_modules -o -name __pycache__ -o -name .tox -o -name dist \
       -o -name build -o -name bin -o -name obj \) -prune \) -o \
    \( -type f \( -iname '*.ps1' -o -iname '*.psm1' -o -iname '*.psd1' \
       -o -iname '*.ps1xml' -o -iname '*.bat' -o -iname '*.cmd' \
       -o -iname '*.py' -o -iname '*.pyw' -o -iname '*.pyi' \
       -o -iname '*.sql' -o -iname '*.ddl' -o -iname '*.dml' -o -iname '*.psql' -o -iname '*.db2' \
       -o -iname '*.json' -o -iname '*.yaml' -o -iname '*.yml' -o -iname '*.xml' \
       -o -iname '*.ini' -o -iname '*.cfg' -o -iname '*.conf' -o -iname '*.config' \
       -o -iname '*.properties' -o -iname '*.toml' -o -name '.env' -o -name '.env.*' \) \
       -size -4000000c -print0 \) |
    while IFS= read -r -d '' file; do
      relative=${file#"$root"/}
      mkdir -p -- "$destination/$(dirname -- "$relative")"
      cp -- "$file" "$destination/$relative" ||
        printf 'WARN: could not copy %s\n' "$file" >&2
    done
done

printf 'Bundle created at %s\n' "$bundle"
printf 'Review access warnings, then copy the bundle to the Atlas host.\n'
printf 'The bundle may contain credentials or other sensitive source data; store and transfer it securely.\n' >&2
