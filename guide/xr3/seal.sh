#!/usr/bin/env bash
# XR3: seal guide/xr3/private/* (money totals) for the measurement seat only.
# Hybrid encryption: a random 256-bit key encrypts the tarball (AES-256-CBC, PBKDF2);
# the key is encrypted with RSA-OAEP to guide/xr3/money_pub.pem, whose private half
# never leaves the seat. Plaintext is deleted. Nothing here prints a value.
set -euo pipefail
umask 077
cd "$(dirname "$0")"
part="${1:?part}"
mkdir -p sealed
if [ ! -d private ] || [ -z "$(ls -A private 2>/dev/null)" ]; then
  echo "seal: nothing to seal for $part"; exit 0
fi
k=$(mktemp)
openssl rand -hex 32 > "$k"
tar -C private -czf - . | openssl enc -aes-256-cbc -pbkdf2 -salt -pass "file:$k" -out "sealed/xr3_${part}.tgz.enc"
openssl pkeyutl -encrypt -pubin -inkey money_pub.pem -pkeyopt rsa_padding_mode:oaep -pkeyopt rsa_oaep_md:sha256 \
  -in "$k" -out "sealed/xr3_${part}.key.enc"
rm -f "$k"
rm -rf private
echo "seal: $part sealed ($(stat -c %s "sealed/xr3_${part}.tgz.enc") bytes); plaintext removed"
