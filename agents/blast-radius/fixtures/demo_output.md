# 💥 BlastRadius: Change Impact Analysis Report

> Automated change impact assessment for target repository: `fixtures/sample_repo`

## Executive Summary

- **Overall Risk Rating**: 🟠 **HIGH RISK** (Score: `70/100`)
- **Changed Java Methods**: `1`
- **Discovered Direct Callers**: `1` (1 production, 0 tests)
- **Recommended Tests to Run**: `1`
- **Test Coverage Gaps**: `1` uncovered method(s)

### Risk Rationale
- 1 method(s) modified.
- 1 direct production caller(s) identified.
- Test coverage gap: No discoverable tests for changed method(s): `processPayment`.

## 🔍 Changed Methods & Direct Impact

| Modified Class | Method Signature | Lines | Return Type | Modifiers |
| :--- | :--- | :--- | :--- | :--- |
| `PaymentClient` | `processPayment(String orderId, double amount, String currency)` | `L5-L14` | `String` | `public` |

## 🌐 Discovered Direct Callers

| Target Method | Caller Location | Type | Invocations Code Snippet |
| :--- | :--- | :--- | :--- |
| `processPayment` | `src/main/java/com/example/order/OrderService.java#L13` (`OrderService#createOrder`) | ⚙️ Production | `String txId = paymentClient.processPayment("ORD-1", totalAmo...` |

## 🧪 Recommended Test Execution Plan

Execute these test targets to validate your changes before deployment:

| Priority | Test Target | Enclosing Test Method | Rationale |
| :--- | :--- | :--- | :--- |
| 🔴 High | `src/test/java/com/example/order/OrderServiceTest.java` | `testCreateOrderSuccess` | Tests direct caller `OrderService#createOrder` (invoked at line 12) |

### Suggested Maven Test Command
```bash
mvn test -Dtest=OrderServiceTest#testCreateOrderSuccess
```

## ⚠️ Test Coverage Gaps

The following modified methods currently lack direct or discoverable caller test coverage:

- **`com.example.order.PaymentClient#processPayment`** (`src/main/java/com/example/order/PaymentClient.java:L5-L14`)

*Recommendation: Add unit tests explicitly exercising the new or updated logic in these methods.*

## ⚠️ Limitations & Analysis Boundaries

To maintain technical honesty and predictable scope, note the following static analysis boundaries:
- Polymorphic Dispatch: Invocations made via shared interfaces with multiple implementations are identified by method name; bytecode classpath resolution is required to disambiguate dynamic runtime implementations.
- Framework Reflection & Dependency Injection: Spring Bean autowiring (@Autowired, @Resource, @Inject), Spring events (ApplicationEventPublisher), and reflective calls are not tracked as direct lexical invocations.
- External Microservice Boundaries: Remote RPC, REST, and messaging consumers (Kafka, RabbitMQ) across external microservice repositories cannot be discovered from local source code alone.
- Target Scope: Analysis is bounded to Java source files (.java) in the specified repository root.
