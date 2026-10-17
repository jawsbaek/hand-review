import asyncio

from poker_tui import PokerApp


def test_renders_with_no_data():
    async def run():
        async with PokerApp([], None, None).run_test() as pilot:
            await pilot.pause()

    asyncio.run(run())


def test_renders_all_tabs_and_sorts():
    rows = [("Hero", 3, 82.8, 2760.0, 2237.4, "100.0", "100.0", "100.0")]
    icm_result = ([5000, 3000, 2000], [50, 30, 20], [38.39, 32.75, 28.86])
    mtt_summary = (3, 100.0, 150.0, 2)

    async def run():
        async with PokerApp(rows, mtt_summary, icm_result).run_test() as pilot:
            await pilot.pause()
            app = pilot.app
            table = app.query_one("HandsTable")
            table.on_data_table_header_selected(type("E", (), {"column_key": type("K", (), {"value": "hands"})()})())
            assert table.row_count == 1

    asyncio.run(run())


def test_percent_columns_sort_numerically():
    rows = [
        ("A", 1, 0.0, 0.0, 0.0, "100.0", "0.0", "-"),
        ("B", 1, 0.0, 0.0, 0.0, "25.0", "0.0", "50.0"),
        ("C", 1, 0.0, 0.0, 0.0, "9.5", "0.0", "100.0"),
    ]

    async def run():
        async with PokerApp(rows, None, None).run_test() as pilot:
            await pilot.pause()
            table = pilot.app.query_one("HandsTable")
            for col in ("VPIP", "3Bet"):
                table.on_data_table_header_selected(type("E", (), {"column_key": type("K", (), {"value": col})()})())
                order = [table.get_row_at(i)[0] for i in range(3)]
                assert order == {"VPIP": ["C", "B", "A"], "3Bet": ["B", "C", "A"]}[col], (col, order)

    asyncio.run(run())
