#!/bin/bash
# Entrypoint for Linux Troubleshooting Lab Sandbox

echo "=========================================================="
echo " Starting Linux Troubleshooting Lab Sandbox Environment... "
echo "=========================================================="

/opt/scripts/clean_state.sh

echo "Sandbox ready. Waiting for learner commands..."

# Keep container running indefinitely
exec tail -f /dev/null
