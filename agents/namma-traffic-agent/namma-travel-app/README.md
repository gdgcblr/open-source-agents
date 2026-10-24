# 🚗 Namma Travel App (Android & iPhone)

> Dedicated mobile travel companion and transit optimizer for Bengaluru. Packaged for the **Google Play Store**, **Apple App Store**, and **Instant Progressive Web App (PWA)**.

## ✨ Features
- **Metro vs Bus vs Cab Multimodal Comparison:** Compare BMTC Ordinary vs Vajra AC buses, Purple/Green/Yellow metro lines, and Auto/Bike Taxi/Cab ride-hailing services in real time.
- **Interactive Visual Map:** Visualizes metro tracks, BMTC bus routes with animated vehicles, station stops, and real-time road repair zones.
- **Mobile First Ergonomics:** Responsive bottom-sheet drawer with swipe handles, notch support (`viewport-fit=cover`), and dark slate UI styling.
- **Offline Ready:** Built-in Service Worker (`sw.js`) caches transit assets for low-connectivity subway commutes.
- **Cross-Platform:** Single codebase deployable to Android (via Bubblewrap TWA or Capacitor) and iPhone (via Safari Home Screen or Capacitor iOS).

## 🚀 Quick Launch
To preview the mobile web app locally:
```bash
python -m http.server 8080 --directory www
```
Open `http://localhost:8080` in your mobile browser or desktop responsive mode (390x844).

## 📦 App Store Guides
See [PLAYSTORE_INSTALL_GUIDE.md](./PLAYSTORE_INSTALL_GUIDE.md) for complete step-by-step instructions on:
1. Installing instantly on Android and iPhone without an app store.
2. Building and packaging `.aab` bundles for Google Play Store.
3. Submitting to Google Play Console and Apple App Store Connect.
