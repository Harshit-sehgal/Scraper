import pytest
from app.topology_state import parse_topology_key


def test_parse_topology_key_valid_tuple():
    """Verify that a valid tuple string representing two string items parses correctly."""
    result = parse_topology_key("('role_a', 'role_b')")
    assert result == ("role_a", "role_b")

    result2 = parse_topology_key('("role_c", "role_d")')
    assert result2 == ("role_c", "role_d")


def test_parse_topology_key_list_fails():
    """Verify that a list representation instead of a tuple raises ValueError."""
    with pytest.raises(ValueError, match="Invalid topology key structure"):
        parse_topology_key("['role_a', 'role_b']")


def test_parse_topology_key_wrong_length_fails():
    """Verify that a tuple with a length other than 2 raises ValueError."""
    with pytest.raises(ValueError, match="Invalid topology key structure"):
        parse_topology_key("('role_a',)")
    with pytest.raises(ValueError, match="Invalid topology key structure"):
        parse_topology_key("('role_a', 'role_b', 'role_c')")


def test_parse_topology_key_non_string_elements_fails():
    """Verify that a tuple containing non-string elements raises ValueError."""
    with pytest.raises(ValueError, match="Invalid topology key structure"):
        parse_topology_key("('role_a', 123)")
    with pytest.raises(ValueError, match="Invalid topology key structure"):
        parse_topology_key("(True, 'role_b')")


def test_parse_topology_key_malformed_string_fails():
    """Verify that a syntactically malformed string raises ValueError."""
    with pytest.raises(ValueError, match="Invalid topology key format"):
        parse_topology_key("('role_a', 'role_b'")


def test_parse_topology_key_malicious_payload_fails():
    """Verify that a malicious string attempting execution raises ValueError and does not execute."""
    malicious = "__import__('os').system('echo hacked')"
    with pytest.raises(ValueError, match="Invalid topology key format"):
        parse_topology_key(malicious)
