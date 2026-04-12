# %%
from semicon_alpha.workflows import run_news_workflow

news_result = run_news_workflow(
    settings=settings,
    enrich_limit=25,
    force_enrich=False,
)
news_result
