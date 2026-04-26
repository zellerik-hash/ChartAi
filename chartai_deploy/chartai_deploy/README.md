# ChartAI Pro

TradingView-ähnliche Aktien-App mit KI-Analyse.

## Lokal starten

```bash
pip install -r requirements.txt
python app.py
# → http://localhost:7432
```

## Kostenlos deployen (öffentlich zugänglich)

### Option 1: Railway (empfohlen, 5min)
1. Konto erstellen: https://railway.app
2. "New Project" → "Deploy from GitHub repo"
3. Diesen Ordner als GitHub-Repo hochladen
4. Railway erkennt automatisch Python und startet die App
5. URL bekommst du unter "Settings" → "Domains"

### Option 2: Render (kostenlos)
1. Konto erstellen: https://render.com
2. "New" → "Web Service" → GitHub-Repo verbinden
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120`
5. Plan: "Free" → Deploy

### Option 3: Fly.io
```bash
curl -L https://fly.io/install.sh | sh
fly auth login
fly launch
fly deploy
```

### Option 4: GitHub → Codespaces (öffentlicher Link)
1. Repo auf GitHub hochladen
2. "Code" → "Codespaces" → "New codespace"
3. Im Terminal: `pip install -r requirements.txt && python app.py`
4. Port 7432 öffentlich machen → URL teilen

## GitHub Repo erstellen (Schritt für Schritt)
```bash
cd chartai_deploy
git init
git add .
git commit -m "ChartAI Pro v11"
# Repo auf github.com erstellen, dann:
git remote add origin https://github.com/DEIN_NAME/chartai-pro.git
git push -u origin main
```

## Features
- 📈 Candlestick Charts (1min bis 5J)
- 🌍 Weltweite Aktien: US, DE, EU, Asia, Indizes, Rohstoffe, Forex
- 📊 Analysten-Bewertungen mit Firmennamen
- 🎯 KI-Optionsschein-Ideen (basierend auf Analysten-Konsens)
- 💡 Trade Ideen (Long/Short/Call/Put)
- 🔍 Scanner für ungewöhnliche Bewegungen
- 🤖 KI Chat (Claude/GPT/Gemini)
- ⚡ Preisalarme
- 📊 Backtesting
- 🌓 Dark/Light Mode
- 🇩🇪/🇬🇧 Deutsch/Englisch

## Hinweis zu API Keys
Die KI-Funktionen benötigen eigene API Keys:
- Claude: https://console.anthropic.com
- GPT: https://platform.openai.com/api-keys  
- Gemini: https://aistudio.google.com/app/apikey

Keys werden nur im Browser gespeichert (localStorage), nie an den Server gesendet außer für die KI-Anfragen.
