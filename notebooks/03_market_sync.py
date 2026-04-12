# %%
from semicon_alpha.workflows import run_market_workflow

market_result = run_market_workflow(
    settings=settings,
    start="2024-01-01",
)
market_result
