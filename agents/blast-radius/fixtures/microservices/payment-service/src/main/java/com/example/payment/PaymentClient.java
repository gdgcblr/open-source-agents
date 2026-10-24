package com.example.payment;

public class PaymentClient {

    public String processPayment(String orderId, double amount, String currency) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Amount must be positive");
        }
        if (currency == null || currency.isBlank()) {
            throw new IllegalArgumentException("Currency must not be empty");
        }
        return "TX-" + orderId + "-" + System.currentTimeMillis();
    }

    public boolean refundPayment(String paymentId) {
        return paymentId != null;
    }
}

