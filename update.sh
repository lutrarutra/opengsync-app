#!/bin/bash

SKIP_TESTS=false

if [[ $EUID -eq 0 ]]; then
    echo "ERROR: This script should not be run as root or with sudo." >&2
    echo "Please run it as a regular user." >&2
    exit 1
fi

# Check for --skip-tests flag
for arg in "$@"; do
    if [ "$arg" == "--skip-tests" ]; then
        SKIP_TESTS=true
    fi
done

if [ "$SKIP_TESTS" = false ]; then
    mkdir ./tmp
    cd ./tmp || exit 1
    git clone https://github.com/lutrarutra/opengsync-app
    cd opengsync-app || exit 1
    sudo bash ./test.sh --build
    STATUS=$?
    cd ../../
    rm -rf ./tmp

    if [ "$STATUS" -ne 0 ]; then
        echo "Some tests failed, exiting"
        exit 1
    fi

    echo "All tests passed..."
else
    echo "Skipping tests as requested..."
fi

echo "Pulling updates for production server..."
git pull

echo "Restarting production server service..."
sudo systemctl restart opengsync

echo "Production server starting as service..."
echo "View logs: 'sudo journalctl -u opengsync -e -f'"