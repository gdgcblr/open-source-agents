package com.shop.tests;

import org.openqa.selenium.By;
import org.testng.annotations.Test;

public class ProfileTest extends BaseTest {

    @Test
    public void testSaveProfileButtonClick() {
        driver.get(baseUrl + "/profile");
        driver.findElement(By.id("displayName")).sendKeys("QA User");
        driver.findElement(By.xpath("//div[3]/button[2]")).click();
    }
}
