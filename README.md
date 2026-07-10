# 🚀 MigrAI

> **Automated Dashboard Migration Platform**
>
> Migrate dashboards, charts, datasets, layouts, and filters from **Metabase** to **Apache Superset** using a modern web interface powered by React and FastAPI.

---

## 🌟 Overview

MigrAI is a full-stack dashboard migration platform designed to simplify the migration process from Metabase to Apache Superset.

Instead of manually recreating dashboards one chart at a time, MigrAI connects to both platforms through their REST APIs, automatically reads dashboard metadata, converts supported visualizations, recreates datasets, generates layouts, and imports the final dashboard into Apache Superset.

The platform is designed for BI teams, data engineers, and organizations looking to reduce migration time while maintaining dashboard consistency.

---

## ✨ Features

- ✅ Connect to Metabase using REST API
- ✅ Connect to Apache Superset
- ✅ Automatically discover dashboards
- ✅ Migrate complete dashboards
- ✅ Convert supported chart types
- ✅ Dataset mapping
- ✅ Dashboard layout recreation
- ✅ Progress tracking
- ✅ Migration history
- ✅ Error handling and validation
- ✅ Responsive modern UI
- ✅ Docker support
- ✅ Cloud deployment (Vercel + Railway)

---

# 📸 Screenshots

## Dashboard

![Dashboard](images/dashboard.png)

---

## Migration Progress

![Migration Progress](images/migration-progress.png)

---

## Migration Complete

![Migration Complete](images/migration-complete.png)

---

## History

![History](images/history.png)

---

## Settings

![Settings](images/settings.png)

---

# 🏗 Architecture

```
                ┌────────────────────┐
                │      Metabase      │
                └─────────┬──────────┘
                          │
                   REST API Calls
                          │
                          ▼
                ┌────────────────────┐
                │    FastAPI API     │
                │  Migration Engine  │
                └─────────┬──────────┘
                          │
            Metadata Parsing
            Dataset Mapping
            Chart Conversion
            Dashboard Builder
                          │
                          ▼
                ┌────────────────────┐
                │ Apache Superset    │
                └────────────────────┘
```

---

# ⚙ Technology Stack

## Frontend

- React
- TypeScript
- Vite
- CSS

## Backend

- Python
- FastAPI
- Uvicorn

## BI Platforms

- Metabase REST API
- Apache Superset REST API

## Database

- PostgreSQL

## Deployment

- Vercel
- Railway

## Version Control

- Git
- GitHub

---

# 📂 Project Structure

```
metabase-to-superset-migrator/

├── backend/
│   ├── app/
│   ├── requirements.txt
│
├── frontend/
│   ├── src/
│   ├── package.json
│
├── images/
├── README.md
├── LICENSE
└── vercel.json
```

---

# 🚀 Installation

## Clone Repository

```bash
git clone https://github.com/2005gargritik-spec/metabase-to-superset-migrator.git

cd metabase-to-superset-migrator
```

---

## Backend

```bash
cd backend

python -m venv .venv

source .venv/bin/activate

pip install -r requirements.txt

uvicorn app.main:app --reload
```

Backend runs on:

```
http://localhost:8000
```

---

## Frontend

```bash
cd frontend

npm install

npm run dev
```

Frontend runs on

```
http://localhost:5173
```

---

# 🌐 Cloud Deployment

## Frontend

- Vercel

## Backend

- Railway

---

# 📋 Migration Workflow

1. Connect to Metabase
2. Authenticate
3. Load Dashboards
4. Connect to Apache Superset
5. Select Target Database
6. Start Migration
7. Parse Metadata
8. Map Datasets
9. Convert Charts
10. Create Dashboard
11. Verify Migration

---

# 🔌 API Endpoints

### Load Dashboards

```
POST /api/metabase/dashboards
```

### Load Databases

```
POST /api/superset/databases
```

### Start Migration

```
POST /api/migrate
```

### Job Status

```
GET /api/jobs/{job_id}
```

---

# 📌 Supported Chart Types

- Bar Chart
- Line Chart
- Pie Chart
- Table
- Big Number
- KPI
- Time Series

---

# 🛣 Future Roadmap

- OAuth Login
- Multi-user Accounts
- Power BI Support
- Looker Support
- Tableau Support
- Snowflake Integration
- ClickHouse Support
- Rollback Migration
- Migration Reports
- AI-assisted field mapping

---

# 🤝 Contributing

Contributions are welcome.

1. Fork the repository
2. Create a new branch
3. Commit your changes
4. Open a Pull Request

---

# 📄 License

This project is licensed under the MIT License.

---

# 👨‍💻 Author

**Ritik Garg**

GitHub:
https://github.com/2005gargritik-spec

---

⭐ If you found this project useful, consider giving it a Star.
