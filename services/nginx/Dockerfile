FROM nginx:1.25.4

RUN rm /etc/nginx/conf.d/default.conf
COPY services/nginx/50x.html /usr/share/nginx/html/custom_50x.html

COPY services/opengsync-app/static/js /static/js
COPY services/opengsync-app/static/images /static/images
COPY services/opengsync-app/static/resources /static/resources
COPY services/opengsync-app/static/robots.txt /usr/share/nginx/html/robots.txt