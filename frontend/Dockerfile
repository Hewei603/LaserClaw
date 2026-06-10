FROM node:22-alpine

WORKDIR /app

# 复制package文件
COPY package*.json ./

# 安装依赖
RUN npm install

# 复制应用代码
COPY . .

# 暴露端口
EXPOSE 5173

# 启动开发服务器
CMD ["npm", "run", "dev", "--", "--host"]
