#!/usr/bin/env bash
# Template verification oracle — edit to assert your task is CORRECT.
# Exit 0 = correct (loop ends). Non-zero = rejected (agent must keep working).
#
# The agent NEVER edits this file, so it cannot fake the oracle.
#
# === HELD-OUT ORACLE (recommended — defeats overfitting) ====================
# Keep the case file OUTSIDE the sandbox, record a trusted reference, then
# grade the candidate against inputs it has never seen:
#
#   python oracle.py record \
#     --reference "python ref.py" --inputs cases.txt --visible 3 \
#     --out .agentloop/oracle_sealed/oracle.json --seal "$ORACLE_SEAL"
#   python oracle.py grade \
#     --candidate "python sandbox/solution.py" \
#     --oracle .agentloop/oracle_sealed/oracle.json --seal "$ORACLE_SEAL"
#
# In that setup VERIFY_CMD would be: bash verify.sh   (this file calls grade).
# ===========================================================================
set -u
cd "$(dirname "$0")/sandbox" || exit 2

# Minimal placeholder: replace with a real correctness check for your task.
test -f solution.py && echo "solution.py present" || { echo "missing solution.py"; exit 1; }
