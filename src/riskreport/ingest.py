"""Reads the morning extractions with each source's CSV dialect and validates them against pandera schemas. Never raises on bad data:
problems are returned so the data-quality controls (C01, C02) can report them and the run can still produce a flagged workbook."""
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import pandera.pandas as pa

SOURCES = ["positions_fo", "positions_bo", "statics", "prices", "fx", "limits", "pnl_fo", "factor_history"]
TYPES = ["EQUITY", "FUTURE", "OPTION", "BOND", "FXCASH"]
DESKS = ["EQUITY", "RATES", "FX"]

_pos = pa.DataFrameSchema({"desk": pa.Column(str, pa.Check.isin(DESKS)), "book": pa.Column(str), "instrument": pa.Column(str),
                           "quantity": pa.Column(float, nullable=False, coerce=True)}, strict=True)
SCHEMAS = {
    "positions_fo": _pos,
    "positions_bo": _pos,
    "statics": pa.DataFrameSchema({"instrument": pa.Column(str, unique=True), "type": pa.Column(str, pa.Check.isin(TYPES)),
                                   "desk": pa.Column(str, pa.Check.isin(DESKS)), "factor": pa.Column(str), "ccy": pa.Column(str),
                                   "multiplier": pa.Column(float, pa.Check.gt(0), coerce=True),
                                   "iv": pa.Column(str, nullable=True, required=False),
                                   "strike": pa.Column(float, pa.Check.gt(0), nullable=True, required=False, coerce=True),
                                   "expiry": pa.Column(str, nullable=True, required=False),
                                   "right": pa.Column(str, pa.Check.isin(["C", "P"]), nullable=True, required=False),
                                   "coupon": pa.Column(float, pa.Check.ge(0), nullable=True, required=False, coerce=True),
                                   "maturity_years": pa.Column(float, pa.Check.gt(0), nullable=True, required=False, coerce=True),
                                   "country": pa.Column(str, nullable=True, required=False)}, strict=True),
    "pnl_fo": pa.DataFrameSchema({"desk": pa.Column(str, pa.Check.isin(DESKS)), "book": pa.Column(str), "instrument": pa.Column(str),
                                  "pnl": pa.Column(float, nullable=False, coerce=True)}, strict=True),
    "prices": pa.DataFrameSchema({"date": pa.Column(str), "instrument": pa.Column(str),
                                  "price": pa.Column(float, pa.Check.gt(0), coerce=True)}, strict=True),
    "fx": pa.DataFrameSchema({"date": pa.Column(str), "pair": pa.Column(str), "rate": pa.Column(float, pa.Check.gt(0), coerce=True)}, strict=True),
    "limits": pa.DataFrameSchema({"desk": pa.Column(str), "metric": pa.Column(str), "limit": pa.Column(float, pa.Check.gt(0), coerce=True)},
                                 strict=True),
}


@dataclass
class Inputs:
    asof: object
    cfg: dict
    folder: Path
    tables: dict = field(default_factory=dict)
    missing: list = field(default_factory=list)
    schema_errors: list = field(default_factory=list)  # (source, column, check, failure_case)


def load(folder, asof, cfg):
    folder = Path(folder)
    inp = Inputs(asof, cfg, folder)
    for name in SOURCES:
        f = folder / f"{name}.csv"
        if not f.exists():
            inp.missing.append(name)
            continue
        s = cfg["sources"][name]
        df = pd.read_csv(f, sep=s["sep"], decimal=s["decimal"], dtype={"date": str} if name != "factor_history" else None)
        if name == "factor_history":
            df = df.set_index("date")
        inp.tables[name] = df
        if name in SCHEMAS:
            try:
                SCHEMAS[name].validate(df, lazy=True)
            except pa.errors.SchemaErrors as e:
                for r in e.failure_cases.itertuples():
                    inp.schema_errors.append((name, str(r.column), str(r.check), str(r.failure_case)))
    return inp
