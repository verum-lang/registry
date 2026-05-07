# Resilience Patterns for Verum Registry

Industrial-grade fault tolerance patterns for building robust distributed systems.

## Overview

This module implements five core resilience patterns that protect against failures and provide graceful degradation:

1. **Circuit Breaker** - Prevents cascading failures
2. **Retry with Exponential Backoff** - Handles transient failures
3. **Timeout** - Prevents indefinite blocking
4. **Bulkhead** - Isolates resources
5. **Fallback** - Provides graceful degradation

## Patterns

### 1. Circuit Breaker

Protects against cascading failures by stopping requests to a failing service.

**States:**
- `Closed`: Normal operation (requests pass through)
- `Open`: Service failing (reject requests immediately)
- `HalfOpen`: Testing recovery (limited requests allowed)

**Example:**
```verum
let cb = CircuitBreaker.new(5, 3, 30000);
// Opens after 5 failures
// Closes after 3 successes in HalfOpen
// Waits 30 seconds before trying HalfOpen

let (result, updated_cb) = execute_with_circuit_breaker(
    cb,
    || Database.query("SELECT * FROM users"),
    || Result.Err(RegistryError.service_unavailable("Circuit open"))
);
```

**When to Use:**
- Calling external services
- Database connections
- Any operation that can fail repeatedly
- When you want to prevent resource exhaustion

**Metrics:**
- Current state (Closed/Open/HalfOpen)
- Failure count
- Success count
- Time since last failure

### 2. Retry with Exponential Backoff

Automatically retries failed operations with increasing delays.

**Features:**
- Exponential backoff: delay = initial × multiplier^attempt
- Configurable maximum delay
- Optional jitter to prevent thundering herd
- Selective retry based on error type

**Example:**
```verum
let result = with_retry(
    || ExternalApi.call(),
    RetryConfig {
        max_attempts: 3,
        initial_delay_ms: 100,
        max_delay_ms: 10000,
        multiplier: 2.0,
        jitter: true,
    },
    |err| err.is_recoverable()
);

// Delays: 100ms, 200ms, 400ms (with jitter)
```

**Retry Delays:**
```
Attempt 1: 100ms
Attempt 2: 200ms (100 × 2^1)
Attempt 3: 400ms (100 × 2^2)
Attempt 4: 800ms (100 × 2^3)
```

**Pre-configured Settings:**
- `RetryConfig.default()`: 3 attempts, 100ms-10s, 2x multiplier
- `RetryConfig.conservative()`: 5 attempts, 500ms-30s, 2x multiplier
- `RetryConfig.aggressive()`: 3 attempts, 50ms-1s, 1.5x multiplier

**When to Use:**
- Network operations
- Transient failures
- Rate-limited APIs
- Any operation that might succeed on retry

### 3. Timeout

Prevents operations from blocking indefinitely.

**Example:**
```verum
let result = with_timeout(
    || Database.long_query(),
    5000  // 5 second timeout
).await;

match result {
    Result.Ok(data) => // Process data
    Result.Err(err) => // Handle timeout or error
}
```

**Adaptive Timeout:**
```verum
let mut adaptive = AdaptiveTimeout.new(1000, 0.95);  // Base 1s, P95

let (result, updated_adaptive) = adaptive.execute(
    || Database.query()
).await;

// Timeout automatically adjusts based on historical performance
```

**When to Use:**
- All external service calls
- Database queries
- File I/O operations
- Any operation that might hang

**Best Practices:**
- Set timeout < SLA requirement
- Use adaptive timeouts for variable latency
- Log timeout events for monitoring

### 4. Bulkhead

Isolates resources to prevent one failing component from exhausting system resources.

**Example:**
```verum
let bulkhead = Bulkhead.new(10, 100);
// Max 10 concurrent operations
// Queue up to 100 waiting requests

let (result, updated_bulkhead) = with_bulkhead(
    bulkhead,
    || Database.query("SELECT * FROM packages")
).await;
```

**Behavior:**
- **Below capacity**: Permits granted immediately
- **At capacity**: Requests queued (up to queue_size)
- **Queue full**: Requests rejected with error

**Pre-configured Bulkheads:**
```verum
database_bulkhead()      // 10 concurrent, 50 queue
api_bulkhead()          // 5 concurrent, 100 queue
io_bulkhead()           // 20 concurrent, 100 queue
cpu_bulkhead()          // CPU cores × 1, CPU cores × 2 queue
```

