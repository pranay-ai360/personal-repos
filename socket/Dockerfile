FROM node:18-alpine

WORKDIR /app


# Install pm2 globally
RUN npm install -g pm2

COPY package*.json ./
RUN npm install

COPY . .

EXPOSE 3000

CMD ["npm", "start"]