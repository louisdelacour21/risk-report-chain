"""Factor naming conventions shared by the report and the synthetic generator."""
import re

EQ = [f"EQ{i}" for i in range(1, 9)]
OPT_UND = EQ[:4]
IV = [f"IV_{u}" for u in OPT_UND]
FX = ["EURUSD", "EURGBP", "EURJPY"]
YLD = ["DE2Y", "DE5Y", "DE10Y", "FR10Y", "IT10Y"]
FACTORS = EQ + ["IDX"] + FX + YLD + IV


def kind(f):
    """logret: equity, index, fx (log return); bp: yield in % (change in bp); volpt: implied vol level (change in vol points)."""
    if f.startswith("IV_"):
        return "volpt"
    return "bp" if re.fullmatch(r"(DE|FR|IT)\d+Y", f) else "logret"
