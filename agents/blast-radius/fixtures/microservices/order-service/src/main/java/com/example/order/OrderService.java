package com.example.order;

import com.example.payment.PaymentClient;

public class OrderService {

    private final PaymentClient paymentClient;

    public OrderService(PaymentClient paymentClient) {
        this.paymentClient = paymentClient;
    }

    public String createOrder(String customerId, double totalAmount) {
        String txId = paymentClient.processPayment("ORD-1", totalAmount, "USD");
        return "CONFIRMED:" + txId;
    }
}

