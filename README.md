# Freeloadarr

<p align="center">
  <img src="static/logo.png" width="120" />
</p>

<p align="center">
  Detect and monitor Plex account sharing using Tautulli data.
</p>

---

## 🔍 Features

- Detect Plex account sharing based on:
  - IP address patterns
  - Device usage
  - Concurrent sessions
- Rolling threat scoring (1 / 7 / 14 / 30 day windows)
- Web UI for monitoring users and threat levels
- Push notifications (Pushbullet / Discord)
- Daily automated reporting

---

## 🐳 Docker Compose (Recommended)

```yaml

services:
  freeloadarr:
    image: freeloadarr:latest
    container_name: freeloadarr
    restart: unless-stopped
    ports:
      - "11012:11012"
    volumes:
      - ./config:/config
    environment:
      - TZ=America/Phoenix
```

### Run

```bash
docker compose up -d
```

---

## 🚀 Quick Start (Manual Build)

```bash
git clone https://github.com/autoentropy/freeloadarr.git
cd freeloadarr

docker build -t freeloadarr .
docker run -d \
  -p 11012:11012 \
  -v $(pwd)/config:/config \
  freeloadarr
```

---

## ⚙️ Configuration

Configure via the web UI:

- **Tautulli URL**
- **Tautulli API Key**
- Notification settings (Pushbullet / Discord)
- Detection thresholds
- Lookback window

---

## 📊 How Scoring Works

Freeloadarr assigns a score based on recent activity:

- **0–39** → Normal  
- **40–69** → Watch  
- **70+** → Likely sharing  

Scores are calculated across:
- 1 day (most recent signal)
- 7 day
- 14 day
- 30 day

---

## 🔔 Notifications

Supports:

- Pushbullet alerts
- Discord webhooks
- Daily reports

---

## ⚠️ Disclaimer

Freeloadarr is not affiliated with Plex or the *arr ecosystem.

---

## 🤝 Contributing

- Open an issue for bugs or suggestions  
- Submit a pull request  
- Share feature ideas  

All contributions are welcome.

---

## 💡 About

Freeloadarr was built to solve real-world Plex account sharing issues.

This project was developed with the help of AI and iterative testing.  
There is plenty of room for improvement—feedback is encouraged.
