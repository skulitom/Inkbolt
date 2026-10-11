"""Measure original native radial edits in fresh external workspaces."""
import sys
import measure_extra
import native_nonlocal_workload

if __name__=='__main__':
    sys.exit(measure_extra.main(native_nonlocal_workload))
