import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--live",
        action="store_true",
        default=False,
        help="run tests that call the configured live model or external services",
    )
    parser.addoption(
        "--postgres",
        action="store_true",
        default=False,
        help="run tests that require the local PostgreSQL service",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if config.getoption("--live"):
        return
    skip_live = pytest.mark.skip(reason="live tests require the --live flag")
    skip_postgres = pytest.mark.skip(
        reason="PostgreSQL tests require the --postgres flag"
    )
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)
        if "postgres" in item.keywords and not config.getoption("--postgres"):
            item.add_marker(skip_postgres)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "live: calls a configured live model or service")
    config.addinivalue_line("markers", "assignment: exercises the PDF scenario")
    config.addinivalue_line(
        "markers", "postgres: requires the local PostgreSQL service"
    )
