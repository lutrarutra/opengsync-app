import string

from openpyxl.styles import Font, PatternFill, Alignment, Side, Border
from openpyxl.worksheet.worksheet import Worksheet
from openpyxl.cell import Cell, MergedCell

def extract_style(cell: Cell | MergedCell) -> dict:
    """Extract cell style and convert to Univer format"""
    style = {}
    font = cell.font
    fill = cell.fill
    border = cell.border
    alignment = cell.alignment
    
    # Font family (ff)
    if font and font.name:
        style["ff"] = font.name
    
    # Font size (fs)
    if font and font.size:
        style["fs"] = int(font.size)
    
    # Italic (it)
    if font and font.italic:
        style["it"] = 1
    
    # Bold (bl)
    if font and font.b:
        style["bl"] = 1
    
    # Underline (ul)
    if font and font.underline and font.underline != "none":
        style["ul"] = 1
    
    # Strikethrough (st)
    if font and font.strike:
        style["st"] = 1
    
    # Superscript/subscript (va)
    # openpyxl doesn't directly support this, so skip
    
    # Text rotation (tr)
    if alignment and alignment.text_rotation:
        style["tr"] = int(alignment.text_rotation)
    
    # Horizontal alignment (ht)
    if alignment and alignment.horizontal:
        # Map openpyxl values to Univer format
        ht_map = {
            "left": "left",
            "center": "center", 
            "right": "right",
            "justify": "justify",
            "fill": "fill",
            "distributed": "distributed"
        }
        if alignment.horizontal in ht_map:
            style["ht"] = ht_map[alignment.horizontal]
    
    # Vertical alignment (vt)
    if alignment and alignment.vertical:
        # Map openpyxl values to Univer format
        vt_map = {
            "top": "top",
            "center": "middle",
            "bottom": "bottom",
            "justify": "justify",
            "distributed": "distributed"
        }
        if alignment.vertical in vt_map:
            style["vt"] = vt_map[alignment.vertical]
    
    # Truncate overflow (tb) - not directly supported in openpyxl
    # This relates to text wrapping, so we can infer from wrap_text
    if alignment and alignment.wrap_text is False:
        style["tb"] = 1  # truncate if not wrapping
    
    # Padding (pd) - not directly supported in openpyxl, skip
    
    # Number format (n)
    if cell.number_format and cell.number_format != "General":
        style["n"] = cell.number_format
    
    return style


def xlsx_to_univer_snapshot(path: str) -> tuple[dict, dict]:
    from openpyxl import load_workbook

    wb = load_workbook(path, data_only=True)
    snapshot = {
        "id": "workbook",
        "name": "Workbook",
        "sheetOrder": wb.sheetnames,
        "sheets": {},
    }
    col_style = {}

    for col_idx, sheet in enumerate(wb.sheetnames):
        ws: Worksheet = wb[sheet]
        snapshot["sheets"][sheet] = {
            "id": sheet,
            "name": sheet,
            "cellData": {}, # (row, col)
        }
        sheet_col_style = {}
        for col_idx, letter in enumerate(list(ws.column_dimensions)):
            sheet_col_style[col_idx] = { "width": ws.column_dimensions[letter].width * 7.5 if ws.column_dimensions[letter].width else 64 }
        
        col_style[sheet] = sheet_col_style
            
        for row_idx, row in enumerate(ws.iter_rows()):
            row_data = {}
            for cell_idx, cell in enumerate(row):
                row_data[cell_idx] = {
                    "v": cell.value or "",
                    "s": extract_style(cell)
                }

            snapshot["sheets"][sheet]["cellData"][row_idx] = row_data


    return snapshot, col_style