# SentinelAI

SentinelAI is a college project where we tried to build a system that can continuously check whether the person using a logged-in session is actually the same user.

The main idea is based on **typing behaviour**. Everyone has a slightly different way of typing, so we collect things like typing speed, key hold time, flight time, pauses and backspace rate and use them to create a typing profile for the user.

During the first setup, the user gives **3 typing samples**. These are used to create their personal baseline. After that, the system keeps checking new typing activity and compares it with the baseline.

If the behaviour starts looking different, SentinelAI gives a risk score:

- **0–29:** Low
- **30–59:** Medium
- **60–79:** High
- **80–100:** Critical

Depending on the risk level, the system can continue monitoring, ask for verification or lock the session.

### What we used

- Python
- FastAPI
- JavaScript, HTML, CSS
- SQLite
- Scikit-learn
- JWT + Bcrypt
- TypingDNA API (optional)

The project has a local ML/statistical model as well as optional TypingDNA integration. We mainly worked on making the complete flow work from typing data → feature extraction → behaviour checking → risk score.

### Running it

Clone the repository and install the requirements:

```bash
git clone https://github.com/harshisnotHarsh/SentinelAI-Behavioral-Authentication.git
cd SentinelAI-Behavioral-Authentication
pip install -r requirements.txt
```

Create a `.env` file using `.env.example` and add the required keys.

Then run:

```bash
uvicorn backend.main:app --reload
```

Open `http://127.0.0.1:8000` in the browser.

This is an academic project and we are still improving the ML part and testing it with more users and typing samples.
