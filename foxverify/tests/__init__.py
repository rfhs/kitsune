"""Unit tests for foxverify. No hardware, no network: every on-air and serial
path runs on fixtures under ``fixtures/``.

Run from the repo root: ``python3 -m unittest discover -s foxverify/tests -t .``
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "fixtures")
REPO = os.path.dirname(os.path.dirname(HERE))


def fixture(*parts):
    return os.path.join(FIXTURES, *parts)


def read_fixture(*parts):
    with open(fixture(*parts), "r", encoding="utf-8") as handle:
        return handle.read()


def project_header(project_dir, name="9999demo.h"):
    path = os.path.join(REPO, project_dir, "src", "conferences", name)
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()
