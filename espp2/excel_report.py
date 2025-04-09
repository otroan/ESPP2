"""
Generates Excel reports for the ESPP portfolio.
"""

import logging
from io import BytesIO
from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from datetime import date
from espp2 import __version__
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    # Avoid circular import, Portfolio needs this module
    from espp2.portfolio import Portfolio
    # Type hints for data structures used
    # from espp2.positions import Ledger # If needed

logger = logging.getLogger(__name__)

# --- Helper Functions ---


def format_cells(ws, column_letter: str, number_format: str):
    """Sets the number format for all cells in a given column (skipping header row 1 & 2)."""
    # Assumes headers are in row 1/2, data starts row 3.
    if column_letter in ws.column_dimensions:
        for row in range(3, ws.max_row + 1):
            try:  # Protect against potential errors on merged/empty cells
                ws[f"{column_letter}{row}"].number_format = number_format
            except AttributeError:
                logger.debug(f"Could not format cell {column_letter}{row}")


def format_fill_columns(ws, headers: List[str], columns: List[str], color: str):
    """Applies a fill color to specified columns based on header names."""
    header_to_letter = {
        header: get_column_letter(i + 1) for i, header in enumerate(headers)
    }
    cols_to_fill = [
        header_to_letter[header] for header in columns if header in header_to_letter
    ]
    fill = PatternFill(start_color=color, end_color=color, fill_type="solid")
    data_end_row = ws.max_row  # Assume total row is calculated later
    for col_letter in cols_to_fill:
        # Apply fill to the header row (assuming row 2)
        if ws[f"{col_letter}2"].value in columns:  # Only fill if it's a target header
            ws[f"{col_letter}2"].fill = fill
        # Apply fill to data rows (assuming starting row 3)
        for row in range(3, data_end_row + 1):
            cell = ws[f"{col_letter}{row}"]
            # Check if cell belongs to a data row (not total or disclaimer)
            if cell.value is not None and not str(ws[f"A{row}"].value).startswith(
                "Total"
            ):
                cell.fill = fill


def adjust_width(ws):
    """Adjusts column width to fit the longest value in each column, including header."""

    def as_text(value):
        if value is None:
            return ""
        # Handle date objects specifically for length calculation
        if isinstance(value, date):
            return value.isoformat()  # YYYY-MM-DD format
        return str(value)

    for col_idx in range(1, ws.max_column + 1):
        column_letter = get_column_letter(col_idx)
        max_length = 0
        for row in range(1, ws.max_row + 1):
            cell = ws.cell(row=row, column=col_idx)
            try:
                cell_value_str = as_text(cell.value)
                # Handle potential formulas by checking calculated value if available
                # This part might need refinement depending on openpyxl version/behavior
                # if cell.data_type == 'f':
                #    # Attempt to get calculated value length, fallback to formula length
                #    try: cell_value_str = as_text(cell.internal_value) # Or check cell._value
                #    except: pass
                cell_len = len(cell_value_str)
                if cell_len > max_length:
                    max_length = cell_len
            except Exception as e:
                logger.debug(f"Could not get length for cell {column_letter}{row}: {e}")
                pass

        adjusted_width = max_length + 1.5  # Add padding
        if adjusted_width < 8:  # Minimum width
            adjusted_width = 8
        ws.column_dimensions[column_letter].width = adjusted_width


def index_to_cell(row: int, column_index: int) -> str:
    """
    Convert a 1-based row and 0-based column index to an Excel cell reference.
    """
    if column_index < 0:
        raise ValueError("Column index cannot be negative")
    column_letter = get_column_letter(column_index + 1)
    return f"{column_letter}{row}"


# --- Main Excel Report Generation Function ---


