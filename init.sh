for i in {33..21}; do
    echo "start aosp_opengrok_sdk$i"
    docker-compose up --profile -d aosp_opengrok_sdk$i
    sleep 3000
done
