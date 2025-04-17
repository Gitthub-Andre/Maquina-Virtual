#!/bin/bash

# Instalar UFW se não estiver instalado
sudo apt-get install -y ufw

# Configurar regras básicas
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Permitir SSH
sudo ufw allow ssh

# Permitir HTTP e HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Permitir MongoDB apenas localmente
sudo ufw allow from 127.0.0.1 to any port 27017

# Habilitar firewall
sudo ufw --force enable

# Mostrar status
sudo ufw status verbose