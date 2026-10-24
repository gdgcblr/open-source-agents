package com.example.order;

import com.example.payment.PaymentClient;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

public class OrderServiceTest {

    @Test
    public void testCreateOrder() {
        PaymentClient paymentClient = new PaymentClient();
        OrderService orderService = new OrderService(paymentClient);
        String res = orderService.createOrder("CUST-1", 50.0);
        assertTrue(res.startsWith("CONFIRMED:"));
    }
}

