"""Shared code for the per-project ``verify`` scripts.

A verify script proves that a flashed fox transmits what ``src/current_conf.h``
says. The modules split the work:

- ``conf``: parses a conference header and picks the block the fox was built from.
- ``devices``: classifies and autodetects the fox, the sniffer and the adapters.
- ``serial_fox``: resets the fox, waits for its banner and parses its readback.
- ``report``: the result table, the one deadline for the run and the exit codes.
- ``privileges``: the tool and privilege checks made before a radio is touched.
- ``tshark``, ``wifi``, ``zigbee``, ``ble``, ``btclassic``: the on-air checks.
- ``run``: the command line and the steps of one run, per project; the
  ``verify`` scripts call ``run.main(project)``.

Nothing is imported here so that ``python3 -m foxverify.conf`` works on a
machine without pyserial.
"""
