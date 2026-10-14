FROM node:24-slim

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ENV VITE_USE_POLLING=true
EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
