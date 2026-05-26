from app.agents.execution_trace import (
    append_tool,
    append_workflow,
    new_trace,
    upsert_stage,
)


def test_new_trace_and_stage_upsert() -> None:
    trace = new_trace()
    upsert_stage(trace, "文献检索", "active")
    upsert_stage(trace, "文献检索", "done")
    assert len(trace["stages"]) == 1
    assert trace["stages"][0]["state"] == "done"


def test_append_tool_and_workflow() -> None:
    trace = new_trace()
    append_tool(
        trace,
        tool_id="tc1",
        name="web_search",
        args={"query": "ai"},
        status="done",
        output='{"hits": 2}',
    )
    append_workflow(
        trace,
        node_id="f0",
        name="web_fetch",
        state="done",
        title="Paper",
        url="https://arxiv.org/abs/1",
    )
    assert len(trace["tools"]) == 1
    assert trace["tools"][0]["name"] == "web_search"
    assert len(trace["workflows"]) == 1
    assert trace["workflows"][0]["state"] == "done"
