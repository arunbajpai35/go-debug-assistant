## 📘 go-debug-assistant

An AI-powered debugging assistant for backend developers that **analyzes logs**, **correlates traces**, and provides **fix suggestions** using **LLMs**. Built with Python, Redis/Kafka for real-time ingestion, PostgreSQL for storage, and a React dashboard for visualization.

---

### 🚀 Features

* 🔍 **Multi-agent AI analysis** of logs using DeepSeek and Azure GPT.
* 🔗 **Trace correlation** using sliding windows for better context.
* ⚡ **Real-time log ingestion** with Kafka or Redis streams.
* 📊 **React dashboard** to explore logs, fixes, and incident timelines.
* 📁 **Postmortem generator** for incident review and reporting.
* 📦 Integration-ready with **Prometheus + Grafana** for observability.

---

### 🏗️ High-Level Architecture (HLD)

```
                +-----------------------------+
                |    React Frontend UI        |
                +-------------+---------------+
                              |
                              v
                    [ FastAPI Backend APIs ]
                              |
            +----------------+----------------+
            |                                 |
     +------v-------+               +---------v--------+
     | Sliding Window|             | Multi-Agent Engine|
     | Correlator    |             | (DeepSeek, GPT-4o)|
     +--------------+             +--------------------+
            |                                 |
            v                                 v
+---------------------------+     +----------------------------+
| Kafka / Redis Log Stream  |     | Fix Suggestions, Timeline |
+---------------------------+     +----------------------------+
            |
            v
+---------------------------+
|   PostgreSQL + Redis DB   |
|  (Logs, Traces, Analysis) |
+---------------------------+
```

---

### ⚙️ Low-Level Design (LLD)

* **Sliding Window Correlator** (`correlator.py`):

  * Segments logs by service/trace.
  * Maintains temporal windows to ensure contextual grouping.

* **Multi-Agent Analyzer** (`analyze_log.py`):

  * Parallel queries to DeepSeek and Azure GPT.
  * Aggregates suggestions with metadata and AI scores.

* **API Layer** (`backend/api.py`):

  * `/analyze`: Accepts logs and returns correlated fixes.
  * `/timeline`: Generates chronological debug timeline.
  * `/postmortem`: Creates markdown + JSON reports.

* **Dashboard Frontend** (`frontend/`):

  * Views for Logs, Fixes, Timeline, Postmortem.
  * Built with React + Tailwind + Charting Libraries.

---

### 🛠️ Tech Stack

* **Backend**: Python, FastAPI, Redis, PostgreSQL, Kafka

> Note: the repo name (`go-debug-assistant`) is historical. The current implementation is Python-only.
* **Frontend**: React.js, Tailwind, Axios
* **AI Models**: DeepSeek-R1-0528, Azure GPT-4o-mini
* **Monitoring**: Prometheus, Grafana
* **Others**: Docker, Docker Compose

---

### 📦 Setup Instructions

#### 1. Clone and configure

```bash
git clone https://github.com/arunbajpai35/go-debug-assistant.git
cd go-debug-assistant
cp backend/config/config.ini.example backend/config/config.ini  # Add your API keys here
```

#### 2. Start services via Docker

```bash
docker-compose up --build
```

#### 3. Open frontend

Visit [http://localhost:3000](http://localhost:3000) for the dashboard.

---

### 📂 Directory Structure

```
go-debug-assistant/
├── backend/
│   ├── aiagent/              # AI integration modules
│   ├── api.py                # FastAPI entrypoint
│   ├── config/               # API and DB config
│   ├── internal/             # Core engine logic (routes)
│   └── scripts/              # Correlator + utility scripts
├── frontend/                 # React Dashboard
├── Dockerfile
├── docker-compose.yml
└── README.md
```

---

### 🔒 Secrets & Security

> ⚠️ `config.ini` contains sensitive info. It is excluded via `.gitignore`.
> If you've committed secrets already:

* Run `git filter-repo --path backend/config/config.ini --invert-paths --force`
* Re-push the cleaned repo

---

### 📸 Screenshots

You can embed them like this in your README:

```markdown
### 🔍 Log Analysis Panel
![Log Viewer](screenshots/log_viewer.png)

### 🧠 AI Fix Suggestions
![Fix Suggestions](screenshots/fix_suggestions.png)
```

---

### 🧪 Testing

* Unit tests: \[WIP]
* Integration tests for API and Kafka ingestion
* Postmortem validator for AI results

---

### 🧠 Future Scope

* Trace tree visualization (DAG)
* OpenTelemetry integration
* Slack/Jira alerts for fixes
* Auto-rollback triggers

---

### 👤 Author

**Arun Bajpai**
Backend Engineer | Golang + Python + AI Systems
[arunbajpai35@gmail.com](mailto:arunbajpai35@gmail.com)
