#!/bin/bash

# Instalar Node.js 18.x
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs

# Instalar build tools
sudo apt-get install -y build-essential

# Instalar PM2 globalmente
sudo npm install -g pm2

# Criar diretório para os arquivos
sudo mkdir -p /var/www/files
sudo chown -R $USER:$USER /var/www/files

# Configurar PM2 para iniciar com o sistema
sudo pm2 startup

# Criar arquivo de ambiente do PM2
cat > /var/www/file-server/.env << EOF
PORT=3000
MONGODB_URI=mongodb://app_user:senha_do_app@localhost:27017/file-server
JWT_SECRET=sua_chave_secreta_muito_segura
EMAIL_USER=seu_email@gmail.com
EMAIL_PASS=sua_senha_de_app_do_gmail
ADMIN_EMAIL=andrecastro.celular@gmail.com
FILES_PATH=/var/www/files
EOF

# Configurar permissões do arquivo .env
chmod 600 /var/www/file-server/.env

# Iniciar a aplicação com PM2
cd /var/www/file-server
pm2 start src/server.js --name "file-server"
pm2 save