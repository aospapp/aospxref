for i in {34..21}; do
    echo "start aosp_opengrok_sdk$i"
    docker-compose --profile init up -d aosp_opengrok_sdk$i
    sleep 3000
done
docker-compose --profile init down