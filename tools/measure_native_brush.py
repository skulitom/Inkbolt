"""Measure original native brush editing in fresh external workspaces."""
import sys
import measure_extra
import native_brush_workload

if __name__ == '__main__':
    sys.exit(measure_extra.main(native_brush_workload))
