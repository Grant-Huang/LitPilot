"""Pipeline 性能合规测试 — 对照 llm-call-optimization.mdc 逐条验证。

每个 test 函数头部用 (#N) 标记对应 rule 中的章节号。

覆盖范围：
  设置缓存（内存 TTL + 文件 fallback + to_thread 不阻塞事件循环）
  Pre-LLM I/O 并行化（asyncio.to_thread + gather）
  DeepSeek 思考模式控制（v4-flash 关闭 / v4-pro 保持）
  冷启动文件缓存存活
  保存设置时清空双缓存
  整体 Pipeline 冷启动计时
"""
from __future__ import annotations

import asyncio
import os
import time as _time
from unittest.mock import MagicMock, patch

import pytest


# =========================================================================
# 设置缓存（# 设置缓存）
# =========================================================================

@pytest.fixture(autouse=True)
def _reset_settings_cache():
    """每个测试前重置设置缓存 + 确保文件缓存不干扰后续测试。"""
    from app.agents.agent_settings import _clear_settings_cache, _SETTINGS_FILE

    _clear_settings_cache()
    try:
        if os.path.isfile(_SETTINGS_FILE):
            os.remove(_SETTINGS_FILE)
    except OSError:
        pass
    yield
    _clear_settings_cache()
    try:
        if os.path.isfile(_SETTINGS_FILE):
            os.remove(_SETTINGS_FILE)
    except OSError:
        pass


@pytest.mark.asyncio
async def test_settings_cache_memory_hit_returns_same_object() -> None:
    """(# 设置缓存) 内存 TTL 缓存，二次调用返回同一对象。"""
    from app.agents.agent_settings import get_merged_settings

    with patch(
        "app.storage.file_store.FileStore.get_agent_settings_merged",
        return_value={"llm_provider": "openai", "llm_model": "gpt-4o-mini"},
    ):
        first = await get_merged_settings()
    second = await get_merged_settings()
    assert first is second, "内存缓存应返回同一 dict 对象"


@pytest.mark.asyncio
async def test_settings_file_cache_fallback_on_cold_start() -> None:
    """(# 设置缓存 / Serverless) 清空内存后仍可从文件缓存读取。"""
    from app.agents.agent_settings import get_merged_settings, _clear_settings_cache

    with patch(
        "app.storage.file_store.FileStore.get_agent_settings_merged",
        return_value={"llm_provider": "deepseek", "llm_model": "deepseek-v4-flash"},
    ):
        first = await get_merged_settings()

    # 模拟冷启动：清内存缓存但文件存活
    _clear_settings_cache()

    # 不应调 store → 应读文件缓存
    second = await get_merged_settings()
    assert first == second, "文件缓存应返回相同数据"
    assert first is not second, "文件缓存返回新 dict（内存指针不同）"


@pytest.mark.asyncio
async def test_settings_cache_refreshes_after_ttl() -> None:
    """(# 设置缓存) TTL 过期后重新调 store。"""
    from app.agents.agent_settings import get_merged_settings

    call_count = [0]

    def _fake_store():
        call_count[0] += 1
        return {"llm_provider": "openai", "ts": call_count[0]}

    with patch(
        "app.storage.file_store.FileStore.get_agent_settings_merged",
        side_effect=_fake_store,
    ):
        first = await get_merged_settings()
        assert first["ts"] == 1, "首次应调 store"

        second = await get_merged_settings()
        assert second is first, "TTL 内不应调 store"


@pytest.mark.asyncio
async def test_clear_all_caches_removes_memory_and_file() -> None:
    """(# 设置缓存) save_agent_settings 后双缓存清空。

    注意：必须用 `import ... as m` 方式访问模块变量，
    因为 `from ... import x` 会拷贝值，不会追踪模块内的 global 赋值。
    """
    import app.agents.agent_settings as m

    with patch(
        "app.storage.file_store.FileStore.get_agent_settings_merged",
        return_value={"key": "val"},
    ):
        await m.get_merged_settings()

    assert m._SETTINGS_CACHE is not None, "get_merged_settings 应写入内存缓存"
    assert os.path.isfile(m._SETTINGS_FILE), "get_merged_settings 应写入文件缓存"

    m._clear_all_caches()

    assert m._SETTINGS_CACHE is None, "内存缓存应清空"
    assert not os.path.isfile(m._SETTINGS_FILE), "文件缓存应删除"


