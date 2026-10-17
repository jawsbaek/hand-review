"""analyze.py 결과를 보여주는 textual TUI. `uv run analyze.py tui ...`로 실행."""

from textual.app import App, ComposeResult
from textual.widgets import DataTable, Footer, Header, Static, TabbedContent, TabPane

HAND_COLUMNS = ("player", "hands", "net bb", "bb/100", "EV bb/100", "VPIP", "PFR", "3Bet")


class HandsTable(DataTable):
    def __init__(self, rows):
        super().__init__()
        self._rows = rows
        self._sort_col, self._reverse = None, False

    def on_mount(self):
        self.cursor_type = "row"
        for col in HAND_COLUMNS:
            self.add_column(col, key=col)
        for row in self._rows:
            self.add_row(*row, key=row[0])

    def on_data_table_header_selected(self, event):
        col = event.column_key.value
        self._reverse = not self._reverse if col == self._sort_col else False
        self._sort_col = col
        self.sort(col, reverse=self._reverse)


class PokerApp(App):
    CSS = """
    DataTable { height: 1fr; }
    .summary { padding: 1 2; }
    """
    BINDINGS = [("q", "quit", "종료")]

    def __init__(self, hand_rows=None, mtt_summary=None, icm_result=None):
        super().__init__()
        self.hand_rows = hand_rows
        self.mtt_summary = mtt_summary
        self.icm_result = icm_result

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent():
            if self.hand_rows is not None:
                with TabPane("Hands", id="hands"):
                    yield HandsTable(self.hand_rows)
            if self.mtt_summary is not None:
                with TabPane("MTT", id="mtt"):
                    n, buyin, prize, itm = self.mtt_summary
                    roi = 100 * (prize - buyin) / buyin if buyin else 0
                    itm_pct = 100 * itm / n if n else 0
                    yield Static(
                        f"토너먼트 {n}개\n"
                        f"바이인 {buyin:.2f} | 상금 {prize:.2f} | 손익 {prize - buyin:+.2f}\n"
                        f"ROI {roi:.1f}% | ITM {itm_pct:.1f}%",
                        classes="summary",
                    )
            if self.icm_result is not None:
                with TabPane("ICM", id="icm"):
                    yield Static(self._icm_table(), classes="summary")
        yield Footer()

    def _icm_table(self):
        stacks, payouts, ev = self.icm_result
        total, pool = sum(stacks), sum(payouts)
        lines = [f"{'player':<10}{'칩':>10}{'칩%':>8}{'ICM $':>10}{'ICM%':>8}"]
        for n, (s, e) in enumerate(zip(stacks, ev, strict=True), 1):
            lines.append(f"{'p' + str(n):<10}{s:>10.0f}{100 * s / total:>7.1f}%{e:>10.2f}{100 * e / pool:>7.1f}%")
        return "\n".join(lines)
