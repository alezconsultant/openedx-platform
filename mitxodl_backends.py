"""
Custom python-social-auth backends for MIT ODL app SSO.

mitxpro uses the stock ol_social_auth `ol-oauth2` backend.
mitxonline expects a distinct provider named `mitxpro-oauth2` (its historical
default), so we subclass OLOAuth2 only to change the backend `name`. This lets a
single Open edX instance act as the SSO client for BOTH apps simultaneously,
since third_party_auth keys provider configs on (site_id, backend_name).
"""

from ol_social_auth.backends import OLOAuth2


class MITxOnlineOAuth2(OLOAuth2):
    """OL OAuth2 backend for mitxonline (distinct backend name)."""

    name = "mitxpro-oauth2"
