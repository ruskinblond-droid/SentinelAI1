# SentinelAI — Continuous Behavioral Authentication System

SentinelAI is an AI-powered continuous behavioral biometric authentication platform developed as an academic cybersecurity project. Rather than relying solely on static one-time login credentials, SentinelAI passively evaluates keyboard dynamics in real time to detect unauthorized session takeovers and behavioral anomalies.

---

## Key Features

* **Passive Keystroke Dynamics Engine:** Captures 9 behavioral timing metrics (key hold time, flight time, typing speed, consistency variance, hesitation pauses, and error rates) client-side in the browser.
* **Personalized 3-Sample Baseline Calibration:** Learns the user's authentic typing cadence during initial enrollment across 3 reference samples to calculate an individual behavioral baseline profile.
* **Continuous Real-Time Monitoring:** Silently assesses user typing rhythm in sliding windows (25 keystrokes) without interrupting active work.
* **Explainable Anomaly Detection:** Calculates statistical Z-score deviations against the user's established baseline and presents plain-English explanations of detected deviations (e.g., cadence fluctuations, hold time irregularities).
* **Automated Risk-Based Policy Enforcement:**
  * **0–29 (LOW):** Normal activity, session continues uninterrupted.
  * **30–59 (MEDIUM):** Elevated risk detected, monitoring heightened.
  * **60–79 (HIGH):** Biometric checkpoint challenge initiated.
  * **80–100 (CRITICAL):** Session automatically locked; access paused until re-authenticated.
* **Hybrid Multimodal Biometrics:** Built-in local statistical ML model with optional server-side TypingDNA integration.
* **Strict Privacy by Design:** Text content, characters, and passwords are never recorded or stored. Only numerical timing intervals and statistical features are processed.

---

## Architecture Overview

```
Browser Client (SPA)
  │
  ├── KeystrokeDynamics Engine (Passive Timing Capture)
  ├── 9-Feature Behavioral Vector Generator
  │
  ▼
FastAPI Backend (REST API)
  │
  ├── Authentication & Session Manager (JWT + Bcrypt)
  ├── Local Statistical ML Model (Z-Score Behavioral Assessment)
  ├── Adaptive Learning Engine (Baseline Calibration)
  └── Optional TypingDNA Cloud Proxy (Multimodal Verification)
  │
  ▼
SQLite Database (sentinelai.db)
  ├── Users & Sessions
  ├── Behavior Profiles (Personalized Baselines)
  └── Risk Events & Verification Logs
```

---

## Getting Started

### Prerequisites

* Python 3.10 or higher
* Modern web browser (Chrome, Edge, Firefox)

### Installation

1. **Clone the Repository:**
   ```bash
   git clone https://github.com/harshisnotHarsh/SentinelAI-Behavioral-Authentication.git
   cd SentinelAI-Behavioral-Authentication
   ```

2. **Create and Activate a Virtual Environment:**
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # macOS/Linux:
   source .venv/bin/activate
   ```

3. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment Variables:**
   Copy `.env.example` to create your local `.env`:
   ```bash
   cp .env.example .env
   # Windows PowerShell:
   Copy-Item .env.example .env
   ```

   Configure optional credentials in `.env` (the system operates fully in local ML mode without them):
   ```env
   # TypingDNA API Credentials (Optional)
   TYPINGDNA_API_KEY=your_api_key_here
   TYPINGDNA_API_SECRET=your_api_secret_here

   # Application Security
   SECRET_KEY=your_secret_key_here

   # Database Connection
   DATABASE_URL=sqlite:///./sentinelai.db
   ```

5. **Start the Application:**
   ```bash
   uvicorn backend.main:app --reload
   ```

6. **Open the Dashboard:**
   Navigate to [http://127.0.0.1:8000](http://127.0.0.1:8000) in your web browser.

---

## Project Structure

```
.
├── backend/
│   ├── main.py               # FastAPI application entrypoint & static mounts
│   ├── api/
│   │   ├── auth.py           # User registration, login, JWT & re-authentication
│   │   ├── dashboard.py      # Security operations metrics & recent events
│   │   ├── enrollment.py     # 3-sample biometric calibration endpoints
│   │   └── monitoring.py     # Continuous verification & feature window processing
│   ├── database/
│   │   ├── database.py       # SQLAlchemy engine & session management
│   │   └── models.py         # Database schema (Users, Profiles, Sessions, Events)
│   ├── frontend/
│   │   └── static/
│   │       ├── index.html    # Single-page application shell
│   │       ├── css/
│   │       │   └── styles.css # Dark cybersecurity interface stylesheet
│   │       └── js/
│   │           ├── app.js    # Application state, SPA router & live dashboard
│   │           ├── keystroke.js # Client-side 9-feature keystroke engine
│   │           └── typingdna.js # TypingDNA client adapter
│   ├── ML/                   # Offline model training & evaluation scripts
│   ├── security/
│   │   └── auth.py           # Bcrypt password hashing & JWT token verification
│   └── services/
│       ├── adaptivelearning.py # Baseline profile updates
│       ├── ml.py             # Local statistical anomaly scoring engine
│       ├── risk_engine.py    # Risk level & action policy determination
│       └── typingdna.py      # Server-side TypingDNA proxy & error handling
├── .env.example              # Template environment variables (no secrets)
├── .gitignore                # Git exclusion patterns
├── requirements.txt          # Python package dependencies
└── README.md                 # Project documentation
```

---

## License

Academic and educational use. Developed for college demonstration and research in continuous behavioral biometrics.
