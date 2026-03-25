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

## Requirements
- Plex
- Tautulli
- Docker
- Flask

---

## 🐳 Docker Compose (Recommended)

```yaml

services:
  freeloadarr:
    image: ghcr.io/autoentropy/freeloadarr:latest
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

Freeloadarr assigns a dynamic score to each user based on recent Plex activity observed via Tautulli.

Scores are calculated across rolling time windows:
- **1 day** (most recent signal)
- **7 days**
- **14 days**
- **30 days**

The 1-day score is treated as the most important indicator of current behavior.

---

## 🧠 Detection Signals

Points are added when suspicious activity is detected:

### 🌍 Multiple IP Addresses
- Different external IPs within a short window → **+20 points**
- Frequent IP switching across sessions → **+10 points per occurrence**

### 📱 Device Anomalies
- Multiple device types in close succession → **+10 points**
- Unusual or new device patterns → **+5–10 points**

### ▶️ Concurrent Streams
- Simultaneous streams from different locations → **+25 points**
- Overlapping sessions → **+15 points**

### ⏱️ Rapid Session Changes
- Rapid start/stop across IPs/devices → **+5–15 points**

---

## ➕ Scoring Behavior

- Points accumulate as events occur
- Repeated behavior increases score progressively
- Older activity decays over time
- Scores are continuously recalculated using rolling windows

---

## 🚦 Score Thresholds

| Score Range | Status           |
|------------|------------------|
| 0 – 39     | Normal           |
| 40 – 69    | Watch            |
| 70+        | Likely Sharing   |

---

## 🔔 Alerts

Alerts are triggered when:

- A user crosses a configured threshold
- A score increases significantly
- A new detection event occurs

Supported notifications:
- Pushbullet
- Discord webhooks
- Daily summary reports

---

## ⚙️ Customization

You can adjust detection sensitivity in the UI:

- Likely sharing threshold
- Watch threshold
- Lookback window
- Polling interval
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
