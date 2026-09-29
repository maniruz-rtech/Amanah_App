#!/usr/bin/env bash
# Extract the SPKI SHA-256 pin for a TLS endpoint.
#
# Two modes:
#
#   1. live host:
#        ./scripts/extract_spki.sh api.amanah.example 443
#
#   2. local PEM file (RSA or EC):
#        ./scripts/extract_spki.sh --pem path/to/cert.pem
#
# Output is the value to plug into PinningConfig:
#        sha256/<base64>
#
# This script intentionally has no dependencies beyond `openssl`. It does
# NOT modify any project files. Pin rotation playbook lives in
# docs/CERTIFICATE_PINNING_PRODUCTION.md.
set -euo pipefail

usage() {
  cat <<EOF
Usage:
  $0 <host> [<port=443>]            # extract from a live TLS endpoint
  $0 --pem <cert.pem>               # extract from a local PEM cert
EOF
  exit 2
}

[ $# -ge 1 ] || usage

# ── Mode 1: PEM file ──────────────────────────────────────────────────────────
if [ "$1" = "--pem" ]; then
  [ $# -eq 2 ] || usage
  pem="$2"
  [ -f "$pem" ] || { echo "no such file: $pem" >&2; exit 1; }

  hash=$(openssl x509 -in "$pem" -pubkey -noout 2>/dev/null \
    | openssl pkey -pubin -outform DER 2>/dev/null \
    | openssl dgst -sha256 -binary \
    | openssl enc -base64)
  echo "sha256/${hash}"
  exit 0
fi

# ── Mode 2: live host ─────────────────────────────────────────────────────────
host="$1"
port="${2:-443}"

cert=$(openssl s_client -servername "$host" -connect "$host:$port" < /dev/null 2>/dev/null \
  | openssl x509 -outform PEM 2>/dev/null) \
  || { echo "could not fetch cert from $host:$port" >&2; exit 1; }

hash=$(echo "$cert" \
  | openssl x509 -pubkey -noout \
  | openssl pkey -pubin -outform DER 2>/dev/null \
  | openssl dgst -sha256 -binary \
  | openssl enc -base64)

echo "sha256/${hash}"
