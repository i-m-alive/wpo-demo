"""The two graphs: the supervisor runs nodes 1-4 in order with the compliance pass/fail edge; the copilot is its own
graph with its own entry point."""
from agents.manager_copilot import copilot
from agents.supervisor import supervisor


def edges(graph) -> set[tuple[str, str]]:
    return {(e.source, e.target) for e in graph.get_graph().edges}


def test_supervisor_order_and_conditional_edge():
    g = supervisor.get_graph()
    assert list(g.nodes) == ["__start__", "forecast_demand", "optimize_roster", "compliance", "writeback", "__end__"]
    e = edges(supervisor)
    assert {("__start__", "forecast_demand"), ("forecast_demand", "optimize_roster"),
            ("optimize_roster", "compliance"), ("compliance", "writeback"), ("compliance", "optimize_roster"),
            ("writeback", "__end__"), ("compliance", "__end__")} == e


def test_copilot_is_a_separate_graph():
    assert list(copilot.get_graph().nodes) == ["__start__", "manager_copilot", "__end__"]
    assert edges(copilot) == {("__start__", "manager_copilot"), ("manager_copilot", "__end__")}
    assert not set(copilot.get_graph().nodes) & {"forecast_demand", "writeback"}
