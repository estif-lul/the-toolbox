"""Provider adapters. Stages never import these directly: they call
`registry.get_provider(stage, profile)` and get a chain (primary + fallbacks) from config."""
