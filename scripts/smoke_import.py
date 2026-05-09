"""Smoke import for Houdini hython."""

from houdini_ai_agent.adapters.houdini import create_best_adapter
from houdini_ai_agent.core.config import discover_external_configs, load_providers
from houdini_ai_agent.core.session import AgentSession


def main():
    adapter = create_best_adapter()
    providers = load_providers()
    hints = discover_external_configs()
    session = AgentSession(adapter)
    context = session.refresh_context()
    print("adapter=", adapter.name)
    print("providers=", [provider.name for provider in providers])
    print("external_configs=", [(hint.source, hint.found) for hint in hints])
    print("context_keys=", sorted(context.keys()))


if __name__ == "__main__":
    main()
