"""Operation declarations, one module per area.

Every code path that changes a status runs one of these operations. Effects describe the current
behaviour, including known gaps (`gap=`); fixing a gap changes the declaration in the same commit.
"""
from . import create, request, receipt, lab, sequencing, release, worker, manual, system

MODULES = (create, request, receipt, lab, sequencing, release, worker, manual, system)