def generate_workbook(portfolio: "Portfolio") -> BytesIO:
    """Generates the full Excel workbook for the portfolio."""
    year = portfolio.year
    positions = portfolio.positions
    column_headers = portfolio.column_headers
    workbook = Workbook()

    # --- Portfolio Sheet ---
    ws = workbook.active
    ws.title = f"Portfolio-{year}"
    disclaimer = (
        "Disclaimer: This tool is provided as is, without warranty of any kind. "
        "Use of this tool is at your own risk. The authors or distributors "
        "are not responsible for any losses, damages, or issues that may arise "
        "from using this tool. Always consult with a professional financial advisor "
        "before making any financial decisions. "
        f"This report is generated with the espp2 tool version: {__version__} on {date.today().isoformat()}"
    )

    # Merged Title Rows (Row 1)
    ws.merge_cells("J1:M1")  # Dividends title span
    ws["J1"] = "Dividends"
    ws["J1"].font = Font(bold=True)
    ws["J1"].alignment = Alignment(horizontal="center", vertical="center")
    ws.merge_cells("N1:Q1")  # Tax Deduction title span
    ws["N1"] = "Deductible Risk-free return"
    ws["N1"].font = Font(bold=True)
    ws["N1"].alignment = Alignment(horizontal="center", vertical="center")
    # Assuming 'Sales' columns might be R through W (adjust if needed)
    last_sales_col = (
        get_column_letter(column_headers.index("Amount USD") + 1)
        if "Amount USD" in column_headers
        else "W"
    )
    ws.merge_cells(f"R1:{last_sales_col}1")
    ws["R1"] = "Sales"
    ws["R1"].font = Font(bold=True)
    ws["R1"].alignment = Alignment(horizontal="center", vertical="center")

    # Column Headers (Row 2)
    ws.append(column_headers)  # Appends to row 2
    header_row_idx = 2
    for cell in ws[header_row_idx]:
        cell.font = Font(bold=True)

    # Write data from PortfolioPosition instances and their records
    data_start_row = 3
    current_row = data_start_row
    for stock_position in positions:
        # Use the format method from the position object itself
        cells_to_write = stock_position.format(current_row, column_headers)
        for r, col_idx, value in cells_to_write:
            ws.cell(row=r, column=col_idx + 1, value=value)
        current_row += 1  # Move to next row for records

        for record in stock_position.records:
            record_cells = record.format(current_row, column_headers)
            for r, col_idx, value in record_cells:
                ws.cell(row=r, column=col_idx + 1, value=value)
            current_row += 1  # Move to next row

    # Create header to column letter mapping
    header_to_letter = {
        header: get_column_letter(i + 1) for i, header in enumerate(column_headers)
    }

    # --- Formatting Portfolio Sheet ---
    num_columns_2dp = [
        "Price",
        "Price USD",
        "Gain",
        "Gain PS",
        "Gain USD",
        "Amount",
        "Amount USD",
        "Div PS",
        "Div PS USD",
        "Total Dividend",
        "Total Dividend USD",
        "Exchange Rate",
        "Accumulated",
        "Added",
        "Used",
        "TD Total",
    ]
    num_cols_2dp_letters = [
        header_to_letter[h] for h in num_columns_2dp if h in header_to_letter
    ]
    for col_letter in num_cols_2dp_letters:
        format_cells(ws, col_letter, "0.00")

    num_columns_4dp = ["pQty", "Qty", "iQty"]
    num_cols_4dp_letters = [
        header_to_letter[h] for h in num_columns_4dp if h in header_to_letter
    ]
    for col_letter in num_cols_4dp_letters:
        format_cells(ws, col_letter, "0.0000")

    # Freeze Panes (freeze rows 1 and 2)
    ws.freeze_panes = ws["A3"]

    # Sum Totals row (calculate index based on current_row)
    total_row_idx = current_row  # The row after the last data row
    sum_columns = [
        # "Qty", # Summing current Qty might not be meaningful if there are splits/transfers
        "Gain",
        "Gain USD",
        "Amount",
        "Amount USD",
        "Total Dividend",
        "Total Dividend USD",
        "TD Total",
    ]
    sum_cols_letters = [
        header_to_letter[h] for h in sum_columns if h in header_to_letter
    ]

    ws[f"A{total_row_idx}"] = "Total"
    ws[f"A{total_row_idx}"].font = Font(bold=True)

    for col_letter in sum_cols_letters:
        # Sum from data start row up to the last data row (total_row_idx - 1)
        formula = f"=SUM({col_letter}{data_start_row}:{col_letter}{total_row_idx - 1})"
        cell = ws[f"{col_letter}{total_row_idx}"]
        cell.value = formula
        cell.font = Font(bold=True)
        cell.number_format = "0.00"

    # Format columns with fill colors (pass headers list for mapping)
    format_fill_columns(
        ws,
        column_headers,
        ["Div PS", "Div PS USD", "Total Dividend", "Total Dividend USD"],
        "CAD8EE",
    )
    format_fill_columns(
        ws,
        column_headers,
        ["Gain PS", "Gain PS USD", "Gain", "Gain USD", "Amount", "Amount USD"],
        "90ADD7",
    )
    format_fill_columns(
        ws, column_headers, ["Accumulated", "Added", "TD Total", "Used"], "618CCE"
    )

    # Apply conditional formatting for negative numbers (red font)
    # Apply to the data range, excluding totals row
    data_range = (
        f"A{data_start_row}:{get_column_letter(len(column_headers))}{total_row_idx - 1}"
    )
    # Ensure rule doesn't stop other rules if needed later
    ws.conditional_formatting.add(
        data_range,
        CellIsRule(
            operator="lessThan",
            formula=["0"],
            stopIfTrue=False,
            font=Font(color="00FF0000"),
        ),
    )

    # Adjust width after all data and formatting applied to main sheet
    adjust_width(ws)

    # Write the disclaimer below the totals
    disclaimer_row_idx = total_row_idx + 4  # Add some space
    ws[f"A{disclaimer_row_idx}"] = disclaimer
    ws[f"A{disclaimer_row_idx}"].alignment = Alignment(wrapText=True)
    # Optional: Merge cells for the disclaimer to make it span wider
    # end_col_letter = get_column_letter(min(5, len(column_headers))) # Span first 5 cols or less
    # ws.merge_cells(start_row=disclaimer_row_idx, start_column=1, end_row=disclaimer_row_idx + 2, end_column=min(5, len(column_headers)))

    # --- Cash Sheet ---
    ws_cash = workbook.create_sheet("Cash")
    cash_headers = [
        "Date",
        "Description",
        "Amount NOK",
        "Amount Base",
        "Currency",
        "Balance NOK",
    ]
    ws_cash.append(cash_headers)
    ws_cash.freeze_panes = ws_cash["A2"]
    for cell in ws_cash[1]:  # Bold headers
        cell.font = Font(bold=True)

    # Assuming portfolio.cash_ledger is List[Tuple[CashEntry, Decimal]]
    for entry, balance_nok in portfolio.cash_ledger:
        nok_value = entry.amount.nok_value
        ws_cash.append(
            [
                entry.date,
                entry.description,
                round(nok_value, 2) if nok_value is not None else "N/A",
                round(entry.amount.value, 2),
                entry.amount.currency,
                round(balance_nok, 2),
            ]
        )

    # Formatting for Cash sheet
    format_cells(ws_cash, "C", "0.00")  # Amount NOK
    format_cells(ws_cash, "D", "0.00")  # Amount Base
    format_cells(ws_cash, "F", "0.00")  # Balance NOK
    adjust_width(ws_cash)

    # --- EOY Holdings Sheet ---
    ws_eoy = workbook.create_sheet("EOY Holdings")
    eoy_headers = [
        "Symbol",
        "Purchase Date",
        "Qty",
        "Purchase Price NOK",
        "Available Tax Deduction (Skjerming) NOK",
    ]
    ws_eoy.append(eoy_headers)
    ws_eoy.freeze_panes = ws_eoy["A2"]
    for cell in ws_eoy[1]:  # Bold headers
        cell.font = Font(bold=True)

    # Assuming portfolio.eoy_holdings is Holdings model
    if portfolio.eoy_holdings and portfolio.eoy_holdings.stocks:
        for h in portfolio.eoy_holdings.stocks:
            # Need to ensure purchase_price Amount object exists and has nok_value calculated
            purchase_nok = None
            try:
                purchase_nok = h.purchase_price.nok_value
            except Exception as e:  # Catch potential errors if nok_value isn't computed
                logger.warning(
                    f"Could not get NOK purchase price for holding {h.symbol} {h.date}: {e}"
                )

            ws_eoy.append(
                [
                    h.symbol,
                    h.date,
                    round(h.qty, 4),
                    round(purchase_nok, 2) if purchase_nok is not None else "N/A",
                    round(
                        h.tax_deduction, 2
                    ),  # This is the remaining/available deduction for this lot
                ]
            )

    # Formatting for EOY Holdings sheet
    format_cells(ws_eoy, "C", "0.0000")  # Qty
    format_cells(ws_eoy, "D", "0.00")  # Purchase Price NOK
    format_cells(ws_eoy, "E", "0.00")  # Tax Deduction NOK
    adjust_width(ws_eoy)

    # --- Save workbook to buffer ---
    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()
