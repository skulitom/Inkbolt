"""Create a retained model/baseline comparison in a new external directory."""
import argparse
from pathlib import Path
import sys

from benchmark_comparison import canonical,compare,digest,load_report,markdown


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-report',required=True,type=Path)
    parser.add_argument('--baseline-report',required=True,type=Path)
    parser.add_argument('--output-root',required=True,type=Path)
    args=parser.parse_args(argv);root=Path(__file__).resolve().parents[1];output=args.output_root.resolve()
    if output.is_relative_to(root) or output.exists() or not output.parent.is_dir():
        parser.error('Use a new external output directory under an existing parent')
    try:
        model=load_report(args.model_report,'model');baseline=load_report(args.baseline_report,'baseline')
        result=compare(model,baseline)
        result['comparison_code']={name:digest(Path(__file__).with_name(name).read_bytes())
            for name in ('compare_agent_benchmarks.py','benchmark_comparison.py','benchmark_tasks.py')}
        output.mkdir()
        with (output/'report.json').open('xb') as stream:stream.write(canonical(result)+b'\n')
        with (output/'summary.md').open('x',encoding='utf-8') as stream:stream.write(markdown(result))
    except (ValueError,KeyError,TypeError,OSError) as error:
        parser.error(str(error))
    print(output/'report.json')
    return 0 if not result['global_issues'] and any(row['minimum_repetitions_met'] for row in result['tasks']) else 2


if __name__=='__main__':sys.exit(main())
