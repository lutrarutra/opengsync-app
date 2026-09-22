FROM node:lts-alpine3.23

WORKDIR /app
RUN npm install tailwindcss@latest @tailwindcss/cli@latest
ENV PATH="/app/node_modules/.bin:${PATH}"
COPY services/backend/static/style /app/style
COPY services/backend/static /app/static
COPY services/backend/templates /app/templates