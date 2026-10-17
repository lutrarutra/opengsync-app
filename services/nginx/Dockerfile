FROM nginx:1.25.4

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