"""This copy's version. A release on GitHub is tagged v<VERSION> (see
.github/workflows/release.yml, which refuses a tag that doesn't match), and
the updater (updater.py) offers any release newer than this."""
VERSION = "0.2.6"
# The bundled Python + libraries of the full package (tools/build_full.py).
# Raise it when requirements.txt changes: copies whose runtime/RUNTIME_VERSION
# is older are told to download the full package again instead of updating.
RUNTIME = 1
