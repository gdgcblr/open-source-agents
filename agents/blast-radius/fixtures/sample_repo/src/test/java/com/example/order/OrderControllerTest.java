package com.example.order;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

public class OrderControllerTest {

    @Test
    public void testSubmitOrderEndpoint() {
        PaymentClient paymentClient = new PaymentClient();
        OrderService orderService = new OrderService(paymentClient);
        OrderController controller = new OrderController(orderService);

        String res = controller.submitOrder("CUST-1", 100.0);
        assertNotNull(res);
    }
}