**When to Use:**
- Limiting database connections
- Throttling external API calls
- Preventing thread pool exhaustion
- Isolating different operation types

**Metrics:**
- Current active operations
- Queue depth
- Total acquired/rejected
- Utilization percentage

### 5. Fallback

Provides alternative operations when primary fails.

**Example:**
```verum
let result = with_fallback(
    || Database.get_package(name),
    |err| Cache.get_package(name)
);
```

**Fallback Chain:**
```verum
let result = with_fallback_chain([
    || Database.get_user(id),        // Try primary
    || ReplicaDb.get_user(id),       // Try replica
    || Cache.get_user(id),           // Try cache
    || Result.Ok(User.guest())       // Return default
]);
```

**Conditional Fallback:**
```verum
let result = with_conditional_fallback(
    || Database.get_package(name),
    |err| err.is_recoverable(),      // Only fallback for recoverable errors
    |err| Cache.get_package(name)
);
```

**When to Use:**
- Cache-aside pattern
- Primary/replica failover
- Default values when service unavailable
- Degraded mode operations

**Common Patterns:**
- Database → Cache
- Primary → Replica
- Remote → Local
- Live → Static

## Composing Patterns

Patterns are designed to compose together for comprehensive protection:

```verum
let db_circuit = CircuitBreaker.new(5, 3, 30000);
let db_bulkhead = Bulkhead.new(10, 50);

pub async fn get_package_resilient(name: Text) -> Result<PackageDto, RegistryError>
    using [Database, Cache]
{
    // 1. Check circuit breaker
    if !db_circuit.should_allow() {
        return with_fallback(
            || Cache.get(f"pkg:{name}"),
            |_| Result.Err(RegistryError.service_unavailable("Circuit open"))
        );
    }

    // 2. Apply bulkhead + retry + timeout
    let (result, updated_bulkhead) = with_bulkhead(
        db_bulkhead,
        || with_retry(
            || with_timeout(
                || Database.fetch_package(name),
                5000  // 5 second timeout
            ),
            RetryConfig.aggressive(),
            |err| err.is_recoverable()
        )
    ).await;

    // 3. Update circuit breaker based on result
    match result {
        Result.Ok(pkg) => {
            db_circuit = db_circuit.record_success();
            Result.Ok(pkg)
        },
        Result.Err(err) => {
            db_circuit = db_circuit.record_failure();

            // 4. Fallback to cache
            with_fallback(
                || Cache.get(f"pkg:{name}"),
                |_| Result.Err(err)
            )
        }
    }
}
```

### Recommended Composition Order

1. **Circuit Breaker** - First check (fail fast if open)
2. **Bulkhead** - Limit concurrency
3. **Timeout** - Prevent blocking
4. **Retry** - Handle transient failures
5. **Fallback** - Last resort

## Comprehensive Resilience Configuration

Use `ResilienceConfig` for declarative configuration:

```verum
let config = ResilienceConfig.new()
    .with_circuit_breaker(CircuitBreaker.new(5, 3, 30000))
    .with_retry(RetryConfig.default())
    .with_timeout(5000)
    .with_bulkhead(database_bulkhead())
    .with_fallback(|err| Cache.get(key));

let result = execute_resilient(config, || Database.query()).await;
```

**Pre-configured Settings:**
```verum
ResilienceConfig.database_default()  // Database operations
ResilienceConfig.api_default()       // External API calls
ResilienceConfig.cache_default()     // Cache operations
```

## Monitoring and Metrics

All patterns provide metrics for observability:

### Circuit Breaker Metrics
```verum
let metrics = circuit_breaker.metrics();
// CircuitBreakerMetrics {
//     state: CircuitState.Closed,
//     failure_count: 0,
//     success_count: 42,
//     time_since_last_failure_ms: 30000
// }
```

### Retry Statistics
```verum
let stats = RetryStats.new()
    .record_success()
    .record_failure();

stats.success_rate();  // 0.5 (50%)
stats.average_delay_ms();  // 150ms
```

### Timeout Statistics
```verum
let stats = TimeoutStats.new()
    .record_success(100)
    .record_timeout();

stats.timeout_rate();  // 0.5 (50%)
stats.average_duration_ms();  // 100ms
```