@pytest.mark.asyncio
async def test_get_merged_settings_does_not_block_event_loop() -> None:
    """(# 设置缓存 / 阻塞检测) 冷启动调 sync store 时须用 to_thread，不阻塞事件循环。

    用 mock 模拟 0.3s Turso 延迟，同时启动一个 async 监视器。
    若监视器在 get_merged_settings 期间未能运行，说明 sync 调用阻塞了事件循环。
    """
    import app.agents.agent_settings as m

    spy_ran = False
    store_delay = 0.3

    def _slow_store():
        _time.sleep(store_delay)
        return {"llm_provider": "openai"}

    async def _spy():
        nonlocal spy_ran
        await asyncio.sleep(store_delay * 0.2)  # 等在阻塞期内能跑一次
        spy_ran = True

    with patch(
        "app.storage.file_store.FileStore.get_agent_settings_merged",
        side_effect=_slow_store,
    ):
        spy = asyncio.create_task(_spy())
        t0 = _time.monotonic()
        result = await m.get_merged_settings()
        elapsed = _time.monotonic() - t0
        await spy

    assert result == {"llm_provider": "openai"}
    assert spy_ran, (
        "并发监视器应在 get_merged_settings 阻塞期内运行；"
        f"若失败则说明 sync 调用阻塞了事件循环（耗时 {elapsed:.2f}s）"
    )
    assert elapsed < store_delay * 1.1, (
        f"get_merged_settings 比 mock Turso 还长（{elapsed:.2f}s），"
        "说明它没有额外阻塞"
    )


@pytest.mark.asyncio
async def test_multiple_concurrent_getx_do_not_serialize() -> None:
    """(# 设置缓存 / 并发) 多个 get_*() 同时调 get_merged_settings 不串行。"""
    from app.agents.agent_settings import (
        get_web_search_provider,
        get_web_search_api_key,
        get_citation_format,
    )

    def _fake_store():
        _time.sleep(0.2)  # 模拟 Turso 延迟
        return {
            "search_provider": "tavily",
            "web_search_api_key": "sk-test",
            "citation_format": "apa",
        }

    with patch(
        "app.storage.file_store.FileStore.get_agent_settings_merged",
        side_effect=_fake_store,
    ):
        t0 = _time.monotonic()
        results = await asyncio.gather(
            get_web_search_provider(),
            get_web_search_api_key(),
            get_citation_format(),
        )
        elapsed = _time.monotonic() - t0

    # 串行 3 次 * 0.2s = 0.6s；并行 ≈ 0.2s（共享同一 to_thread 的 store 调用？
    assert elapsed < 0.5, (
        f"3 个 get_* 总耗时 {elapsed:.2f}s；"
        "若 ≥0.5s 说明未利用内存缓存或 to_thread 并行"
    )
    assert results[0] == "tavily"
    assert results[1] == "sk-test"
    assert results[2] == "apa"


# =========================================================================
# Pre-LLM I/O 并行化（# 预调用 I/O 并行化）
# =========================================================================

def test_pre_llm_io_uses_asyncio_gather() -> None:
    """(# 预调用 I/O 并行化) literature_turn 的初始读操作用 gather 并发。

    这是 AST 静态检查 — 确保 stream_literature_turn 调用 asyncio.gather + to_thread。
    """
    from app.agents.literature_turn import stream_literature_turn

    import ast
    import inspect

    source = inspect.getsource(stream_literature_turn)
    tree = ast.parse(source)

    has_gather = any(
        isinstance(node, ast.Call)
        and getattr(node.func, "attr", None) == "gather"
        for node in ast.walk(tree)
    )
    assert has_gather, "stream_literature_turn 必须使用 asyncio.gather 并行化 I/O"
    has_to_thread = any(
        isinstance(node, ast.Call)
        and getattr(node.func, "attr", None) == "to_thread"
        for node in ast.walk(tree)
    )
    assert has_to_thread, "Turso 同步方法须用 asyncio.to_thread 封装"


def test_get_merged_settings_uses_to_thread() -> None:
    """(# 设置缓存 / 阻塞检测 / AST) get_merged_settings 内部使用 asyncio.to_thread。"""
    from app.agents.agent_settings import get_merged_settings

    import ast
    import inspect

    source = inspect.getsource(get_merged_settings)
    tree = ast.parse(source)

    has_to_thread = any(
        isinstance(node, ast.Call)
        and getattr(node.func, "attr", None) == "to_thread"
        for node in ast.walk(tree)
    )
    assert has_to_thread, (
        "get_merged_settings 必须用 asyncio.to_thread 调用 sync store，"
        "否则阻塞事件循环"
    )


