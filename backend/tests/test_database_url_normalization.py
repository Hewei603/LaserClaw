"""Bare PostgreSQL URLs must select the driver declared in requirements."""
import pytest
from sqlalchemy.engine import make_url

from app.config import Settings


@pytest.mark.parametrize(('url', 'expected'), [
    ('postgresql://user:pass@localhost:5432/lab', 'postgresql+psycopg2://user:pass@localhost:5432/lab'),
    ('postgres://user:pass@localhost/lab?sslmode=require', 'postgresql+psycopg2://user:pass@localhost/lab?sslmode=require'),
    ('postgresql+psycopg2://user:pass@host/lab', 'postgresql+psycopg2://user:pass@host/lab'),
    ('postgresql+psycopg://user:pass@host/lab', 'postgresql+psycopg://user:pass@host/lab'),
    ('sqlite://', 'sqlite://'),
    ('sqlite:///:memory:', 'sqlite:///:memory:'),
])
def test_database_url_uses_declared_driver_without_changing_connection(url, expected):
    actual = Settings(database_url=url).database_url
    assert actual == expected
    if actual.startswith('postgresql+psycopg2://'):
        dialect = make_url(actual).get_dialect()
        assert dialect.driver == 'psycopg2'
        assert dialect.import_dbapi().__name__ == 'psycopg2'
