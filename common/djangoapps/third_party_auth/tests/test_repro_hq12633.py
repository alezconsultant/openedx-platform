"""
Reproduction for mitodl/hq#12633 ("CI VERAWOOD BLOCKER: Instructor Dashboard
Enrollments Failing" -> "account cannot be created").

Timeline on the ticket: a learner (cbmit1@outlook.com) already has BOTH a
mitxonline/xpro account and an edX account (courses-ci.xpro.mit.edu, uid 194).
Following a link straight into courseware shows the course for a moment, then
bounces the learner back to the IdP login page; logging in again there ends
with "your account cannot be created" -- even though the account already
exists on both sides.

Root cause traced through the SSO pipeline (SOCIAL_AUTH_PIPELINE order is
`associate_by_email_if_oauth` -> `get_username` -> `ensure_user_information`,
see lms/envs/common.py):

1. `associate_by_email_if_oauth` (pipeline.py) is the step meant to silently
   link this login to the learner's existing edX account by email. It works
   correctly, but only trusts the match while the matched account is active
   (`get_associated_user_by_email_response`, third_party_auth/utils.py) --
   a deliberate anti-takeover guard for unverified emails.

2. When that step declines to link (or the emails don't match byte-for-byte),
   `ensure_user_information` falls back to `user_exists()`
   (third_party_auth/utils.py) as a safety net before deciding whether to
   send the browser to /login or /register. That fallback is itself narrower
   than it looks:

       def user_exists(details):
           email = details.get('email')
           username = details.get('username')
           if email:
               return email_exists_or_retired(email)
           elif username:
               return User.objects.filter(username__iexact=username).exists() \
                   or username_exists_or_retired(username)
           return False

   Because `email` is checked first and the branch is `if/elif`, a `details`
   dict that carries *any* email (even one that doesn't match the account on
   file -- e.g. the learner used a different address on the IdP side, or the
   two systems record a different address) short-circuits the function: the
   matching `username` is never consulted, and `user_exists()` reports False
   even though the account is right there.

3. For IdP providers configured to skip email verification / auto-register
   (`should_force_account_creation()` -- this is the normal configuration for
   an OL-managed OAuth2 provider like mitxonline/xpro's), a False from
   `user_exists()` sends the pipeline to `/register` instead of `/login`.

4. The registration endpoint DOES check the username
   (`_handle_duplicate_email_username`,
   openedx/core/djangoapps/user_authn/views/register.py), so it correctly
   detects the collision and refuses with HTTP 409 / `AUTHN_USERNAME_CONFLICT_MSG`.
   That refusal is exactly the "account cannot be created" experience the
   learner hit -- for an account that was never missing, just invisible to
   the pipeline's own existence check one step earlier.
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.urls import reverse
from openedx_events.testing import OpenEdxEventsTestMixin

from common.djangoapps.third_party_auth import pipeline
from common.djangoapps.third_party_auth.tests.testutil import ThirdPartyAuthTestMixin
from common.djangoapps.third_party_auth.utils import get_associated_user_by_email_response, user_exists
from openedx.core.djangoapps.user_api.accounts import AUTHN_USERNAME_CONFLICT_MSG
from openedx.core.djangoapps.user_api.accounts.tests.retirement_helpers import (
    RetirementTestCase,
    setup_retirement_states,  # noqa: F401
)
from openedx.core.djangoapps.user_api.tests.test_views import UserAPITestCase
from openedx.core.djangolib.testing.utils import skip_unless_lms

User = get_user_model()

# The learner from the ticket: already has an account on both sides, just not
# through this particular OAuth2 backend yet.
EXISTING_USERNAME = 'cbmit1'
EXISTING_EMAIL = 'cbmit1@outlook.com'
# What the IdP happens to send back for this login -- same person, but not
# byte-for-byte the email on file (a very ordinary real-world mismatch: a
# secondary address, different casing, etc).
IDP_REPORTED_EMAIL = 'cbmit1+xpro@outlook.com'


@skip_unless_lms
class ExistingAccountInvisibleToUserExistsTest(ThirdPartyAuthTestMixin, UserAPITestCase):
    """
    Exercises the exact fallback (`user_exists`) that `ensure_user_information`
    relies on to avoid re-registering a learner who already has an account.
    """

    def setUp(self):
        super().setUp()
        self.existing_user = User.objects.create(username=EXISTING_USERNAME, email=EXISTING_EMAIL, is_active=True)

    def test_control_username_only_details_are_recognized(self):
        """Control: with no email in `details`, the username match is used."""
        assert user_exists({'username': EXISTING_USERNAME}) is True

    def test_the_bug_mismatched_email_hides_the_username_match(self):
        """
        The bug: `details` from the IdP carries an email that isn't on file,
        but the SAME username the account already has. `user_exists()` still
        reports False, because the `email` branch short-circuits before the
        `username` branch is ever reached.
        """
        details = {'email': IDP_REPORTED_EMAIL, 'username': EXISTING_USERNAME}

        assert User.objects.filter(username=EXISTING_USERNAME).exists()  # the account is right there...
        assert user_exists(details) is False  # ...but user_exists() says otherwise.


@skip_unless_lms
class InactiveAccountNotAutoLinkedTest(ThirdPartyAuthTestMixin, UserAPITestCase):
    """
    Confirms the first link in the chain: `associate_by_email_if_oauth`
    deliberately declines to trust an email match against an inactive
    account, which is what leaves `ensure_user_information`'s `user_exists()`
    fallback as the only thing standing between this learner and a bogus
    "create a new account" dispatch.
    """

    def setUp(self):
        super().setUp()
        self.existing_user = User.objects.create(
            username=EXISTING_USERNAME, email=EXISTING_EMAIL, is_active=False,
        )

    def test_matched_but_inactive_account_is_not_trusted(self):
        details = {'email': EXISTING_EMAIL, 'username': EXISTING_USERNAME}

        # Stand in for social_core's real `associate_by_email`, which looks the
        # learner up by email and would find exactly this account.
        with mock.patch(
            'common.djangoapps.third_party_auth.utils.associate_by_email',
            return_value={'user': self.existing_user, 'is_new': False},
        ):
            association_response, user_is_active = get_associated_user_by_email_response(
                backend=None, details=details, user=None,
            )

        # The match is real...
        assert association_response is not None
        assert association_response['user'] == self.existing_user
        # ...but is_active=False means the caller is told not to use it.
        assert user_is_active is False


@skip_unless_lms
class PipelineDispatchesToRegisterInsteadOfLoginTest(ThirdPartyAuthTestMixin, UserAPITestCase):
    """
    Ties `user_exists()`'s blind spot to the actual pipeline branch: with a
    provider configured the way mitxonline/xpro's is (forced account
    creation), a mismatched-email `details` dict sends an existing user to
    /register instead of /login.
    """

    def setUp(self):
        super().setUp()
        self.existing_user = User.objects.create(username=EXISTING_USERNAME, email=EXISTING_EMAIL, is_active=True)

    def test_existing_user_is_sent_to_register(self):
        provider_mock = mock.MagicMock(send_to_registration_first=True, skip_email_verification=False)

        with mock.patch(
            'common.djangoapps.third_party_auth.pipeline.provider.Registry.get_from_pipeline',
            return_value=provider_mock,
        ), mock.patch('social_core.pipeline.partial.partial_prepare') as partial_prepare:
            partial_prepare.return_value = mock.MagicMock(token='')
            response = pipeline.ensure_user_information(
                strategy=mock.MagicMock(),
                backend=None,
                auth_entry=pipeline.AUTH_ENTRY_LOGIN,
                pipeline_index=0,
                user=None,
                social=None,
                details={'email': IDP_REPORTED_EMAIL, 'username': EXISTING_USERNAME},
            )

        assert response.status_code == 302
        assert response.url == '/register'


@skip_unless_lms
class RegistrationThenRejectsTheExistingAccountTest(OpenEdxEventsTestMixin, ThirdPartyAuthTestMixin,
                                                     UserAPITestCase, RetirementTestCase):
    """
    Completes the loop: having been sent to /register, the learner (or the
    auto-submitted SSO registration form) posts the same username the account
    already has. The registration endpoint IS careful about this and rejects
    it -- surfacing as "your account cannot be created" for someone who
    already has an account.
    """

    ENABLED_OPENEDX_EVENTS = []

    def setUp(self):
        super().setUp()
        self.url = reverse('user_api_registration')
        self.existing_user = User.objects.create(username=EXISTING_USERNAME, email=EXISTING_EMAIL, is_active=True)

    def test_registration_is_refused_for_the_already_existing_account(self):
        response = self.client.post(self.url, {
            'email': IDP_REPORTED_EMAIL,
            'name': 'CB Mit',
            'username': EXISTING_USERNAME,
            'password': 'irrelevant-password-1',
            'honor_code': 'true',
        })

        assert response.status_code == 409
        body = response.json()
        assert body['error_code'] == 'duplicate-username'
        assert body['username'][0]['user_message'] == AUTHN_USERNAME_CONFLICT_MSG
