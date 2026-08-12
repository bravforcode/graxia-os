#!/usr/bin/env bash
# generate-certs.sh — Self-signed CA + TLS server certs for *.graxia.local
# Usage: bash docker/generate-certs.sh [output_dir]
set -euo pipefail

CERT_DIR="${1:-$(dirname "$0")/certs}"
mkdir -p "$CERT_DIR"
cd "$CERT_DIR"

DOMAIN="graxia.local"
CA_SUBJECT="/C=TH/ST=Bangkok/O=Graxia/CN=Graxia Root CA"
SERVER_SUBJECT="/C=TH/ST=Bangoko/O=Graxia/CN=graxia-api.${DOMAIN}"

# ── 1. Root CA ────────────────────────────────────────────────────────
if [ ! -f ca.key ]; then
  openssl genrsa -out ca.key 4096
fi
openssl req -new -x509 -days 3650 -key ca.key -out ca.crt \
  -subj "$CA_SUBJECT"

# ── 2. Server key + CSR ──────────────────────────────────────────────
openssl genrsa -out server.key 2048

cat > server.cnf <<EOF
[req]
distinguished_name = req_dn
req_extensions = v3_req
prompt = no

[req_dn]
C  = TH
ST = Bangkok
O  = Graxia
CN = graxia.${DOMAIN}

[v3_req]
subjectAltName = @alt_names

[alt_names]
DNS.1 = graxia-api
DNS.2 = graxia-signal
DNS.3 = graxia-executor
DNS.4 = localhost
DNS.5 = *.${DOMAIN}
IP.1  = 127.0.0.1
EOF

openssl req -new -key server.key -out server.csr -config server.cnf

cat > server_ext.cnf <<EOF
authorityKeyIdentifier = keyid,issuer
basicConstraints       = CA:FALSE
keyUsage               = digitalSignature, keyEncipherment
extendedKeyUsage       = serverAuth
subjectAltName         = DNS:graxia-api, DNS:graxia-signal, DNS:graxia-executor, DNS:localhost, DNS:*.${DOMAIN}, IP:127.0.0.1
EOF

openssl x509 -req -days 365 \
  -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out server.crt -extfile server_ext.cnf

rm -f server.csr server.cnf server_ext.cnf ca.srl

echo "TLS certs generated in ${CERT_DIR}:"
ls -la ca.key ca.crt server.key server.crt
