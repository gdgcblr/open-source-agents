#!/bin/sh
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
destination=${1:-"$project_dir/build/MigineConnector.app"}
mkdir -p "$destination/Contents/MacOS"
cp "$project_dir/mac-connector/Info.plist" "$destination/Contents/Info.plist"
xcrun swiftc -module-cache-path /private/tmp/migine-swift-cache \
  "$project_dir/mac-connector/main.swift" -o "$destination/Contents/MacOS/MigineConnector" \
  -framework EventKit -framework Contacts
codesign --force --sign - "$destination"
printf 'Built %s\nMIGINE_MAC_HELPER=%s/Contents/MacOS/MigineConnector\n' "$destination" "$destination"
