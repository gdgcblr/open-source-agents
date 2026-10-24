package com.example.payment;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

public class PaymentServiceTest {

    @Test
    public void testHandlePayment() {
        PaymentClient client = new PaymentClient();
        PaymentService service = new PaymentService(client);
        assertNotNull(service.handlePayment("ORD-1", 10.0));
    }
}

