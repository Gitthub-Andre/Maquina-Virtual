#!/bin/bash

# Importar a chave pública do MongoDB
curl -fsSL https://www.mongodb.org/static/pgp/server-6.0.asc | sudo gpg --dearmor -o /usr/share/keyrings/mongodb-archive-keyring.gpg

# Adicionar o repositório do MongoDB
echo "deb [signed-by=/usr/share/keyrings/mongodb-archive-keyring.gpg] http://repo.mongodb.org/apt/ubuntu $(lsb_release -cs)/mongodb-org/6.0 multiverse" | sudo tee /etc/apt/sources.list.d/mongodb-org-6.0.list

# Atualizar os pacotes
sudo apt-get update

# Instalar o MongoDB
sudo apt-get install -y mongodb-org

# Iniciar o MongoDB
sudo systemctl start mongod

# Habilitar o MongoDB para iniciar com o sistema
sudo systemctl enable mongod

# Criar usuário admin do MongoDB
mongosh admin --eval '
  db.createUser({
    user: "admin",
    pwd: "sua_senha_segura",
    roles: [ { role: "userAdminAnyDatabase", db: "admin" } ]
  })
'

# Criar banco de dados e usuário da aplicação
mongosh admin -u admin -p sua_senha_segura --eval '
  use file-server;
  db.createUser({
    user: "app_user",
    pwd: "senha_do_app",
    roles: [ { role: "readWrite", db: "file-server" } ]
  })
'

# Habilitar autenticação no MongoDB
sudo sed -i 's/#security:/security:\n  authorization: enabled/' /etc/mongod.conf

# Reiniciar o MongoDB
sudo systemctl restart mongod