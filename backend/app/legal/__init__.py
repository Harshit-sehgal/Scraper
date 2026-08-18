"""Legal pages (Terms of Service, Privacy Policy, Acceptable Use Policy).

E2.5: the app serves its own legal minimum for the beta. The AUP page
renders the exact version enforced by ``app.utils.aup``
(``CURRENT_AUP_VERSION``) so the served policy can never drift from the
enforced one. Lawyer review is the owner's task.
"""

from app.legal.content import LEGAL_PAGES, PRIVACY_VERSION, TERMS_VERSION
from app.legal.router import router

__all__ = ["LEGAL_PAGES", "PRIVACY_VERSION", "TERMS_VERSION", "router"]
