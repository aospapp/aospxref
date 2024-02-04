def generate_docker_compose_yml(versions):
    template_opengrok = """  aosp_opengrok_sdk{api}:
    container_name: aosp_opengrok_sdk{api}
    image: opengrok/docker:latest
    environment:
      SYNC_PERIOD_MINUTES: '0'
      URL_ROOT: '/{version}'
    profiles:
       - init
    volumes:
       - '/data/aospapp/webapps/{version}:/usr/local/tomcat/webapps'
       - '/data/aospapp/src/{version}:/opengrok/src/'
       - '/data/aospapp/etc/{version}:/opengrok/etc/'
       - '/data/aospapp/data/{version}:/opengrok/data/'
    restart: unless-stopped
    networks:
      vpn:
        ipv4_address: {ip}
"""
    template_tomcat = """  aosp_tomcat_sdk{api}:
    container_name: aosp_tomcat_sdk{api}
    image: tomcat:10.1-jdk11
    profiles:
       - service
    volumes:
      - '/data/aospapp/webapps/{version}:/usr/local/tomcat/webapps'
      - '/data/aospapp/src/{version}:/opengrok/src/'
      - '/data/aospapp/etc/{version}:/opengrok/etc/'
      - '/data/aospapp/data/{version}:/opengrok/data/'
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 2G
    networks:
      vpn:
        ipv4_address: {ip}
"""

    result = ""
    result += 'version: "3"\n\nservices:\n'
    result += """  aosp_openresty:
    container_name: aosp_openresty
    image: openresty/openresty:alpine
    profiles:
       - service
    ports:
      - 8080:80
    volumes:
      - ./conf.d:/etc/nginx/conf.d
      - ./html:/usr/local/openresty/nginx/html
    restart: unless-stopped
    networks:
      vpn:
        ipv4_address: 172.16.22.99
"""
    result += "\n"
    for line in versions.splitlines():
        if line != "":
            version, api = line.split(",")
            result += template_tomcat.format(version=version, api=api, ip="172.16.22.1" + api) + "\n"
            result += template_opengrok.format(version=version, api=api, ip="172.16.22.2" + api) + "\n"
    result += """networks:
  vpn:
    driver: bridge
    ipam:
      driver: default
      config:
        - subnet:  172.16.22.0/24
          gateway: 172.16.22.1
"""
    return result


def generate_default_conf(versions):
    template = """    location /{version}/ {
        proxy_pass http://{ip}:8080/{version}/;

        proxy_set_header Host $host;
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
            result += template.replace("{version}", version).replace("{ip}", "172.16.22.1" + api) + "\n"

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
