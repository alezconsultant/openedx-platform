"""
Reproduction for mitodl/hq#12620.

Legacy ``/assets/courseware/<version>/<digest>/asset-v1:<course>+type@asset+block/<name>``
URLs persisted in OLX embed a specific course run. The contentserver resolves the
embedded asset key literally, so the URL only works while *that* course exists in
the same contentstore. A re-run or a migration to a different instance leaves the
URL pointing at a course that isn't there, and the asset 404s.

``/static/<name>`` does not have this problem: ``replace_static_urls`` rebases it
onto the course being rendered at request time.
"""

import copy
from uuid import uuid4

from django.conf import settings
from django.test.client import Client
from django.test.utils import override_settings
from opaque_keys.edx.keys import CourseKey

from common.djangoapps.static_replace import replace_static_urls
from common.djangoapps.student.tests.factories import AdminFactory
from xmodule.contentstore.content import StaticContent
from xmodule.contentstore.django import contentstore
from xmodule.modulestore.tests.django_utils import TEST_DATA_SPLIT_MODULESTORE, SharedModuleStoreTestCase
from xmodule.modulestore.tests.factories import CourseFactory

TEST_DATA_CONTENTSTORE = copy.deepcopy(settings.CONTENTSTORE)
TEST_DATA_CONTENTSTORE['DOC_STORE_CONFIG']['db'] = 'test_xcontent_%s' % uuid4().hex  # noqa: UP031

ASSET_NAME = 'Screen_Shot_2017-05-23_at_2.23.39_PM.jpg'
ASSET_BODY = b'\xff\xd8\xff\xe0 not-really-a-jpeg'

# The run whose key is baked into the OLX. Never created in this test -- it stands
# in for a course that lives on edx.org but was not migrated to courses.learn.
STALE_COURSE_KEY = CourseKey.from_string('course-v1:MITx+CTL.SC0x+2T2023')


@override_settings(CONTENTSTORE=TEST_DATA_CONTENTSTORE)
class LegacyCoursewareAssetUrlTest(SharedModuleStoreTestCase):
    """
    Exercises the contentserver with a legacy versioned asset URL whose embedded
    course key is not the course being rendered.
    """

    MODULESTORE = TEST_DATA_SPLIT_MODULESTORE

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # The current run. Assets were carried forward into it, as they are on a re-run.
        cls.course = CourseFactory.create(org='MITxT', number='CTL.SC0x', run='2T2026')
        cls.course_key = cls.course.id

        cls.asset_key = cls.course_key.make_asset_key('asset', ASSET_NAME)
        contentstore().save(
            StaticContent(cls.asset_key, ASSET_NAME, 'image/jpeg', ASSET_BODY)
        )
        cls.digest = contentstore().find(cls.asset_key).content_digest

    def setUp(self):
        super().setUp()
        self.client = Client()
        self.client.login(username=AdminFactory.create().username, password='test')

    @staticmethod
    def legacy_url(course_key, digest):
        """
        Build the OLX-persisted URL shape: a versioned /assets/courseware/ path
        wrapping a canonical asset key, with `block/` rather than `block@`.
        """
        path = StaticContent.add_version_to_asset_path(
            '/' + str(course_key.make_asset_key('asset', ASSET_NAME)), digest
        )
        return path.replace('block@', 'block/', 1)

    def test_asset_is_present_in_the_current_run(self):
        """Control: the file itself was carried forward and is served fine."""
        response = self.client.get('/' + str(self.asset_key))
        assert response.status_code == 200
        assert response['Content-Type'] == 'image/jpeg'

    def test_legacy_url_for_this_course_is_served(self):
        """
        Control: the legacy URL shape is still supported. When the embedded course
        key is a course that exists here, it resolves -- this is edx.org today.
        """
        response = self.client.get(self.legacy_url(self.course_key, self.digest))
        assert response.status_code == 200
        assert response['Content-Type'] == 'image/jpeg'

    def test_legacy_url_for_a_missing_course_is_not_found(self):
        """
        The bug. Identical URL shape, identical filename, and the file *is* in the
        contentstore under the current run -- but the OLX names the 2T2023 run,
        which does not exist here, so the lookup fails.
        """
        url = self.legacy_url(STALE_COURSE_KEY, self.digest)
        assert 'MITx+CTL.SC0x+2T2023' in url

        response = self.client.get(url)
        assert response.status_code == 404

    def test_static_url_is_rebased_onto_the_current_course(self):
        """
        The fix. /static/ is resolved against the course being rendered, so it
        reaches the asset that the legacy URL missed.
        """
        rewritten = replace_static_urls(
            f'<img src="/static/{ASSET_NAME}"/>', course_id=self.course_key
        )
        # Note the output shape: /static/ is expanded into exactly the legacy
        # /assets/courseware/<version>/<digest>/asset-v1:... form, but bound to the
        # *current* course. This is how these URLs ended up in OLX in the first
        # place -- rendered output copied back into the source.
        assert str(self.asset_key).replace('block@', 'block/') in rewritten
        assert 'MITx+CTL.SC0x+2T2023' not in rewritten

        src = rewritten.split('src="')[1].split('"')[0]
        response = self.client.get(src)
        assert response.status_code == 200
        assert response['Content-Type'] == 'image/jpeg'

    def test_static_replace_never_touches_legacy_urls(self):
        """
        Why no amount of link-rewriting would have saved this: the regex in
        process_static_urls only anchors on STATIC_URL or /static/, so a stored
        /assets/courseware/ URL is passed through to the browser verbatim.
        """
        legacy = self.legacy_url(STALE_COURSE_KEY, self.digest)
        html = f'<img src="{legacy}"/>'

        assert replace_static_urls(html, course_id=self.course_key) == html
