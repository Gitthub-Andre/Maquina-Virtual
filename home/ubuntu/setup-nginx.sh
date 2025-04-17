#!/bin/bash

# Instalar Nginx
sudo apt update
sudo apt install -y nginx

# Instalar Certbot para SSL
sudo apt install -y certbot python3-certbot-nginx

# Criar configuração do Nginx
sudo tee /etc/nginx/sites-available/file-server << 'EOF'
server {
    listen 80;
    server_name seu_dominio.com;

    # Redirecionar HTTP para HTTPS
    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl;
    server_name seu_dominio.com;

    # Configurações SSL serão adicionadas pelo Certbot

    # Frontend
    location / {
        root /var/www/file-server;
        try_files $uri $uri/ /index.html;

        # Configurações de cache para arquivos estáticos
        location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg)$ {
            expires 30d;
            add_header Cache-Control "public, no-transform";
        }
    }

    # Backend API
    location /api {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        # Aumentar limite de upload se necessário
        client_max_body_size 100M;
    }

    # Configurações de segurança
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;
    add_header Content-Security-Policy "default-src 'self' http: https: data: blob: 'unsafe-inline'" always;
}
EOF

# Criar link simbólico
sudo ln -s /etc/nginx/sites-available/file-server /etc/nginx/sites-enabled/

# Remover configuração padrão
sudo rm /etc/nginx/sites-enabled/default

# Criar diretório para o frontend
sudo mkdir -p /var/www/file-server

# Ajustar permissões
sudo chown -R www-data:www-data /var/www/file-server

# Testar configuração do Nginx
sudo nginx -t

# Reiniciar Nginx
sudo systemctl restart nginx

# Obter certificado SSL
sudo certbot --nginx -d seu_dominio.com --non-interactive --agree-tos --email seu_email@dominio.com