from app.tools.check_db import diagnose_network


def test_reachable_in_any_family_means_no_diagnosis():
    assert diagnose_network({"IPv4": "no-address", "IPv6": "ok"}) is None
    assert diagnose_network({"IPv4": "ok", "IPv6": "timeout"}) is None


def test_ipv6_only_host_with_unreachable_ipv6_points_to_the_session_pooler():
    msg = diagnose_network({"IPv4": "no-address", "IPv6": "timeout"})
    assert msg and "Session pooler" in msg and "IPv6" in msg


def test_unresolvable_host_is_a_dns_problem():
    assert "DNS" in (diagnose_network({"IPv4": "no-address", "IPv6": "no-address"}) or "")


def test_dual_stack_but_unreachable_is_a_network_problem_not_an_ipv6_one():
    msg = diagnose_network({"IPv4": "timeout", "IPv6": "timeout"})
    assert msg and "Session pooler" not in msg
