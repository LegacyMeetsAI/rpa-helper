"""Pure-logic helpers used by main_window.

Each controller owns one concern and exposes a small surface. They do not
depend on Qt — main_window calls them and renders the result. Keeping
them Qt-free means they can be tested in headless pytest.
"""
