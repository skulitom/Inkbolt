"""Measure original native clone/heal editing in fresh external workspaces."""
import sys
import measure_extra
import native_retouch_workload

if __name__ == '__main__':
    sys.exit(measure_extra.main(native_retouch_workload))