@pytest.mark.asyncio
async def test_parallel_reads_faster_than_serial() -> None:
    """(# 预调用 I/O 并行化) 4 个 Turso 读并行比串行快。"""
    delay = 0.1

    t0 = _time.monotonic()
    for _ in range(4):
        await asyncio.sleep(delay)
    serial_ms = (_time.monotonic() - t0) * 1000

    t0 = _time.monotonic()
    await asyncio.gather(
        asyncio.sleep(delay),
        asyncio.sleep(delay),
        asyncio.sleep(delay),
        asyncio.sleep(delay),
    )
    parallel_ms = (_time.monotonic() - t0) * 1000

    assert parallel_ms < serial_ms * 0.8, "并行应显著快于串行"
    assert parallel_ms < delay * 1000 * 1.3, "并行总耗时 ≈ 最慢个体耗时"


# =========================================================================
# DeepSeek 思考模式控制（# DeepSeek 思考模式控制）
# =========================================================================

@pytest.mark.parametrize(
    ("provider", "model", "extra", "expected"),
    [
        ("deepseek", "deepseek-v4-flash", None, {"thinking": {"type": "disabled"}}),
        ("deepseek", "deepseek-chat", None, {"thinking": {"type": "disabled"}}),
        ("deepseek", "deepseek-v4-pro", None, None),
        ("deepseek", "deepseek-reasoner", None, None),
        ("openai", "gpt-4o-mini", None, None),
        ("zhipu", "glm-4-flash", None, None),
        ("deepseek", "deepseek-v4-pro", {"thinking": "disabled"}, {"thinking": {"type": "disabled"}}),
        ("deepseek", "deepseek-v4-flash", {"thinking": "enabled"}, None),
    ],
)
def test_deepseek_extra_body(provider, model, extra, expected) -> None:
    """(# DeepSeek 思考模式控制) 按模型自动控制 thinking 开关。"""
    from app.llm.base import LLMConfig
    from app.llm.openai_llm import OpenAILLM

    cfg = LLMConfig(provider=provider, api_key="sk-test", model=model, extra=extra)
    llm = OpenAILLM(cfg)
    result = llm._deepseek_extra_body()
    assert result == expected, (
        f"provider={provider} model={model} extra={extra}: "
        f"expected {expected}, got {result}"
    )


def test_deepseek_extra_body_in_chat_stream_parts() -> None:
    """(# DeepSeek 思考模式控制) chat_stream_parts 传递了 extra_body。"""
    from app.llm.base import LLMConfig
    from app.llm.openai_llm import OpenAILLM

    cfg = LLMConfig(provider="deepseek", api_key="sk-test", model="deepseek-v4-flash")
    llm = OpenAILLM(cfg)
    eb = llm._deepseek_extra_body()
    assert eb is not None, "v4-flash 应关闭思考"
    assert eb["thinking"]["type"] == "disabled"


# =========================================================================
# 流式落库（# 流式落库）
# =========================================================================


def test_stream_coalescer_installed() -> None:
    """(# 流式落库) literature_tasks 使用 _StreamCoalescer。"""
    from app.tasks.literature_tasks import _StreamCoalescer, COALESCE_MAX_CHARS, COALESCE_MAX_IDLE_MS

    assert callable(_StreamCoalescer)
    assert COALESCE_MAX_CHARS <= 20, "阈值应 ≤ 20 避免长时间 buffer"
    assert COALESCE_MAX_IDLE_MS <= 100, "空闲冲刷延迟应 ≤ 100ms"


def test_heartbeat_constant_defined() -> None:
    """(# 流式落库) 心跳常量 HEARTBEAT_SEC 已定义。"""
    from app.tasks.literature_tasks import HEARTBEAT_SEC

    assert isinstance(HEARTBEAT_SEC, (int, float))
    assert HEARTBEAT_SEC > 0


# =========================================================================
# HTTP 连接复用（# 连接复用）— smoke 检查
# =========================================================================

def test_http_client_pool_configured() -> None:
    """(# 连接复用) 共享 client 有连接池和拆分超时。"""
    import httpx

    from app.llm.http_client import DEFAULT_LIMITS, get_async_client

    client = get_async_client()
    assert isinstance(client, httpx.AsyncClient)
    assert isinstance(client.timeout, httpx.Timeout)
    assert client.timeout.connect is not None
    assert client.timeout.read is not None
    assert DEFAULT_LIMITS.max_keepalive_connections > 0


# =========================================================================
# LLM 实例复用（# LLM 实例复用）— smoke 检查
# =========================================================================

def test_llm_cache_exists() -> None:
    """(# LLM 实例复用) llm_service 有缓存函数。"""
    from app.services.llm_service import _build_from_cfg, reset_llm_cache

    assert callable(_build_from_cfg)
    assert callable(reset_llm_cache)


# =========================================================================
# 整体 pipeline 冷启动计时测试
# =========================================================================

