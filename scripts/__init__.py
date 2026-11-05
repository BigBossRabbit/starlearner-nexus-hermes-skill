# scripts/ — the StarLearner-Nexus engine.
#
# This __init__.py makes the scripts directory a PACKAGE for the plugin
# mode (the plugin layer imports the engine under its own namespace,
# ``hermes_plugins.starlearner_nexus.scripts.*``, via _engine.py's
# spec-from-file-location imports). It has ZERO effect on the standalone:
# ``python3 scripts/<x>.py`` and the shell pipeline never import the
# package, and an empty __init__ changes nothing about script execution.
