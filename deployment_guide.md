# 🚀 Vighnaharta Fataka Django API Backend Production Deployment Guide

This guide describes the end-to-end steps required to deploy the **Django API Backend (Billing-Software-API)** to a clean Linux virtual private server (Ubuntu 20.04/22.04 LTS recommended) using **Gunicorn**, **Nginx**, **Systemd**, and **PostgreSQL** under custom, isolated daemon names to prevent any default system conflicts.

---

## 📋 Table of Contents
1. [Prerequisites](#1-prerequisites)
2. [Step 1: System Packages Installation](#step-1-system-packages-installation)
3. [Step 2: PostgreSQL Database Provisioning](#step-2-postgresql-database-provisioning)
4. [Step 3: Cloning Repository & Setup Workspace](#step-3-cloning-repository--setup-workspace)
5. [Step 4: Environment Variables & Database Migration](#step-4-environment-variables--database-migration)
6. [Step 5: Gunicorn Daemonization (Systemd Custom Socket & Service)](#step-5-gunicorn-daemonization-systemd-custom-socket--service)
7. [Step 6: Nginx Reverse-Proxy Integration](#step-6-nginx-reverse-proxy-integration)
8. [Step 7: Activating SSL/HTTPS with Let's Encrypt Certbot](#step-7-activating-sslhttps-with-lets-encrypt-certbot)
9. [🛠️ Troubleshooting & Server Maintenance Cheatsheet](#%EF%B8%8F-troubleshooting--server-maintenance-cheatsheet)

---

## 1. Prerequisites
*   A Linux Server running **Ubuntu 20.04 / 22.04 LTS** with root or `sudo` access.
*   A domain name pointing to your server's IP address (e.g., `api.vighnahartafataka.com`).
*   Allow port ingress rules:
    *   **Port 22** (SSH)
    *   **Port 80** (HTTP - for redirecting and Let's Encrypt validation)
    *   **Port 443** (HTTPS - secure API communication)

---

## Step 1: System Packages Installation
Log into your server via SSH and execute the following commands to update system packages and install Python, PostgreSQL, Git, Nginx, and Certbot:

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install Python environment utilities, Nginx, PostgreSQL, Git, and build tools
sudo apt install -y python3-pip python3-venv python3-dev libpq-dev postgresql postgresql-contrib nginx git curl build-essential

# Install Certbot and its Nginx plugin for SSL certificate auto-provisioning
sudo apt install -y certbot python3-certbot-nginx
```

---

## Step 2: PostgreSQL Database Provisioning
Log into the PostgreSQL shell as the system database superuser (`postgres`) to create your production database, user, and security configurations:

```bash
# Enter the Postgres shell
sudo -i -u postgres psql
```

Run the following SQL commands (be sure to replace `'SecureProductionPasswordHere'` with a high-entropy password):

```sql
-- 1. Create a dedicated database user for our billing system
CREATE USER vighnaharta_user WITH PASSWORD 'SecureProductionPasswordHere';

-- 2. Tune database parameters for Django connection standards
ALTER ROLE vighnaharta_user SET client_encoding TO 'utf8';
ALTER ROLE vighnaharta_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE vighnaharta_user SET timezone TO 'UTC';

-- 3. Create the production database with the user as the OWNER (PostgreSQL 15+ best practice)
CREATE DATABASE vighnaharta_prod OWNER vighnaharta_user;

-- 4. Grant all database privileges
GRANT ALL PRIVILEGES ON DATABASE vighnaharta_prod TO vighnaharta_user;

-- 5. Connect to the database and grant all schema privileges to the user (Fixes 'permission denied for schema public')
\c vighnaharta_prod
GRANT ALL ON SCHEMA public TO vighnaharta_user;

-- 6. Exit the Postgres CLI shell
\q
```

---

## Step 3: Application Workspace Setup
The project is already cloned and located under `/home/ubuntu/fataka_app/Billing-Software-API/`. We will configure all environment setups, virtual environments, and production run configurations directly within this directory.

Ensure directory permissions are configured properly to allow the Nginx worker group (`www-data`) to read static and media files:
```bash
# Set secure, collaborative permissions on the project directory
sudo chown -R ubuntu:www-data /home/ubuntu/fataka_app/Billing-Software-API
sudo chmod -R 775 /home/ubuntu/fataka_app/Billing-Software-API

# Navigate to the workspace folder
cd /home/ubuntu/fataka_app/Billing-Software-API

# Create a clean isolated Python Virtual Environment
python3 -m venv venv

# Activate the virtual environment
source venv/bin/activate

# Install all production dependencies (Django, Gunicorn, PostgreSQL adapter, etc.)
pip install --upgrade pip
pip install -r requirements.txt
```

---

## Step 4: Environment Variables & Database Migration
1. Copy the `.env.example` file to `.env`:
   ```bash
   cp .env.example .env
   ```
2. Open the `.env` file using a CLI editor (like `nano`) and populate the values:
   ```bash
   nano .env
   ```
   **Key Configurations to Change:**
   *   `SECRET_KEY`: Generate a high-entropy production key (e.g., run `openssl rand -hex 32` in bash and copy the result).
   *   `DEBUG`: Set to `False`.
   *   `ALLOWED_HOSTS`: Set to your API domain name (e.g., `api.vighnahartafataka.com`).
   *   `SECURE_SSL`: Set to `True`.
   *   `DATABASE_URL`: Set to the Postgres credentials created in Step 2:
       `DATABASE_URL=postgres://vighnaharta_user:SecureProductionPasswordHere@127.0.0.1:5432/vighnaharta_prod`
   *   `CORS_ALLOWED_ORIGINS`: Add your web app frontend domain.

3. Run migrations and compile static assets inside the activated virtual environment:
   ```bash
   # Run Django database migrations
   python manage.py migrate

   # Create the administrative user (Django Admin Panel superuser)
   python manage.py createsuperuser

   # Collect all static files (Django admin styling, REST API UI) into 'staticfiles/'
   python manage.py collectstatic --no-input

   # Set secure permissions on media uploads folder
   mkdir -p media
   sudo chmod -R 775 media
   sudo chown -R $USER:www-data media
   ```

---

## Step 5: Gunicorn Daemonization (Systemd Custom Socket & Service)
To manage Gunicorn in the background as a system service that auto-starts on boot, copy our custom socket and service configurations to `/etc/systemd/system/`.

1. **Systemd Socket configuration (`fataka_api.socket`)**:
   ```bash
   # Copy socket configuration to systemd system registry
   sudo cp fataka_api.socket /etc/systemd/system/fataka_api.socket
   ```
2. **Systemd Service configuration (`fataka_api.service`)**:
   ```bash
   # Copy service configuration to systemd system registry
   sudo cp fataka_api.service /etc/systemd/system/fataka_api.service
   ```
   *Note: If your repo files are owned by a different user than `www-data` (e.g., `ubuntu`), open the service file (`sudo nano /etc/systemd/system/fataka_api.service`) and adjust `User=ubuntu`.*

3. **Start and enable the daemons**:
   ```bash
   # Reload Systemd daemon configurations to register new files
   sudo systemctl daemon-reload

   # Enable and start Gunicorn Socket (handles requests immediately)
   sudo systemctl start fataka_api.socket
   sudo systemctl enable fataka_api.socket

   # Start the Gunicorn Service daemon
   sudo systemctl start fataka_api
   sudo systemctl enable fataka_api
   ```

4. **Verify Gunicorn socket bindings**:
   ```bash
   # Check the socket status (should show Active & Listening on /run/fataka_api.sock)
   sudo systemctl status fataka_api.socket

   # Verify the Unix socket exists on the server file system
   ls -la /run/fataka_api.sock
   ```

---

## Step 6: Nginx Reverse-Proxy Integration
1. **Copy custom Nginx configuration**:
   ```bash
   sudo cp fataka_nginx.conf /etc/nginx/sites-available/fataka_api
   ```
2. **Review configurations**:
   Open the file using `sudo nano /etc/nginx/sites-available/fataka_api` and verify that `server_name` matches your domain name and `alias` folders correctly map to `/home/ubuntu/fataka_app/Billing-Software-API/staticfiles/` and `/home/ubuntu/fataka_app/Billing-Software-API/media/`.

3. **Enable the site by symlinking it**:
   ```bash
   # Link sites-available to sites-enabled
   sudo ln -sf /etc/nginx/sites-available/fataka_api /etc/nginx/sites-enabled/

   # (Optional) Remove default Nginx welcome page to prevent overlaps
   sudo rm -f /etc/nginx/sites-enabled/default
   ```

4. **Test Nginx syntax and reload server**:
   ```bash
   # Perform syntax check on Nginx configurations
   sudo nginx -t
   # Output should confirm: syntax is ok, test is successful

   # Reload Nginx server configuration
   sudo systemctl reload nginx
   ```

---

## Step 7: Activating SSL/HTTPS with Let's Encrypt Certbot
To secure the reverse-proxy endpoint with an SSL/TLS Certificate automatically managed by Certbot:

```bash
# Run Certbot mapping to Nginx for your API domain
sudo certbot --nginx -d api.vighnahartafataka.com

# (Follow the prompts: enter your email, agree to terms, and Certbot will automatically
# patch 'fataka_nginx.conf' with the cert file parameters and reload Nginx.)
```

Certbot automatically configures a system timer to renew certificates. To verify the renewal cron runs smoothly:
```bash
sudo certbot renew --dry-run
```

Your Vighnaharta Fataka Backend API is now **100% securely deployed** in production at `https://api.vighnahartafataka.com`!

---

## 🛠️ Troubleshooting & Server Maintenance Cheatsheet

### 1. View Live System Application Logs
Gunicorn outputs stdout/stderr directly into systemd logs. Inspect live logs using `journalctl`:
```bash
# Stream live logs for the Vighnaharta Fataka service
sudo journalctl -u fataka_api -f

# View logs for today only
sudo journalctl -u fataka_api --since today
```

### 2. View Server Access/Error Logs
```bash
# Stream Nginx error logs
sudo tail -f /var/log/nginx/fataka_api_error.log

# View Gunicorn logs in your Django logs folder
tail -f /home/ubuntu/fataka_app/Billing-Software-API/logs/django_error.log
```

### 3. Deploying Code Updates (Simple Git Pull workflow)
Whenever you push updates to your main repository, pull them into the server by running:
```bash
cd /home/ubuntu/fataka_app/Billing-Software-API
git pull origin main

# Activate env and run any new migrations / static collections
source venv/bin/activate
python manage.py migrate
python manage.py collectstatic --no-input

# Restart Gunicorn service to load updated python files
sudo systemctl restart fataka_api
```

### 4. Restarting Services Cheatlist
```bash
# Restart Backend Gunicorn API
sudo systemctl restart fataka_api

# Restart Nginx Reverse-Proxy
sudo systemctl restart nginx

# Reload Gunicorn socket mapping
sudo systemctl restart fataka_api.socket
```
