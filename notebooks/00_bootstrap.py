# %%
from semicon_alpha.workflows import build_settings, build_workspace_summary

# In Zerve, prefer setting SEMICON_ALPHA_STORAGE_ROOT in the environment.
settings = build_settings()

workspace_summary = build_workspace_summary(settings)
workspace_summary
