ARG NGINX_VERSION=1.25.4

# mod_zip streams share downloads as one zip (see docs/file-share.md). Built as a dynamic module
# against the same nginx version as the final image; --with-compat makes it loadable there.
FROM nginx:${NGINX_VERSION} AS mod-zip
ARG NGINX_VERSION
# mod_zip master after 1.3.0: needed for correct CRCs in dynamic builds (explicit filter order), HEAD requests
# and the descriptor/memory growth fix (evanmiller/mod_zip 288d665, 8e65b82, ec39e9b)
ARG MOD_ZIP_COMMIT=d3f9f6f4e22fb05c94341821a183968bbf545c71

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential ca-certificates git wget libpcre2-dev zlib1g-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build
RUN wget -q "https://nginx.org/download/nginx-${NGINX_VERSION}.tar.gz" \
    && tar xzf "nginx-${NGINX_VERSION}.tar.gz" \
    && git clone https://github.com/evanmiller/mod_zip.git \
    && git -C mod_zip checkout "${MOD_ZIP_COMMIT}"
RUN cd "nginx-${NGINX_VERSION}" \
    && ./configure --with-compat --add-dynamic-module=../mod_zip \
    && make modules \
    && cp objs/ngx_http_zip_module.so /build/


FROM nginx:${NGINX_VERSION}

COPY --from=mod-zip /build/ngx_http_zip_module.so /usr/lib/nginx/modules/ngx_http_zip_module.so
# load_module belongs in the main context; conf.d is mounted per deployment
RUN sed -i '1i load_module modules/ngx_http_zip_module.so;' /etc/nginx/nginx.conf

RUN rm /etc/nginx/conf.d/default.conf
COPY services/nginx/50x.html /usr/share/nginx/html/custom_50x.html

COPY services/backend/static/js /static/js
COPY services/backend/static/images /static/images
COPY services/backend/static/resources /static/resources
COPY services/backend/static/robots.txt /usr/share/nginx/html/robots.txt

# Add nginx user to the media group so it can read mounted media files. The GID is set at
# container start (MEDIA_GID env), so one published image works for any host owner.
ENV MEDIA_GID=1000
COPY --chmod=755 services/nginx/media-gid.sh /docker-entrypoint.d/05-media-gid.sh
