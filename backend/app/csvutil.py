import csv
import io

_DANGEROUS = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value) -> str:
    """Neutralise spreadsheet formula injection: a cell starting with = + - @ would be executed by Excel."""
    s = "" if value is None else str(value)
    return "'" + s if s.startswith(_DANGEROUS) else s


def to_csv(header: list[str], rows) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(header)
    for r in rows:
        w.writerow([csv_safe(c) for c in r])
    return buf.getvalue()
