# Landing Page (Phase 0)

A single static `index.html` (Tailwind via CDN, no build step) for the demand
test: explains the value, captures waitlist emails, and probes willingness-to-pay
with a fake-door pricing section. Pairs with the demo in `../demo/`.

## Before deploying — set two placeholders

Search `index.html` for these and replace every occurrence:

1. **`FORM_ENDPOINT`** — a form backend for a static site. Free option:
   create a form at [formspree.io](https://formspree.io), copy its endpoint
   (e.g. `https://formspree.io/f/abc123`), paste it into every `<form action="...">`.
   Submissions (waitlist emails + chosen price tier via the `source`/`price`
   hidden fields) land in your Formspree inbox / CSV export.
2. **`DEMO_URL`** — the deployed Streamlit demo URL (see `../demo/README.md`).

## Deploy to Vercel (static, free)

```bash
cd landing
npx vercel --prod      # or: drag this folder into vercel.com/new
```

No framework, no build command — Vercel serves `index.html` directly. Point your
domain (or use the `*.vercel.app` URL) and share it in student channels.

## How the two pieces connect

```
landing/index.html  ──"Try the live demo"──►  demo/app.py (Streamlit)
       │                                              │
       └─ waitlist + price probe → Formspree          └─ events.jsonl → demo/funnel.py
```

Read both signals together against the Phase 0 gate (docs/PRODUCT_PLAN.md §10):
Formspree gives you waitlist size + price-tier interest; `funnel.py` gives you
completed plans + in-demo WTP. Hit the gate → build Phase 1. Miss it → re-pitch.

## Privacy

The page itself collects only an email (with the user's action). No documents are
handled here — that's the demo. The footer discloses third-party AI processing.
