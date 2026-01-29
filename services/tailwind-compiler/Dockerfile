FROM node:lts-alpine3.23

WORKDIR /app
RUN npm install tailwindcss@latest @tailwindcss/cli@latest
ENV PATH="/app/node_modules/.bin:${PATH}"
COPY services/opengsync-app/static/style /app/style
COPY services/opengsync-app/templates /app/templates