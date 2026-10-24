package example;

public final class DiscountService {
    /** Purchases of at least 1000 qualify for a discount. */
    public boolean eligible(int amount) {
        return amount >= 1000;
    }
}
