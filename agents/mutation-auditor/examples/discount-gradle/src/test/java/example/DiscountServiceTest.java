package example;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class DiscountServiceTest {
    @Test void largePurchaseQualifies() { assertTrue(new DiscountService().eligible(1500)); }
    @Test void smallPurchaseDoesNotQualify() { assertFalse(new DiscountService().eligible(500)); }
    // Deliberately missing: the documented boundary at exactly 1000.
}
