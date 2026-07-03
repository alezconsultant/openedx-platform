"""Helper functions for drf-spectacular"""

import re


def cms_api_filter(endpoints):
    """
    Pre-processing hook: keep only contentstore versioned endpoints and select
    course-level endpoints.
    """
    filtered = []
    CMS_PATH_PATTERN = re.compile(r"^/api/contentstore/v\d+/")
    ENROLLMENT_PATH_PATTERN = re.compile(r"^/api/enrollment/v\d+/")

    for path, path_regex, method, callback in endpoints:
        if (
            CMS_PATH_PATTERN.match(path)
            or ENROLLMENT_PATH_PATTERN.match(path)
            or (
                path.startswith("/api/courses/")
                and "bulk_enable_disable_discussions" in path
            )
        ):
            filtered.append((path, path_regex, method, callback))

    return filtered
