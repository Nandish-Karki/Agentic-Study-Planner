"""Versioned legal copy (BUILD_PLAN §5.1).

Plain text served by the /legal routes; the version string is recorded in the
`consents` table when a user accepts at signup, so we can prove which version
each user agreed to.
"""
from __future__ import annotations

PRIVACY_VERSION = "2026-06-14"
TOS_VERSION = "2026-06-14"

PRIVACY_POLICY = f"""\
PRIVACY POLICY (v{PRIVACY_VERSION})

What we collect:
  - Account: your email address and a hashed password.
  - For each plan: the text of the documents you upload (CV, transcript, target
    role, module handbook) and the credit/semester preferences you set.

Lawful basis: your explicit consent, given at signup and each time you upload.

How documents are handled:
  - Uploaded files are processed in a temporary workspace and DELETED immediately
    after your plan is generated. We do NOT store your uploaded documents.
  - Only the GENERATED PLAN (text) is stored in your account so you can view it.

Third-party processing (important):
  - To generate your plan, the text of your documents is sent to a third-party AI
    provider for processing. By generating a plan you consent to this transfer.

Retention & your rights:
  - Plans are retained until you delete them or your account.
  - Right to erasure: deleting your account permanently purges your plans, jobs,
    consents, events, and audit records.
  - Right to access: you can view and export your stored plans at any time.

Hosting: data is stored in the EU.

Contact: the operator of this deployment.
"""

TERMS_OF_SERVICE = f"""\
TERMS & CONDITIONS (v{TOS_VERSION})

1. The study plans produced by this service are AI-generated guidance only. They
   are NOT official academic advice. Always confirm module choices, prerequisites,
   and credit requirements with your university's examination office.
2. You are responsible for the documents you upload and must have the right to
   process them.
3. The service is provided "as is", without warranty, on a best-effort basis.
4. Abuse (automated scraping, attempts to exceed quotas, or to access other users'
   data) will result in account termination.
"""

COOKIE_NOTICE = """\
COOKIE NOTICE

This service uses only essential cookies/storage required to keep you signed in.
We do not use advertising or third-party tracking cookies. If analytics are added
later, they will be opt-in.
"""
