# verum-registry

A web-api project written in Verum.

**Language Profile:** Application
**Description:** No unsafe, refinements + runtime checks (80% users)

## Quick Start

```bash
# Build (Tier 0 - instant compilation)
verum build

# Run
verum run

# Run tests
verum test

# Build for production (Tier 2 - AOT compilation)
verum build --release
```

## Performance Profiles

| Tier | Compilation | Execution | Use Case |
|------|-------------|-----------|----------|
| 0 | Instant (<100ms) | Interpreted | Fast iteration |
| 1 | Fast (~1s) | JIT | Development |
| 2 | Moderate (~10s) | Native | Production |
| 3 | Slow (~30s) | Optimized | Maximum performance |

## Project Structure

- `src/` - Source code
- `tests/` - Integration tests
- `benches/` - Performance benchmarks
- `examples/` - Usage examples
- `verum.toml` - Project manifest

## Semantic Honesty

Verum shows real costs transparently:
- CBGR overhead: ~15ns per reference check
- Verification: Runtime by default, compile-time optional
- Memory safety: Zero-cost where proven, minimal cost otherwise

Run `verum profile --memory` to analyze CBGR overhead in your code.

## License

MIT OR Apache-2.0
