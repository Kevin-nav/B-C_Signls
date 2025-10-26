#!/bin/bash
# This script generates a self-signed SSL certificate for the server.
# Run this once on your server in the project's root directory.

# Stop on any error
set -e

# Certificate details (can be customized)
COUNTRY="US"
STATE="California"
CITY="San Francisco"
ORGANIZATION="B/C Signals"
ORG_UNIT="Trading Division"
COMMON_NAME="35.208.6.252"

# Check if openssl is installed
if ! [ -x "$(command -v openssl)" ]; then
  echo "Error: openssl is not installed. Please install it to continue." >&2
  exit 1
fi

# Generate the key and certificate
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -sha256 -days 3650 -nodes -subj "/C=$COUNTRY/ST=$STATE/L=$CITY/O=$ORGANIZATION/OU=$ORG_UNIT/CN=$COMMON_NAME"

echo ""
echo "Successfully created key.pem and cert.pem."
echo "Ensure your .env file points to these files with:"
echo "SSL_CERT_PATH=cert.pem"
echo "SSL_KEY_PATH=key.pem"
