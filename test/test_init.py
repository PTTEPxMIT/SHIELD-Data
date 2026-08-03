"""Unit tests for __init__.py module.

Tests cover:
- Version attribute existence
- Exported API functions
"""

import shield_data


def test_version_attribute_exists():
    """Test that __version__ attribute is defined."""
    assert hasattr(shield_data, "__version__")


def test_version_is_string():
    """Test that __version__ is a string."""
    assert isinstance(shield_data.__version__, str)


def test_version_is_not_empty():
    """Test that __version__ is not an empty string."""
    assert len(shield_data.__version__) > 0


def test_catalogue_is_exported():
    """Test that catalogue function is exported."""
    assert hasattr(shield_data, "catalogue")


def test_load_is_exported():
    """Test that load function is exported."""
    assert hasattr(shield_data, "load")


def test_load_filtered_is_exported():
    """Test that load_filtered function is exported."""
    assert hasattr(shield_data, "load_filtered")


def test_load_metadata_is_exported():
    """Test that load_metadata function is exported."""
    assert hasattr(shield_data, "load_metadata")


def test_all_contains_catalogue():
    """Test that __all__ contains 'catalogue'."""
    assert "catalogue" in shield_data.__all__


def test_all_contains_load():
    """Test that __all__ contains 'load'."""
    assert "load" in shield_data.__all__


def test_all_contains_load_filtered():
    """Test that __all__ contains 'load_filtered'."""
    assert "load_filtered" in shield_data.__all__


def test_all_contains_load_metadata():
    """Test that __all__ contains 'load_metadata'."""
    assert "load_metadata" in shield_data.__all__


def test_all_has_correct_count():
    """Test that __all__ contains exactly 6 items."""
    assert len(shield_data.__all__) == 6
