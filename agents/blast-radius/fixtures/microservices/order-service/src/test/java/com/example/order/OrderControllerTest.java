package com.example.order;

import com.example.payment.PaymentClient;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

public class OrderControllerTest {

    @Test
    public void testSubmitOrderEndpoint() {
        PaymentClient paymentClient = new PaymentClient();
        OrderService orderService = new OrderService(paymentClient);
        OrderController controller = new OrderController(orderService);
        assertNotNull(controller.submitOrder("CUST-1", 10.0));
    }
}

