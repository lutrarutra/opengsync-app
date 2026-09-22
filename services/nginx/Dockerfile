FROM nginx:1.25.4

RUN rm /etc/nginx/conf.d/default.conf
COPY services/nginx/50x.html /usr/share/nginx/html/custom_50x.html

COPY services/backend/static/js /static/js
COPY services/backend/static/images /static/images
COPY services/backend/static/resources /static/resources
COPY services/backend/static/robots.txt /usr/share/nginx/html/robots.txt

ARG MEDIA_GID=1000

# Add nginx user to the media group so it can read mounted media files
RUN groupadd -g ${MEDIA_GID} mediagroup && usermod -aG mediagroup nginx