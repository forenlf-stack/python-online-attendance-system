"""Spreadsheet-compatible CSV without executable formula cells."""
import csv
from io import StringIO


def csv_content(rows):
    def safe_cell(value):
        text = str(value) if value is not None else ""
        if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
            text = "'" + text
        return text

    output = StringIO(newline="")
    writer = csv.writer(output)
    for row in rows:
        writer.writerow([safe_cell(value) for value in row])
    return "\ufeff" + output.getvalue()