### Bulkhead Statistics
```verum
let stats = bulkhead.stats();
// BulkheadStats {
//     current_count: 5,
//     queued_count: 10,
//     total_acquired: 100,
//     total_rejected: 5
// }

stats.utilization();  // 0.5 (50% capacity)
stats.rejection_rate();  // 0.05 (5%)
```

## Best Practices

### 1. Choose Appropriate Timeouts
- **Cache**: 100-500ms
- **Database**: 1-5s
- **External API**: 5-30s
- **Background Job**: 60s+

### 2. Circuit Breaker Thresholds
- **Conservative**: 10+ failures, useful for non-critical paths
- **Moderate**: 5 failures (recommended default)
- **Aggressive**: 3 failures, for critical or expensive operations

### 3. Retry Strategy
- **Transient errors**: Always retry (network, timeout)
- **Client errors**: Never retry (validation, auth)
- **Server errors**: Conditionally retry (based on idempotency)

### 4. Bulkhead Sizing
- **Database**: Limit to connection pool size ÷ 2
- **External API**: Based on rate limits
- **CPU-bound**: Number of CPU cores
- **I/O-bound**: 2-3× CPU cores

### 5. Fallback Design
- **Fast**: Fallback should be faster than primary
- **Safe**: Return safe defaults, never fail
- **Stale**: Stale data better than no data
- **Limited**: Clearly indicate degraded mode

## Error Handling

All patterns use `RegistryError` for consistency:

```verum
pub type RegistryError is
    | PackageNotFound { name: Text }
    | DatabaseError { message: Text }
    | NetworkError { message: Text }
    | InternalError { message: Text }
    | ...;

implement RegistryError {
    pub fn is_recoverable(self) -> Bool {
        match self {
            RegistryError.NetworkError { _ } => true,
            RegistryError.DatabaseError { _ } => true,
            RegistryError.StorageError { _ } => true,
            _ => false
        }
    }
}
```

## Testing

Test resilience patterns with controlled failures:

```verum
// Test circuit breaker opens after threshold
let mut cb = CircuitBreaker.new(3, 2, 1000);

for i in 1..5 {
    cb = cb.record_failure();
}

assert_eq!(cb.get_state(), CircuitState.Open);

// Test retry with mock that fails N times
let mut attempts = 0;
let result = with_retry(
    || {
        attempts = attempts + 1;
        if attempts < 3 {
            Result.Err(RegistryError.network_error("Transient"))
        } else {
            Result.Ok("Success")
        }
    },
    RetryConfig.default(),
    |err| true
);

assert_eq!(result, Result.Ok("Success"));
assert_eq!(attempts, 3);
```

## Performance Impact

| Pattern | Overhead | When to Use |
|---------|----------|-------------|
| Circuit Breaker | ~10ns | Always (negligible) |
| Retry | Delay × attempts | Transient failures |
| Timeout | ~100ns | All external calls |
| Bulkhead | ~50ns | Resource protection |
| Fallback | Operation cost | Critical paths |

## Migration Guide

### Before
```verum
pub async fn get_package(name: Text) -> Result<PackageDto, RegistryError>
    using [Database]
{
    Database.fetch_package(name).await
}
```

### After (Basic)
```verum
pub async fn get_package(name: Text) -> Result<PackageDto, RegistryError>
    using [Database]
{
    with_timeout(
        || Database.fetch_package(name),
        5000
    ).await
}
```

### After (Comprehensive)
```verum
pub async fn get_package(name: Text) -> Result<PackageDto, RegistryError>
    using [Database, Cache]
{
    let config = ResilienceConfig.database_default()
        .with_fallback(|_| Cache.get(name));

    execute_resilient(
        config,
        || Database.fetch_package(name)
    ).await
}
```

## References

- Martin Fowler - [CircuitBreaker](https://martinfowler.com/bliki/CircuitBreaker.html)
- Microsoft - [Retry Pattern](https://docs.microsoft.com/en-us/azure/architecture/patterns/retry)
- Netflix - [Hystrix Design Principles](https://github.com/Netflix/Hystrix/wiki)
- Release It! - Michael Nygard (Book)
- Site Reliability Engineering - Google (Book)

## License

Part of the Verum Registry project.
