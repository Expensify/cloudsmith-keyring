#!/bin/bash

set -eu

CURRENT_VERSION="$(uv version --short)"
readonly CURRENT_VERSION

readonly MAJOR="${CURRENT_VERSION%%.*}"
readonly REMAINING="${CURRENT_VERSION#*.}"
readonly MINOR="${REMAINING%%.*}"
readonly PATCH="${CURRENT_VERSION##*.}"

NEW_MAJOR="$MAJOR"
NEW_MINOR="$MINOR"
NEW_PATCH="$((PATCH + 1))"

if [[ "$NEW_PATCH" -gt 99 ]]; then
  NEW_PATCH=0
  NEW_MINOR="$((NEW_MINOR + 1))"
fi

if [[ "$NEW_MINOR" -gt 99 ]]; then
  NEW_MINOR=0
  NEW_MAJOR="$((NEW_MAJOR + 1))"
fi

readonly NEW_VERSION="$NEW_MAJOR.$NEW_MINOR.$NEW_PATCH"

# This automatically bumps the version, locks, and syncs.
uv vesrion "$NEW_VERSION"
