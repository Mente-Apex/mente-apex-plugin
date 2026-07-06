# DDD Testing Strategy — Hexagonal / Ports-and-Adapters

When the codebase follows a hexagonal architecture, the testing approach shifts to respect the domain boundary. This is dependency inversion made structural: the domain owns the port abstractions, and infrastructure depends on the domain — never the reverse.

## Test the ports first

Ports (interfaces defining how the domain talks to the outside world) are where unit tests belong. The domain layer — entities, value objects, aggregates, domain services — should be fully testable through its ports without any infrastructure dependencies. These are pure unit tests: instantiate domain objects, call methods, assert outcomes.

Start the TDD cycle by writing tests against the domain layer through its ports. This is where the core business logic lives and should be the most thoroughly tested part of the system.

## No mocks — and that's the point

If the domain is properly isolated behind ports, you don't need mocks for unit tests. Test domain logic by creating real domain objects and calling real methods. No mock repositories, no mock services, no mock anything.

If you find yourself reaching for `unittest.mock`, `MagicMock`, or `patch` to test domain logic, stop and flag it. This is a design smell — the domain layer has a direct dependency on infrastructure, which violates the ports-and-adapters boundary. The correct fix is restructuring so the domain depends on an abstraction (a port), not papering over coupling with mocks.

Warn the user explicitly: *"This domain code depends directly on [infrastructure detail]. In a properly structured hexagonal architecture, this would go through a port. Want me to refactor the boundary first?"*

## Integration tests for adapters — only when requested

Adapters (concrete implementations that plug into ports — database repositories, HTTP clients, message queue publishers) need integration tests to verify they work with the real external system. But these are slower, require infrastructure, and are a different concern.

Don't write adapter integration tests as part of the default TDD cycle. Focus on the domain. If the user asks for integration tests, write them — testing that the adapter correctly implements the port interface against real infrastructure (or a close stand-in like a test database).

## The testing pyramid for DDD

1. **Unit tests on the domain layer** (through ports) — fast, no mocks, high volume. This is the default.
2. **Integration tests on adapters** — slower, real infrastructure. Only when requested.
3. **End-to-end tests** — full stack. Out of scope unless explicitly asked.
