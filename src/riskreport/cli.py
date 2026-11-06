import argparse

EXIT = {"VALIDATED": 0, "WITH_RESERVATIONS": 1, "NOT_VALIDATED": 2, "CRASH": 3}


def main(argv=None):
    p = argparse.ArgumentParser(prog="riskreport", description="Daily market-risk reporting chain")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, h in [("run", "produce the report for a date"), ("check", "run the data-quality controls only"),
                    ("rerun", "replay an archived run and compare"), ("generate-demo", "write synthetic inputs")]:
        sub.add_parser(name, help=h)
    p.parse_args(argv)
