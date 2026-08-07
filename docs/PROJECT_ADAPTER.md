# Project Adapter

AAH attaches to an existing repository before it plans changes. It detects stacks, manifests, instruction files, package scripts, probable test/build commands, Git state, environment variable names and local tool availability.

It never persists environment variable values. `.env*` files are represented by filename plus variable names/classification only. Project-specific secret values are removed from review-agent child-process environments and can be passed to implementation roles only through an explicit task `required_env` declaration.

Existing project rules take precedence over generic AAH defaults. AAH does not rename folders or migrate stacks merely to match its own preferences.
