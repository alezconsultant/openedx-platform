"""
H1 validation: does send_notifications drop immediate-cadence emails for all
users except those in the LAST batch?

Scenario:
  - 5 users, each with an account preference: email=True, cadence=Immediately
    for notification type `new_response` (app `discussion`).
  - NOTIFICATION_CREATION_BATCH_SIZE forced to 2  ->  batches: [u0,u1] [u2,u3] [u4]
  - send_notifications is invoked once.

We mock ONLY the outward side effects (the actual email send, the analytics
event and the push fan-out). Everything else (preference lookup, per-batch
Notification bulk_create, the immediate-email user collection, and the refetch
by content_context uuid) runs for real against the DB.

If H1 is real, `send_immediate_cadence_email` receives a mapping containing only
the final batch's users instead of all 5.
"""
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from openedx.core.djangoapps.notifications import tasks as notifications_tasks
from openedx.core.djangoapps.notifications.models import NotificationPreference

User = get_user_model()

COURSE_KEY = "course-v1:edX+H1+2024"
APP = "discussion"
NTYPE = "new_response"
NUM_USERS = 5
BATCH_SIZE = 2


@override_settings(NOTIFICATION_CREATION_BATCH_SIZE=BATCH_SIZE)
class H1BatchEmailValidation(TestCase):
    """Validate the multi-batch immediate-email drop described in H1."""

    def setUp(self):
        super().setUp()
        self.users = []
        for i in range(NUM_USERS):
            user = User.objects.create(username=f"h1user{i}", email=f"h1user{i}@example.com")
            user.set_password("test")
            user.save()
            self.users.append(user)
            # Force immediate email cadence for this type (signal already made a row).
            NotificationPreference.objects.update_or_create(
                user=user,
                type=NTYPE,
                app=APP,
                defaults=dict(
                    web=True,
                    email=True,
                    push=False,
                    email_cadence="Immediately",
                    is_active=True,
                ),
            )

    def _run_send_notifications(self):
        context = {"replier_name": "Bob", "post_title": "Hello world"}
        with mock.patch.object(
            notifications_tasks.NotificationFilter,
            "apply_filters",
            side_effect=lambda user_ids, course_key, notification_type: list(user_ids),
        ), mock.patch.object(
            notifications_tasks, "send_immediate_cadence_email"
        ) as mock_send, mock.patch.object(
            notifications_tasks, "notification_generated_event"
        ), mock.patch.object(
            notifications_tasks, "send_ace_msg_to_push_channel"
        ):
            notifications_tasks.send_notifications(
                user_ids=[u.id for u in self.users],
                course_key=COURSE_KEY,
                app_name=APP,
                notification_type=NTYPE,
                context=dict(context),
                content_url="http://example.com/thread/1",
            )
        return mock_send

    def test_h1_immediate_email_batch_drop(self):
        mock_send = self._run_send_notifications()

        all_ids = sorted(u.id for u in self.users)
        last_batch_ids = sorted(u.id for u in self.users[-(NUM_USERS % BATCH_SIZE or BATCH_SIZE):])

        self.assertTrue(mock_send.called, "send_immediate_cadence_email was never called")
        mapping = mock_send.call_args.args[0]
        emailed_ids = sorted(mapping.keys())

        print("\n" + "=" * 60)
        print("H1 VALIDATION RESULT")
        print("=" * 60)
        print(f"Total immediate-cadence users : {len(all_ids)}  -> {all_ids}")
        print(f"Batch size                    : {BATCH_SIZE}")
        print(f"Users actually emailed        : {len(emailed_ids)} -> {emailed_ids}")
        print(f"(Last batch users only        : {last_batch_ids})")
        dropped = sorted(set(all_ids) - set(emailed_ids))
        print(f"Users silently DROPPED        : {len(dropped)} -> {dropped}")
        print("=" * 60)

        # Correct behaviour: every immediate-cadence user is emailed.
        self.assertEqual(
            emailed_ids,
            all_ids,
            f"H1 CONFIRMED: only {len(emailed_ids)} of {len(all_ids)} immediate-cadence "
            f"users were emailed; {len(dropped)} dropped (users {dropped}).",
        )
