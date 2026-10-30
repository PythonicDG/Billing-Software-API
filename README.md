# 🕯️ Vighnaharta Fataka: Billing Software API

A professional, high-performance REST API built with **Django & Django REST Framework** for the **Vighnaharta Fataka** firecracker wholesale and retail business.

---

## 🏗️ Architecture & Features

-   **Modular Architecture**: Clean separation into `accounts`, `products`, `billing`, and `customers`.
-   **Security**: Single-user Token Authentication.
-   **Inventory**: Unique SKU generation, stock alerts, and firecracker-specific attributes.
-   **Media**: Support for product image uploads.
-   **Production Ready**: Configured for **PostgreSQL**, **WhiteNoise**, and **Gunicorn**.
-   **Documentation**: Ready for frontend integration with clear JSON payloads.

---

## 📊 Project Progress

| Status | Module | Description |
| :--- | :--- | :--- |
| ✅ Done | **Authentication** | Token Auth (single user) |
| ✅ Done | **Inventory** | CRUD, SKU Auto-gen, Search/Filter, Image support |
| ✅ Done | **Data Seeding** | Custom command to fill 100+ firecracker products |
| 🚧 In Prog | **Billing** | Invoices, Bill Items, Cart Integration |
| 📅 Planned | **Customers** | Profiles, Credit Tracking, WhatsApp Integration |
| 📅 Planned | **Reports** | Daily Sales, Stock Level Alerts, PDF Invoices |

---

## 🛠️ Quick Start (Local Setup)

### 1. Installation
```bash
git clone <repository-url>
cd Billing-Software-API
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configuration
Copy `.env.example` to `.env` and update your settings.

### 3. Database setup
```bash
python manage.py makemigrations
python manage.py migrate
```

### 4. Seed Data (Optional)
Fill your local database with 100 firecracker products instantly:
```bash
python manage.py seed_products --count 100
```

### 5. Start Server
```bash
python manage.py runserver
```

---

## 📡 Key Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/login/` | Returns auth token |
| `GET` | `/api/products/` | List all inventory (Search & Pagination) |
| `POST` | `/api/products/` | Add new firecracker (Owner Only) |

---

## 📦 Deployment Guide
The project is configured for **AWS EC2** and **Railway**. 
-   **Production Command**: `gunicorn --bind 0.0.0.0:8000 billing_api.wsgi --daemon`
-   **Static Files**: Auto-handled by WhiteNoise.

---

Built with ❤️ for Vighnaharta Fataka.
