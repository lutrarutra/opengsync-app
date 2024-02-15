#!/bin/bash
source .test.env
rm -rf .tmp/
docker compose -f compose.test.yaml -p limbless-testing up --abort-on-container-exit
rm -rf .tmp/
