"""
Module to put all pytest hooks that modify pytest behaviour
"""
import io  # pylint: disable=unused-import  # noqa: F401
import json
import os
import sys


def pytest_json_modifyreport(json_report):
    """
    - The function is called by pytest-json-report plugin to only output warnings in json format.
    - Everything else is removed due to it already being saved by junitxml
    - --json-omit flag in does not allow us to remove everything but the warnings
    - (the environment metadata is one example of unremoveable data)
    - The json warning outputs are meant to be read by jenkins
    """
    warnings_flag = "warnings"
    if warnings_flag in json_report:
        warnings = json_report[warnings_flag]
        json_report.clear()
        json_report[warnings_flag] = warnings
    else:
        json_report = {}
    return json_report


def create_file_name(dir_path, file_name_postfix, num=0):
    """
    Used to create file name with this given
    structure: TEST_SUITE + "_" + file_name_postfix + "_ " + num.json
    The env variable TEST_SUITE is set in jenkinsfile

    This was necessary cause Pytest is run multiple times and we need to make sure old pytest
    warning json files are not being overwritten.
    """
    name = dir_path + "/"
    if "TEST_SUITE" in os.environ:
        name += os.environ["TEST_SUITE"] + "_"
    name += file_name_postfix
    if num != 0:
        name += "_" + str(num)
    return name + ".json"


def pytest_sessionfinish(session):
    """
    Since multiple pytests are running,
    this makes sure warnings from different run are not overwritten
    """
    # Under pytest-xdist this hook fires on every worker as well as on the
    # controller. Only the controller holds the aggregated report, so the
    # workers bail out here; otherwise they race each other for the next free
    # file name and leave behind partial files that the warning report job
    # would then double-count.
    if os.environ.get("PYTEST_XDIST_WORKER"):
        return

    dir_path = "test_root/log"
    file_name_postfix = "pytest_warnings"
    num = 0
    # to make sure this doesn't loop forever, putting a maximum
    while (
        os.path.isfile(create_file_name(dir_path, file_name_postfix, num)) and num < 100
    ):
        num += 1

    report = session.config._json_report.report  # noqa pylint: disable=protected-access

    with open(create_file_name(dir_path, file_name_postfix, num), "w") as outfile:
        json.dump(report, outfile)


class DeferPlugin:
    """Simple plugin to defer pytest-xdist hook functions."""

    def pytest_json_modifyreport(self, json_report):
        """standard xdist hook function.
        """
        return pytest_json_modifyreport(json_report)

    def pytest_sessionfinish(self, session):
        return pytest_sessionfinish(session)


def pytest_configure(config):
    if config.pluginmanager.hasplugin("pytest_jsonreport") or config.pluginmanager.hasplugin("json-report"):
        config.pluginmanager.register(DeferPlugin())

# --- temporary diagnostic -------------------------------------------------
# Something removes settings.CONTENTSTORE from the base Settings object partway
# through a run (transiently -- it comes back), which breaks any test that reads
# it, including plain TestCases like SandboxServiceTest that call contentstore().
# The attribute is gone from the base object's own __dict__ while the object's
# identity is unchanged, so it is a delete rather than a settings reload. This
# traces the delete to its caller. Remove once the cause is fixed.

_DELETION_TRACER_INSTALLED = False


def install_settings_deletion_tracer(*names):
    """Log a stack trace whenever one of `names` is deleted off a settings object."""
    global _DELETION_TRACER_INSTALLED  # noqa: PLW0603
    if _DELETION_TRACER_INSTALLED:
        return
    _DELETION_TRACER_INSTALLED = True

    import sys  # pylint: disable=import-outside-toplevel
    import traceback  # pylint: disable=import-outside-toplevel

    from django.conf import Settings, UserSettingsHolder  # pylint: disable=import-outside-toplevel

    watched = set(names)

    def _wrap(owner, original):
        def __delattr__(self, name):  # noqa: N807
            if name in watched:
                sys.stderr.write(
                    f"\n=== SETTINGS-DELETE {name} on {owner.__name__} id={id(self):#x} "
                    f"test={os.environ.get('PYTEST_CURRENT_TEST', '?')} ===\n"
                    + "".join(traceback.format_stack()[-14:-1])
                    + "=== end SETTINGS-DELETE ===\n"
                )
                sys.stderr.flush()
            return original(self, name)
        return __delattr__

    Settings.__delattr__ = _wrap(Settings, Settings.__delattr__)
    UserSettingsHolder.__delattr__ = _wrap(UserSettingsHolder, UserSettingsHolder.__delattr__)

    # Record where each holder was created. A leaked override frame is only
    # actionable if we can name the override_settings call that made it, and the
    # holder itself carries no such information. sys._getframe rather than
    # traceback.extract_stack because this runs on every override in the suite.
    original_init = UserSettingsHolder.__init__

    def _tracking_init(self, default_settings):
        original_init(self, default_settings)
        origin = "?"
        try:
            frame = sys._getframe(1)  # noqa: SLF001  # pylint: disable=protected-access
            for _ in range(15):
                if frame is None:
                    break
                filename = frame.f_code.co_filename
                if "/django/" not in filename:
                    origin = f"{'/'.join(filename.rsplit('/', 3)[-3:])}:{frame.f_lineno}"
                    break
                frame = frame.f_back
        except Exception:  # pylint: disable=broad-except  # noqa: BLE001
            pass
        self.__dict__["_created_by"] = origin

    UserSettingsHolder.__init__ = _tracking_init

    sys.stderr.write(f"=== SETTINGS-DELETE tracer installed for {sorted(watched)} ===\n")
    sys.stderr.flush()
