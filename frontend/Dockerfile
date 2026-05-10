FROM node:20-alpine AS deps
WORKDIR /srv
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

FROM deps AS build
WORKDIR /srv
COPY . .
RUN npm run build

FROM node:20-alpine AS runtime
WORKDIR /srv
ENV NODE_ENV=production
COPY --from=build /srv/.next ./.next
COPY --from=build /srv/public ./public
COPY --from=build /srv/package.json ./package.json
COPY --from=deps /srv/node_modules ./node_modules
EXPOSE 3000
CMD ["npm", "run", "start"]
