FROM node:20-alpine

WORKDIR /app

ENV PORT=5173

# Install deps
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --silent || npm install --silent

# Copy source and build
COPY frontend ./frontend
WORKDIR /app/frontend

ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL

RUN npm run build

EXPOSE 5173

CMD ["npm", "run", "start"]