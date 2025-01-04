#!/usr/bin/env bash

export JAVA_HOME=/usr/lib/jvm/default
log_file="/var/log/aosp-indexer.log"
echo "Versions to deploy:"
for version in `ls /opengrok/src`; do
    echo $version
done
sleep 1
echo "Task start:"
for version in `ls /opengrok/src`; do
    (
    set -x
    opengrok-deploy \
        -c /opengrok/etc/$version/configuration.xml \
        /opengrok/lib/source.war \
	    /usr/local/tomcat/webapps/$version.war
    sleep 20
    opengrok-indexer \
        -J=-Djava.util.logging.config.file=/opengrok/etc/logging.properties \
        -a /opengrok/lib/opengrok.jar -- \
        -c /usr/local/bin/ctags \
        -s /opengrok/src/$version \
	    -d /opengrok/data/$version \
	    -H -P -S -G \
        -W /opengrok/etc/${version}/configuration.xml \
	    -U http://localhost:8080/$version
    )
    if [ $? -eq 0 ]; then
        echo "$(date) $version success."
    else
        echo "$(date) $version failure."
    fi >> "$log_file"
done