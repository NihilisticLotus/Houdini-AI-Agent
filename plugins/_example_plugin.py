"""Example plugin demonstrating the plugin API.

Copy this file to the plugins/ directory (without the _ prefix) to activate.
"""

PLUGIN_INFO = {
    "name": "Example Plugin",
    "version": "1.0.0",
    "author": "Houdini AI Agent Team",
    "description": "Demonstrates the plugin hook, tool, and button APIs.",
    "settings": [
        {
            "key": "log_tools",
            "type": "bool",
            "label": "Log tool executions",
            "default": True,
        },
        {
            "key": "greeting",
            "type": "string",
            "label": "Greeting message",
            "default": "Hello from Example Plugin!",
        },
    ],
}


def register(ctx):
    """Plugin entry point — ctx is a PluginContext instance."""

    greeting = ctx.get_setting("greeting", "Hello!")
    ctx.log(f"Loaded! Greeting: {greeting}")

    # --- Event hook ---
    @ctx.on("on_tool_after")
    def on_tool_after(tool_name, args, result):
        if ctx.get_setting("log_tools", True):
            success = result.get("success", True) if isinstance(result, dict) else True
            status = "✓" if success else "✕"
            ctx.log(f"Tool {status} {tool_name}")

    # --- External tool ---
    ctx.register_tool(
        name="example_hello",
        description="Returns a greeting from the example plugin.",
        schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name to greet",
                },
            },
            "required": ["name"],
        },
        handler=_handle_hello,
        modes=("ask", "agent"),
    )

    # --- Toolbar button ---
    ctx.register_button(
        icon="🔌",
        tooltip="Example Plugin: Click to log a message",
        callback=_on_button_click,
    )


def _handle_hello(args):
    """Handler for the example_hello tool."""
    name = args.get("name", "World")
    return {
        "success": True,
        "result": f"Hello, {name}! This is the example plugin speaking.",
    }


def _on_button_click():
    """Handler for the toolbar button."""
    print("[Plugin:Example Plugin] Button clicked!")
