package com.example.payment;

public class PaymentService {

    private final PaymentClient client;

    public PaymentService(PaymentClient client) {
        this.client = client;
    }

    public String handlePayment(String orderId, double amt) {
        return client.processPayment(orderId, amt, "USD");
    }
}

