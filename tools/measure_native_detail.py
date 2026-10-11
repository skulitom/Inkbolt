"""Measure original native detail edits in fresh external workspaces."""
import sys
import measure_extra
import native_detail_workload

if __name__=='__main__':
    sys.exit(measure_extra.main(native_detail_workload))
