#!/bin/bash
printenv | sed 's/=\(.*\)/="\1"/' | grep -v "no_proxy" >> /etc/environment
crond -f