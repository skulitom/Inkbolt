"""Measure a native image with 5,000 clipped annotations and retained edits."""
import sys
import measure_extra
import native_layout_workload


if __name__ == "__main__":
    sys.exit(measure_extra.main(native_layout_workload))
