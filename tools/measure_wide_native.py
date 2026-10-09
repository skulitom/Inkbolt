"""Measure the original wider native composition separately from scale-v1."""
import sys
import measure_extra
import wide_native_workload


if __name__ == "__main__":
    sys.exit(measure_extra.main(wide_native_workload))
