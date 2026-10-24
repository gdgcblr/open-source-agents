package com.example.order;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

public class OrderServiceTest {

    @Test
    public void testCreateOrderSuccess() {
        PaymentClient paymentClient = new PaymentClient();
        OrderService orderService = new OrderService(paymentClient);
        String confirmation = orderService.createOrder("CUST-101", 50.0);
        assertNotNull(confirmation);
        assertTrue(confirmation.startsWith("ORDER-CONFIRMED:"));
    }

    @Test
    public void testValidateOrderInvalid() {
        PaymentClient paymentClient = new PaymentClient();
        OrderService orderService = new OrderService(paymentClient);
        assertThrows(IllegalArgumentException.class, () -> {
            orderService.validateOrder(0.5);
        });
    }

    @Test
    public void testCancelOrder() {
        PaymentClient paymentClient = new PaymentClient();
        OrderService orderService = new OrderService(paymentClient);
        boolean result = orderService.cancelOrder("ORD-999");
        assertTrue(result);
    }
}

