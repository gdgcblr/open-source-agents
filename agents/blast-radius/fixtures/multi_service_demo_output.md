# 🌐 Multi-Service BlastRadius: Cross-Service Change Impact Report

> Pull Request impact analysis initiated on primary service: `payment-service`

## Executive Multi-Service Summary

- **Global Cross-Service Risk**: 🟠 **HIGH RISK** (Score: `75/100`)
- **Primary Modified Service**: `payment-service`
- **Impacted Downstream Services (1)**: `order-service`
- **Unaffected Neighbour Services (1)**: `inventory-service`

### Risk Assessment Rationale
- PR modifies `1` method(s) in `payment-service`.
- Downstream service impact detected: 1 neighbouring service(s) (order-service) call modified methods.

## 🏢 Microservice Ecosystem Impact Matrix

| Microservice | Relationship | Status | Risk Level | Callers Found | Tests Impacted |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `payment-service` | 🎯 Target (Modified) | ⚠️ Impacted | **HIGH** | `1` | `1` |
| `order-service` | 📡 Downstream Neighbour | ⚠️ Impacted | **HIGH** | `1` | `1` |
| `inventory-service` | 📡 Downstream Neighbour | ✅ Unaffected | **NONE** | `0` | `0` |

## 🔍 Service Impact Details

### Service: `payment-service` (HIGH Risk)

- Primary service where PR was raised. 1 method(s) modified.

**Discovered Invocations:**
- [⚙️ Production] `src/main/java/com/example/payment/PaymentService.java#L12` (`PaymentService#handlePayment`): `return client.processPayment(orderId, amt, "USD");`

**Recommended Selective Tests to Run:**
- `PaymentServiceTest#testHandlePayment`: Tests direct caller `PaymentService#handlePayment` (invoked at line 12)

```bash
# In payment-service directory:
mvn test -Dtest=PaymentServiceTest#testHandlePayment
```

### Service: `order-service` (HIGH Risk)

- Found 1 production call site(s) and 0 test call site(s) referencing changed methods.

**Discovered Invocations:**
- [⚙️ Production] `src/main/java/com/example/order/OrderService.java#L14` (`OrderService#createOrder`): `String txId = paymentClient.processPayment("ORD-1", totalAmount, "USD");`

**Recommended Selective Tests to Run:**
- `OrderServiceTest#testCreateOrder`: Tests direct caller `OrderService#createOrder` (invoked at line 13)

```bash
# In order-service directory:
mvn test -Dtest=OrderServiceTest#testCreateOrder
```

## ⚠️ Multi-Service Boundaries & Verification Notes

- Service agents independently analyzed their local ASTs against the public API signatures exported by the target service.
- Asynchronous event contracts (e.g. Kafka/RabbitMQ) and runtime schema registries should be validated alongside HTTP/Feign clients.