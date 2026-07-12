from gui.ui_theme import get_theme, normalize_theme, theme_toggle_label


def test_normalize_theme() -> None:
    assert normalize_theme("dark") == "dark"
    assert normalize_theme("DarkMode") == "dark"
    assert normalize_theme("light") == "light"
    assert normalize_theme(None) == "light"


def test_theme_toggle_label() -> None:
    assert theme_toggle_label("light") == "深色模式"
    assert theme_toggle_label("dark") == "浅色模式"


def test_get_theme_palette() -> None:
    assert get_theme("dark").window_bg == "#1e1e1e"
    assert get_theme("light").text_bg == "#ffffff"
