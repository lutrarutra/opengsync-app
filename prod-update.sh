#!/bin/bash

mkdir ./tmp
cd ./tmp
git clone https://github.com/lutrarutra/opengsync-app
cd opengsync-app
bash ./test.sh --build
STATUS=$?

cd ../../
rm -rf ./tmp

if [ "$STATUS" == 0 ]; then
    echo "All tests passed..."
else
    echo "Some tests failed, exiting"
    exit 1
fi

echo "Pulling updates for production server..."

git pull

echo "Restarting production server service..."

sudo systemctl restart opengsync

echo "Production server starting as service..."
echo "View logs: 'sudo journalctl -u opengsync -e -f'"





