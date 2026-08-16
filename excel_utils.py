"""Excel template parsing and write-back helpers."""

from platform_config import NUMERIC_FIELDS


def find_data_sheet(wb):
    for name in wb.sheetnames:
        if "fill" in name.lower():
            return wb[name]
    return wb[wb.sheetnames[1]] if len(wb.sheetnames) > 1 else wb[wb.sheetnames[0]]


def find_header_row(ws):
    for r in range(1, 10):
        v = ws.cell(row=r, column=1).value
        if v and "Fields + Description" in str(v):
            return r
    for r in range(1, 10):
        for c in range(1, 60):
            v = ws.cell(row=r, column=c).value
            if v and "Product Name" in str(v) and len(str(v)) > 30:
                return r
    for r in range(1, 10):
        v = ws.cell(row=r, column=1).value
        if v and str(v).strip() == "Field Names":
            return r + 1
    return 3


def find_data_start(ws, hdr):
    start = hdr + 1
    for r in range(hdr + 1, hdr + 5):
        skip = False
        for c in range(1, 10):
            v = ws.cell(row=r, column=c).value
            if v and ("Tutorial" in str(v) or "Watch" in str(v) or
                      "Validation Sheet" in str(v) or len(str(v)) > 200):
                skip = True
                break
        if skip:
            start = r + 1
        else:
            break
    return start


def get_col_map(ws, hdr):
    m = {}
    for c in range(1, ws.max_column + 1):
        v = ws.cell(row=hdr, column=c).value
        if v:
            for line in str(v).split("\n"):
                s = line.strip()
                if s and s not in (
                    "Fields + Description:",
                    "Field Names",
                    "Field Type (Compulsory, Recommended, System_Use) ->",
                ):
                    m[s] = c
                    break
    return m


def get_compulsory(ws, hdr, col_map):
    comp = set()
    for mr in [hdr - 1, hdr - 2]:
        if mr < 1:
            continue
        found = False
        for fn, ci in col_map.items():
            v = ws.cell(row=mr, column=ci).value
            if v and "Compulsory" in str(v):
                comp.add(fn)
                found = True
        if found:
            break
    return comp


def get_dropdowns(wb, col_map):
    dd = {}
    vs = None
    for name in wb.sheetnames:
        if "validation" in name.lower():
            vs = wb[name]
            break
    if not vs:
        return dd
    vhr = 1
    for r in range(1, 5):
        v = vs.cell(row=r, column=1).value
        if v and ("Field Type" in str(v) or "Field Names" in str(v)):
            vhr = r
            break
    vcm = {}
    for c in range(1, vs.max_column + 1):
        v = vs.cell(row=vhr, column=c).value
        if v and str(v).strip() in col_map:
            vcm[str(v).strip()] = c
    ds = vhr + 1
    chk = vs.cell(row=ds, column=1).value
    if chk and "Field Names" in str(chk):
        ds += 1
    for fn, ci in vcm.items():
        vals = []
        for r in range(ds, min(ds + 300, vs.max_row + 1)):
            v = vs.cell(row=r, column=ci).value
            if v:
                vals.append(str(v).strip())
        if vals:
            dd[fn] = vals
    return dd


def inject_data(wb, rows):
    ws = find_data_sheet(wb)
    hdr = find_header_row(ws)
    cm = get_col_map(ws, hdr)
    start = find_data_start(ws, hdr)
    for r in range(start, start + len(rows) + 100):
        for c in range(1, ws.max_column + 1):
            ws.cell(row=r, column=c).value = None
    for i, row in enumerate(rows):
        for fn, val in row.items():
            if fn not in cm:
                continue
            if fn in NUMERIC_FIELDS and val is not None and str(val).strip():
                try:
                    num_val = float(str(val).strip())
                    ws.cell(row=start + i, column=cm[fn]).value = (
                        int(num_val) if num_val == int(num_val) else num_val
                    )
                except (ValueError, TypeError):
                    ws.cell(row=start + i, column=cm[fn]).value = val
            else:
                ws.cell(row=start + i, column=cm[fn]).value = val
