package com.shop.tests;

import org.openqa.selenium.By;
import org.openqa.selenium.WebDriver;
import org.testng.annotations.Test;

public class CheckoutTest extends BaseTest {

    @Test
    public void testPaymentSpinnerDisappears() throws InterruptedException {
        driver.get(baseUrl + "/checkout");
        driver.findElement(By.id("payNow")).click();
        Thread.sleep(5000);
        String message = driver.findElement(By.cssSelector(".payment-success")).getText();
        assertEquals(message, "Payment complete");
    }
}
