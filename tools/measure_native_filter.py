"""Measure the original native filter workload in fresh external workspaces."""
import sys
import measure_extra
import native_filter_workload

if __name__ == '__main__':
    sys.exit(measure_extra.main(native_filter_workload))
