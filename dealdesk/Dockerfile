# Sinder Deal Desk on our own server (the same app Vercel runs; see deploy/README.md).
FROM node:22-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM node:22-slim
WORKDIR /app
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0
COPY --from=build /app/package.json /app/package-lock.json ./
COPY --from=build /app/node_modules ./node_modules
# .next belongs to the app user: Next writes its prerender, fetch and image caches under .next/cache at run time
# (EACCES on mkdir .next/cache/fetch-cache when it was root's)
COPY --from=build --chown=node:node /app/.next ./.next
RUN mkdir -p /app/.next/cache && chown -R node:node /app/.next/cache
COPY --from=build /app/public ./public
COPY --from=build /app/next.config.mjs ./
USER node
EXPOSE 3000
CMD ["npx", "next", "start", "-p", "3000"]
