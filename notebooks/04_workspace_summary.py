# %%
from semicon_alpha.workflows import build_workspace_summary, load_processed_dataset

workspace_summary = build_workspace_summary(settings)
workspace_summary

# %%
news_articles = load_processed_dataset("news_articles_discovered", settings=settings)
company_registry = load_processed_dataset("company_registry", settings=settings)
market_prices = load_processed_dataset("market_prices_daily", settings=settings)

news_articles.head()
