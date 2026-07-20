#!/usr/bin/env bash
# Verification oracle for the tax-calculator demo.
# Reuses the main project verify.sh logic.
set -u
cd "$(dirname "$0")/../.." || exit 2

exec bash verify.sh
