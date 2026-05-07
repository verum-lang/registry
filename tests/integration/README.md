# Verum Registry - Integration Tests

Comprehensive integration test suite for the verum-registry covering all API endpoints and functionality.

## Overview

This directory contains production-quality integration tests that verify the entire system works correctly end-to-end. Tests cover:

- Package lifecycle (publish, retrieve, update, yank)
- User authentication and management
- Token-based authorization
- Package ownership operations
- Administrative functions
- Resilience patterns (circuit breakers, retries, timeouts)
- Input validation

## Test Structure

```
integration/
├── package_tests.vr       # Package operations
├── user_tests.vr          # User management
├── auth_tests.vr          # Authentication & tokens
├── ownership_tests.vr     # Package ownership
├── admin_tests.vr         # Admin operations
├── resilience_tests.vr    # Resilience patterns
├── validation_tests.vr    # Input validation
└── mod.vr                 # Module exports
```

## Running Tests

```bash
# Run all integration tests
verum test tests/integration/

# Run specific test module
verum test tests/integration/package_tests.vr

# Run specific test
verum test tests/integration/package_tests.vr::test_package_publish_and_retrieve

# Run with verbose output
verum test tests/integration/ --verbose

# Run with coverage
verum test tests/integration/ --coverage
```

## Test Categories

### 1. Package Tests (`package_tests.vr`)

Tests the complete package lifecycle:

- **Publish and Retrieve**: Verify packages can be published and retrieved
- **Version Listing**: Test multiple version management
- **Download Counter**: Verify download statistics are tracked
- **Yank Prevention**: Test yanked versions cannot be downloaded
- **Metadata Updates**: Verify package metadata can be updated
- **Search**: Test package search functionality
- **Stats**: Verify download statistics

**Key Tests:**
- `test_package_publish_and_retrieve()`: End-to-end publish/retrieve
- `test_package_version_listing()`: Multiple version management
- `test_package_download_increments_counter()`: Download tracking
- `test_package_yank_prevents_download()`: Yank enforcement
- `test_package_search_pagination()`: Search with pagination

### 2. User Tests (`user_tests.vr`)

Tests user registration, login, and profile management:

- **Registration**: User creation with validation
- **Login**: Authentication with credentials
- **Profile Management**: Update user information
- **Public Profiles**: View public user data
- **Account Deletion**: Delete with package transfer

**Key Tests:**
- `test_user_registration_and_login()`: Complete auth flow
- `test_user_registration_duplicate_username()`: Uniqueness enforcement
- `test_user_profile_update()`: Profile modification
- `test_user_delete_account_with_package_transfer()`: Account cleanup

### 3. Authentication Tests (`auth_tests.vr`)

Tests token-based authentication:

- **Token Creation**: Generate API tokens
- **Token Usage**: Authenticate with tokens
- **Token Revocation**: Invalidate tokens
- **Token Expiration**: Time-based invalidation
- **Scopes**: Permission-based access

**Key Tests:**
- `test_token_creation_and_usage()`: Complete token lifecycle
- `test_token_revocation()`: Token invalidation
- `test_invalid_token_rejected()`: Security validation
- `test_token_with_scopes()`: Permission management

### 4. Ownership Tests (`ownership_tests.vr`)

Tests package ownership management:

- **Add Owners**: Grant ownership to users
- **Remove Owners**: Revoke ownership
- **Transfer**: Change primary owner
- **List Owners**: View package owners
- **Authorization**: Verify ownership permissions

**Key Tests:**
- `test_add_package_owner()`: Grant co-ownership
- `test_remove_package_owner()`: Revoke access
- `test_cannot_remove_last_owner()`: Protection against orphaned packages
- `test_transfer_ownership()`: Change ownership

### 5. Admin Tests (`admin_tests.vr`)

Tests administrative operations:

- **User Management**: Suspend/unsuspend users
- **Package Management**: Block/unblock packages
- **Statistics**: Registry-wide metrics
- **Listings**: Admin-level package/user views

**Key Tests:**
- `test_admin_can_suspend_user()`: User moderation
- `test_admin_can_block_package()`: Content moderation
- `test_registry_stats()`: Metrics collection
- `test_list_all_users_pagination()`: Admin views

### 6. Resilience Tests (`resilience_tests.vr`)

Tests fault tolerance patterns:

- **Circuit Breakers**: Failure detection and recovery
- **Retries**: Transient failure handling
- **Timeouts**: Hanging operation prevention
- **Fallbacks**: Degraded service responses

**Key Tests:**
- `test_circuit_breaker_opens_on_failures()`: Circuit protection
- `test_retry_succeeds_on_transient_failure()`: Retry logic
- `test_timeout_prevents_hanging()`: Timeout enforcement
- `test_fallback_on_primary_failure()`: Graceful degradation

