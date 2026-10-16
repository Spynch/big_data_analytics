FROM node:22.20.0-bookworm-slim
WORKDIR /migrations
COPY migrations/mongo/package*.json ./
RUN npm ci --omit=dev && npm cache clean --force
COPY migrations/mongo/ ./
ENTRYPOINT ["./node_modules/.bin/migrate-mongo"]
CMD ["up"]
