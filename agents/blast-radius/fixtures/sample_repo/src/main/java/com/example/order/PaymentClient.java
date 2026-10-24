package com.example.order;

public class PaymentClient {

    public String processPayment(String orderId, double amount, String currency) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Payment amount must be greater than zero");
        }
        if (currency == null || currency.isBlank()) {
            throw new IllegalArgumentException("Currency must not be empty");
        }
        // Simulated HTTP payment gateway invocation
        return "PAY-" + orderId + "-" + System.currentTimeMillis();
    }

    public boolean refundPayment(String paymentId) {
        if (paymentId == null) {
            return false;
        }
        return true;
    }

    public String getPaymentStatus(String paymentId) {
        return "SUCCESS";
    }
}

