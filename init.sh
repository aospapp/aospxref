docker-compose up -d openresty
for i in {33..21}; do
    echo "start opengrok_aosp_sdk$i"
    docker-compose up -d opengrok_aosp_sdk$i
    sleep 3000
done
