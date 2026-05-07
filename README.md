# MatchOracle v2

Football Intelligence Engine — Hybrid V1 Algorithm + Claude AI

## Features

- **Engine A** — Match prediction with win/draw/loss probabilities
- **Engine B** — FIFA-style player rating calculator
- **Engine C** — ELO-based team power ranking
- **Engine D** — Monte Carlo match simulation
- **AI Ask** — Natural language football Q&A via Claude AI
- Live scores and today's fixtures
- Weekly forecasts and tips
- Subscription plans (Free / Basic / Pro) with Paystack integration
- REST API with API key authentication

## Stack

- Django 4.2
- Django REST Framework
- WhiteNoise (static files)
- Gunicorn
- Anthropic Claude API
- Paystack payments

## Deployment (Railway)

Set the following environment variables in Railway:

| Variable | Description |
|---|---|
| `SECRET_KEY` | Django secret key |
| `ANTHROPIC_API_KEY` | Claude AI API key |
| `FOOTBALL_API_KEY` | RapidAPI football key |
| `PAYSTACK_SECRET_KEY` | Paystack secret key |
| `PAYSTACK_PUBLIC_KEY` | Paystack public key |
| `EMAIL_HOST_USER` | Gmail address for transactional email |
| `EMAIL_HOST_PASSWORD` | Gmail app password |

The app deploys from the root directory. `manage.py` is at the root.

## Local Development

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```
