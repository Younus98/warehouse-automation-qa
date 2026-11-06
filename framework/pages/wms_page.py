"""
Page Object for the Mini WMS screen.

The test says WHAT it does ("scan pallet PAL-0001"), the page object knows
HOW (which field to fill, which button to click). If the screen layout
changes, only this file needs updating - not every test.

Locators use data-testid attributes: they don't change when someone renames
a label or restyles the page, so the tests don't break for cosmetic changes.
"""
from playwright.sync_api import Page, expect


class WmsPage:
    def __init__(self, page: Page):
        self.page = page
        self.message = page.get_by_test_id("message")

    def open(self):
        self.page.goto("/")
        return self

    def go_to(self, tab: str):
        """tab: inventory | receiving | orders | tasks"""
        self.page.get_by_test_id(f"tab-{tab}").click()

    # --- Receiving ---
    def scan_pallet(self, tu_id: str, tu_type: str, weight: float):
        self.go_to("receiving")
        self.page.get_by_test_id("infeed-tu").fill(tu_id)
        self.page.get_by_test_id("infeed-type").select_option(tu_type)
        self.page.get_by_test_id("infeed-weight").fill(str(weight))
        self.page.get_by_test_id("infeed-submit").click()

    # --- Inventory ---
    def stock_row(self, product_id: str):
        return self.page.get_by_test_id(f"stock-row-{product_id}")

    def tu_row(self, tu_id: str):
        return self.page.get_by_test_id(f"tu-row-{tu_id}")

    def expect_stock(self, product_id: str, on_hand, allocated, available):
        self.go_to("inventory")
        row = self.stock_row(product_id)
        expect(row.get_by_test_id("on-hand")).to_have_text(str(on_hand))
        expect(row.get_by_test_id("allocated")).to_have_text(str(allocated))
        expect(row.get_by_test_id("available")).to_have_text(str(available))

    # --- Orders ---
    def order_row(self, order_id: str):
        return self.page.get_by_test_id(f"order-row-{order_id}")

    def release_order(self, order_id: str):
        self.go_to("orders")
        self.page.get_by_test_id(f"release-{order_id}").click()

    # --- Tasks ---
    def task_rows(self):
        return self.page.locator("[data-testid^='task-row-']")

    def complete_task(self, task_id: int):
        self.go_to("tasks")
        self.page.get_by_test_id(f"complete-{task_id}").click()
