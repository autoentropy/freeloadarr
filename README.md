# Freeloadarr

<p align="center">
  <img src="static/logo.png" width="120" />
</p>

**Freeloadarr** is a Plex account sharing detection and monitoring tool inspired by the *arr ecosystem.

---

## 🔍 Features

- Detect Plex account sharing based on:
  - IP address patterns
  - Device usage
  - Concurrent sessions
- Scoring system (1 / 7 / 14 / 30 day windows)
- Web UI for monitoring users and threat levels
- Push notifications (Pushbullet / Discord)
- Daily reporting

---

## ⚙️ Requirements

- Plex
- Tautulli
- Docker

---

## ⚠️ Disclaimer

Freeloadarr is not affiliated with Plex or the *arr ecosystem.

---

## 🚀 Quick Start

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

## 💡 About This Project

I am not a professional developer — I built Freeloadarr to solve a real problem I was having with Plex account sharing.

This project was created with the help of AI and a lot of iteration, testing, and refinement. While it is working well for my use case, I know there is plenty of room for improvement.

If you are a developer and see ways to improve the code, structure, performance, or features, I would greatly appreciate your feedback or contributions.

---

## 🤝 Contributing / Feedback

- Open an issue for bugs or suggestions  
- Submit a pull request if you'd like to improve something  
- Share ideas for features or improvements  

Even small improvements are welcome.
