def generate_docker_compose_yml(versions):
    template = """  opengrok_aosp_sdk{api}:
    container_name: opengrok_aosp_sdk{api}
    image: opengrok/docker:latest
    environment:
      SYNC_PERIOD_MINUTES: '0'
      URL_ROOT: '/{version}'
    volumes:
       - '/data/aospxref/src/{version}:/opengrok/src/'
       - '/data/aospxref/etc/{version}:/opengrok/etc/'
       - '/data/aospxref/data/{version}:/opengrok/data/'
    networks: 
      vpn:
        ipv4_address: {ip}
"""

    result = ""
    result += 'version: "3"\n\nservices:\n'
    result += """  openresty:
    container_name: openresty
    image: openresty/openresty:alpine
    ports:
      - 8080:80
    volumes:
      - ./conf.d:/etc/nginx/conf.d
      - ./html:/usr/local/openresty/nginx/html
    networks: 
      vpn:
        ipv4_address: 172.168.22.99
"""
    result += "\n"
    for line in versions.splitlines():
        if line != "":
            version, api = line.split(",")
            result += template.format(version=version, api=api, ip="172.168.22.1" + api) + "\n"
    result += """networks:
  vpn:
    driver: bridge
    ipam:
      driver: default
      config:
        - subnet:  172.168.22.0/24
          gateway: 172.168.22.1
"""
    return result


def generate_default_conf(versions):
    template = """    location /{version}/ {
        proxy_pass http://{ip}:8080/{version}/;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        sub_filter '</body>' '<script src="/js/branch.js"></script></body>';
        sub_filter_once off;
    }
"""

    result = """server {
    listen 80;

    root   /usr/local/openresty/nginx/html;
    index  index.html;
"""
    result += "\n"
    for line in versions.splitlines():
        if line != "":
            version, api = line.split(",")
            result += template.replace("{version}", version).replace("{ip}", "172.168.22.1" + api) + "\n"

    result += "}\n"
    return result


# def gen_li(versions):
#     lines = versions.splitlines()
#     lines.reverse()
#     for line in lines:
#         if line != "":
#             version, _ = line.split(",")
#             # print(f'<li><a href="/{version}/">{version}</a></li>')
#             print(f'<li><b>2023-09-25</b> - New Index: <a href="/{version}/">{version}</a></li>')


if __name__ == "__main__":
    with open("versions.txt", "r") as f:
        content = f.read()
    with open("docker-compose.yml", "w") as f:
        f.write(generate_docker_compose_yml(content))
    with open("conf.d/default.conf", "w") as f:
        f.write(generate_default_conf(content))
    # gen_li(content)

