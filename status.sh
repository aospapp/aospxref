for i in {33..21}; do
    echo "status opengrok_aosp_sdk$i"
    docker exec -it opengrok_aosp_sdk$i netstat -tnlp
done
