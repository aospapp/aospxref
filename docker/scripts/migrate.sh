#!/bin/bash

# Run in /data/aospapp

sudo cp -rp etc etc_one

for version in `ls src`; do
    set -x
    sed -i "s|/opengrok/src|/opengrok/src/$version|" etc_one/$version/configuration.xml
    sed -i "s|/opengrok/data|/opengrok/data/$version|" etc_one/$version/configuration.xml
done

for version in `ls src`; do
    set -x
    cp -rp webapps/$version/$version webapps_one/
    cp -rp webapps/$version/$version.war webapps_one/
    sed -i "s|/opengrok/etc|/opengrok/etc/$version|" webapps_one/$version/WEB-INF/web.xml
done