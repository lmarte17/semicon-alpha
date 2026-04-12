# %%
from semicon_alpha.workflows import run_reference_workflow

reference_result = run_reference_workflow(
    settings=settings,
    skip_exchange_symbols=False,
)
reference_result