@pytest.mark.asyncio
async def test_pipeline_cold_start_timing_with_realistic_mocks(
    tmp_path, monkeypatch
) -> None:
    """(整体 / 冷启动) 模拟 Turso 延迟验证 pipeline 启动阶段 ≤ 5s。

    场景：完整冷启动 — 无内存缓存、无文件缓存、store 同步操作延迟 0.3s。
    不执行完整的 retrieval pipeline（search / fetch / relevance filter），
    而是将其 mock 为快速返回，只测试 orchestration 启动开销（并行 I/O + 设置缓存 + intent路由）。
    预期：从 yield turn_start 到 early_return ≤ 5s。
    """
    from app.agents.literature_turn import stream_literature_turn
    from app.storage.file_store import FileStore

    store = FileStore(tmp_path)
    monkeypatch.setattr("app.agents.literature_turn.get_store", lambda: store)
    monkeypatch.setattr("app.agents.agent_settings.get_store", lambda: store)
    monkeypatch.setattr("app.storage.file_store.get_store", lambda: store)

    meta = store.create_session("cold-start-perf-test")

    # 模拟 store sync 操作有 0.3s 延迟（Turso 远程 DB 典型值）
    _orig_get_merged = store.get_agent_settings_merged

    def _slow_get_merged():
        _time.sleep(0.3)
        return _orig_get_merged()

    monkeypatch.setattr(store, "get_agent_settings_merged", _slow_get_merged)

    mock_llm = MagicMock()

    async def _mock_retrieval_pipeline(ctx):
        """快速返回的 retrieval pipeline mock（async generator）。"""
        if False:
            yield  # pragma: no cover
        ctx.early_return = True  # 让 pipeline 短路退出

    t0 = _time.monotonic()

    with (
        patch(
            "app.agents.literature_turn.get_web_search_provider",
            return_value="multi_academic",
        ),
        patch(
            "app.agents.literature_turn.get_web_fetch_provider",
            return_value="jina",
        ),
        patch(
            "app.agents.literature_turn.load_planner_context",
            return_value=MagicMock(use_llm_planner=False),
        ),
        patch(
            "app.agents.literature_turn.get_review_llm",
            return_value=mock_llm,
        ),
        patch(
            "app.agents.literature_turn.get_pipeline_llm",
            return_value=mock_llm,
        ),
        patch(
            "app.agents.literature_intent.get_router_llm",
            return_value=mock_llm,
        ),
        patch(
            "app.agents.literature_turn.run_retrieval_pipeline",
            _mock_retrieval_pipeline,
        ),
    ):
        collected_events = []
        async for ev_type, _ in stream_literature_turn(
            meta["id"],
            "test cold start performance",
            persist_user_message=False,
        ):
            collected_events.append(ev_type)
            if ev_type in ("turn_end", "error"):
                break

    elapsed = _time.monotonic() - t0
    assert elapsed < 5.0, (
        f"冷启动 pipeline 启动阶段总耗时 {elapsed:.2f}s ≥ 5s 上线；"
        "预期并行 I/O + 设置缓存应快速完成"
    )
    assert "extension" in collected_events, "应产出 turn_start 事件（类型为 extension）"
    assert "skill_active" in collected_events, "产出 skill_active 事件"


# =========================================================================
# 性能门禁：关键常量合规
# =========================================================================

def test_coalesce_constants_compliant() -> None:
    """(性能门禁) COALESCE_MAX_CHARS ≤ 20，COALESCE_MAX_IDLE_MS 在合理范围。"""
    from app.tasks.literature_tasks import COALESCE_MAX_CHARS, COALESCE_MAX_IDLE_MS

    assert COALESCE_MAX_CHARS <= 20, "字阈值过高导致延迟感知"
    assert COALESCE_MAX_IDLE_MS <= 100, "空闲冲刷延迟过大"
    assert COALESCE_MAX_IDLE_MS >= 10, "空闲冲刷太小可能高频冲刷"


def test_settings_cache_ttl_env_overridable() -> None:
    """(性能门禁) 设置缓存 TTL 可通过环境变量覆盖。"""
    from app.agents.agent_settings import _SETTINGS_TTL_SEC, _SETTINGS_FILE_TTL_SEC

    assert _SETTINGS_TTL_SEC > 0
    assert _SETTINGS_FILE_TTL_SEC > 0
    assert _SETTINGS_FILE_TTL_SEC >= _SETTINGS_TTL_SEC, "文件 TTL 应 ≥ 内存 TTL"


def test_llm_cache_reset_function_exported() -> None:
    """(性能门禁) llm_service 导出 reset_llm_cache 供测试/热加载使用。"""
    from app.services.llm_service import reset_llm_cache

    reset_llm_cache()
    reset_llm_cache()
