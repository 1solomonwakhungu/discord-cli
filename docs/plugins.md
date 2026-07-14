# Plugin system

`discord-cli` can be extended with third-party command groups without
modifying this repository. A plugin is any installed Python distribution
that declares a `discord_cli.plugins` entry point.

## How it works

On startup, `discord_cli.cli` attaches its own built-in command groups and
then calls `discord_cli.plugins.load_plugins(registry, main)`, which:

1. Discovers every entry point registered in the `discord_cli.plugins`
   group across all installed distributions (via
   `importlib.metadata.entry_points`).
2. Resolves and calls each entry point with the shared
   `discord_cli.registry.CommandRegistry` instance.
3. Attaches any command groups the plugin registered to the root CLI.

If a plugin fails to import, resolve, or register (missing dependency,
raises an exception, entry point points at something that isn't callable,
etc.), `discord-cli` logs a warning naming the plugin and continues
loading the rest. **A broken plugin can never crash the CLI or prevent
other plugins or built-in commands from working.**

## Plugin API contract

A plugin package must:

1. Declare an entry point in the `discord_cli.plugins` group, pointing at a
   callable (function or any other callable object):

   ```toml
   [project.entry-points."discord_cli.plugins"]
   hello = "plugin_hello:register"
   ```

   The entry point *name* (`hello` above) is what shows up in
   `discord-cli plugins list`. It does not have to match the command group
   name, though keeping them aligned makes plugins easier to identify.

2. Implement that callable with the signature:

   ```python
   def register(registry: CommandRegistry) -> None: ...
   ```

   `registry` is the same `discord_cli.registry.CommandRegistry` instance
   used by every built-in command module. Use `@registry.group("name")` to
   define one or more new top-level command groups, exactly like a built-in
   command module does — see `src/discord_cli/commands/guilds.py` for a
   full example of the pattern (groups, subcommands, `@click.pass_context`).

3. Depend on `discordcli-agents` (the installed distribution name for
   `discord_cli`) so `import discord_cli` is guaranteed to work wherever the
   plugin is installed.

A plugin should **not** call `registry.attach_all()` itself — the loader
does that once, after every plugin has had a chance to register.

## Versioning expectations

- `discord-cli plugins list` reports the plugin's *distribution* version
  (from the installed package's metadata, e.g. `plugin-hello==0.1.0`), not
  a version declared inside the plugin's code. Bump your package's
  `version` in `pyproject.toml` when you cut a release.
- There is currently no compatibility pinning between `discord-cli` and
  plugins beyond whatever your plugin's `dependencies` declare (e.g.
  `discordcli-agents>=1.0.0`). Plugins should depend on a minimum
  `discord-cli` version that provides the registry APIs they use, and treat
  the `CommandRegistry` / Click APIs as the stable surface.
- Entry points are resolved fresh on every CLI invocation (each `discord-cli`
  run is a new process), so there is no plugin caching to invalidate between
  upgrades.

## Example plugin walkthrough

`examples/plugin-hello/` is a minimal, complete plugin package:

```
examples/plugin-hello/
├── pyproject.toml
├── README.md
└── src/
    └── plugin_hello/
        └── __init__.py
```

`pyproject.toml` declares the entry point:

```toml
[project.entry-points."discord_cli.plugins"]
hello = "plugin_hello:register"
```

`src/plugin_hello/__init__.py` defines `register()`, which uses the
registry to add a `hello` command group with a `world` subcommand that
prints a JSON payload:

```python
def register(registry: CommandRegistry) -> None:
    @registry.group("hello")
    def hello_group() -> None: ...

    @hello_group.command("world")
    @click.pass_context
    def hello_world(ctx: click.Context) -> None:
        print_output(make_payload({"message": "Hello from plugin!"}), human=...)
```

Once installed, this plugin adds:

- `discord-cli hello world` → `{"ok": true, "data": {"message": "Hello from plugin!"}}`
- An entry named `hello` in `discord-cli plugins list`

## Installing and testing a plugin

From a checkout of `discord-cli` with the example plugin present:

```bash
# Install discord-cli itself (editable, with the entry-point machinery active)
pip install -e ".[dev]"

# Install the example plugin so its entry point is discoverable
pip install -e examples/plugin-hello

# Confirm it was discovered
discord-cli plugins list
# {"ok": true, "data": {"plugins": [{"name": "hello", "version": "0.1.0", "module": "plugin_hello:register"}]}}

# Run its command
discord-cli hello world
# {"ok": true, "data": {"message": "Hello from plugin!"}}
```

To test that a broken plugin is handled gracefully, make `register()` raise
an exception (or point the entry point at a nonexistent module) and rerun
any `discord-cli` command — you should see a warning logged for that plugin
and every other command should keep working normally.

To write automated tests for your own plugin, register a fake
`CommandRegistry`/`click.Group` pair directly instead of relying on entry
point discovery — see `tests/test_plugins.py` in this repository for the
pattern used to test the loader itself.
