"""Measure the original native shadow workload in fresh external workspaces."""
import sys
import measure_extra
import native_shadow_workload

if __name__ == '__main__':
    sys.exit(measure_extra.main(native_shadow_workload))
