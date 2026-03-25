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

## 💡 About This Project

I am not a developer. I built Freeloadarr to solve a real problem I was having with Plex account sharing on my server. 

This project was created with the help of AI and a lot of iteration, testing, and refinement. While it is working well for my use case, I know there is plenty of room for improvement.

If you are a developer and see ways to improve the code, structure, performance, or features, I would greatly appreciate your feedback or contributions.

---

## 🤝 Contributing

- Open an issue for bugs or suggestions  
- Submit a pull request  
- Share feature ideas  

All contributions are welcome.
