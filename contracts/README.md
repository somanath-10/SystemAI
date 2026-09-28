# Cross-language Contracts

JSON Schema exports live in `schema/` and are generated from the Python Pydantic source-of-truth for using `make schemas`.

The Rust Security Kernel currently has hand-written equivalent structures. A later release should add code generation/checks that prevent schema drift across Python/Rust/TypeScript.