### 7. Validation Tests (`validation_tests.vr`)

Tests input validation rules:

- **Package Names**: Format and length validation
- **Email Addresses**: RFC 5322 compliance
- **Semantic Versions**: SemVer format
- **URLs**: Protocol and format validation
- **Pagination**: Boundary checking

**Key Tests:**
- `test_package_name_validation()`: Name format rules
- `test_email_validation()`: Email format rules
- `test_version_validation()`: SemVer compliance
- `test_pagination_validation()`: Boundary checks

## Test Utilities

The `test_utils.vr` module provides shared helpers:

### Database Management
- `setup_test_db()`: Initialize clean test database
- `cleanup_test_db()`: Remove test data

### Fixtures
- `create_test_user(username)`: Generate test user
- `create_admin_user(username, email)`: Generate admin user
- `create_test_package(name, owner)`: Generate test package
- `publish_test_package(name, version, token)`: Publish package

### Assertions
- `assert_ok(result)`: Verify Result is Ok
- `assert_err(result)`: Verify Result is Err
- `assert_eq(actual, expected)`: Verify equality
- `assert_ne(actual, unexpected)`: Verify inequality

### Data Generation
- `random_string(length)`: Generate random text
- `random_email()`: Generate test email
- `random_package_name()`: Generate package name
- `generate_test_tarball()`: Create test artifact

### Failure Simulation
- `simulate_database_failure(should_fail)`: Inject DB failures
- `simulate_slow_operation(delay_ms)`: Inject delays
- `reset_failure_simulation()`: Clear injections

## Writing New Tests

### Test Structure

```verum
@test
fn test_descriptive_name() {
    // Setup
    setup_test_db();
    let user = create_test_user("testuser");

    // Exercise
    let result = operation_under_test(user).await;

    // Verify
    assert_ok(&result);
    assert_eq(&result.unwrap().field, &expected_value);

    // Cleanup
    cleanup_test_db();
}
```

### Best Practices

1. **Descriptive Names**: Use clear test names that describe what's tested
   - ✅ `test_package_yank_prevents_download()`
   - ❌ `test_yank()`

2. **Setup/Teardown**: Always call `setup_test_db()` and `cleanup_test_db()`

3. **Isolation**: Each test should be independent and not rely on other tests

4. **Assertions**: Use appropriate assertion helpers:
   ```verum
   assert_ok(&result);              // Verify success
   assert_err(&result);             // Verify failure
   assert_eq(&actual, &expected);   // Verify equality
   ```

5. **Error Matching**: Verify specific error types:
   ```verum
   match result {
       Result.Err(RegistryError.PackageNotFound { name }) => {
           assert_eq(&name, &"expected-name");
       },
       _ => panic("Expected PackageNotFound error"),
   }
   ```

6. **Both Paths**: Test both success and failure cases

7. **Edge Cases**: Include boundary conditions and special cases

## Test Coverage Goals

Target coverage levels:

- **Package Operations**: 95%+
- **User Management**: 95%+
- **Authentication**: 95%+
- **Validation**: 100% (all validation rules)
- **Admin Operations**: 90%+
- **Resilience**: 85%+ (may include integration with external services)

## CI/CD Integration

### GitHub Actions

```yaml
name: Integration Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Setup Verum
        run: curl -sSL https://install.vr.dev | sh
      - name: Run Integration Tests
        run: verum test tests/integration/ --coverage
      - name: Upload Coverage
        uses: codecov/codecov-action@v3
```

## Performance Benchmarks

Integration tests should complete within:

- Individual test: < 5 seconds
- Package tests: < 30 seconds
- User tests: < 20 seconds
- Auth tests: < 20 seconds
- Ownership tests: < 20 seconds
- Admin tests: < 25 seconds
- Resilience tests: < 30 seconds
- Validation tests: < 5 seconds
- **Total suite: < 3 minutes**

## Troubleshooting

### Tests Hanging

- Check for missing `cleanup_test_db()` calls
- Verify async operations have timeout
- Look for circular dependencies

### Flaky Tests

- Ensure test isolation (no shared state)
- Check for race conditions in async code
- Verify database is properly reset

### Database Connection Issues

- Verify test database is configured
- Check connection pool settings
- Ensure migrations are run

## Contributing

When adding new features:

1. Write integration tests first (TDD)
2. Cover both success and failure paths
3. Include edge cases and boundary conditions
4. Update this README with new test categories
5. Ensure tests pass before submitting PR

## References

- [Verum Testing Guide](../../docs/testing-guide.md)
- [Registry API Specification](../../docs/api-spec.md)
- [Domain Model](../../docs/domain-model.md)
- [Error Handling](../../docs/error-handling.md)
