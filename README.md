# 🛡️ Fraud Ring Sentinel

A **defense-only, real-time fraud-ring detector** built for Razorpay's AI Buildathon (Track 02 — AI Risk Manager).

Instead of scoring transactions individually, it builds a live transaction graph, detects coordinated communities, and scores them using five explainable signals.

> ⚠️ **100% synthetic data** — no real transactions, users, or PII. Defense-only — no blocking or charging logic.

---

## 🚀 Quickstart

### Docker (recommended)

```bash
git clone https://github.com/GowsiSM/FraudRingSentinel.git
cd FraudRingSentinel
docker compose up --build
```
