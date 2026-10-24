package com.workwise.ai.outcomes.domain;

import com.workwise.ai.common.domain.BaseEntity;
import com.workwise.ai.strategies.domain.Strategy;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

import java.math.BigDecimal;
import java.time.LocalDate;

@Entity
@Table(name = "strategy_outcome")
public class StrategyOutcome extends BaseEntity {

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "strategy_id", nullable = false)
    private Strategy strategy;

    @Column(name = "date_started")
    private LocalDate dateStarted;

    @Column(name = "date_completed")
    private LocalDate dateCompleted;

    @Column(name = "actual_expenses", precision = 14, scale = 2)
    private BigDecimal actualExpenses;

    @Column(name = "actual_revenue", precision = 14, scale = 2)
    private BigDecimal actualRevenue;

    @Column(name = "time_spent_hours", precision = 10, scale = 2)
    private BigDecimal timeSpentHours;

    @Column(name = "orders_received")
    private Integer ordersReceived;

    @Column(name = "customers_acquired")
    private Integer customersAcquired;

    @Column(name = "user_reported_outcome", columnDefinition = "text")
    private String userReportedOutcome;

    @Column(name = "lessons_learned", columnDefinition = "text")
    private String lessonsLearned;

    @Column(name = "is_independently_verified", nullable = false)
    private boolean independentlyVerified = false;

    public Strategy getStrategy() {
        return strategy;
    }

    public void setStrategy(Strategy strategy) {
        this.strategy = strategy;
    }

    public LocalDate getDateStarted() {
        return dateStarted;
    }

    public void setDateStarted(LocalDate dateStarted) {
        this.dateStarted = dateStarted;
    }

    public LocalDate getDateCompleted() {
        return dateCompleted;
    }

    public void setDateCompleted(LocalDate dateCompleted) {
        this.dateCompleted = dateCompleted;
    }

    public BigDecimal getActualExpenses() {
        return actualExpenses;
    }

    public void setActualExpenses(BigDecimal actualExpenses) {
        this.actualExpenses = actualExpenses;
    }

    public BigDecimal getActualRevenue() {
        return actualRevenue;
    }

    public void setActualRevenue(BigDecimal actualRevenue) {
        this.actualRevenue = actualRevenue;
    }

    public BigDecimal getTimeSpentHours() {
        return timeSpentHours;
    }

    public void setTimeSpentHours(BigDecimal timeSpentHours) {
        this.timeSpentHours = timeSpentHours;
    }

    public Integer getOrdersReceived() {
        return ordersReceived;
    }

    public void setOrdersReceived(Integer ordersReceived) {
        this.ordersReceived = ordersReceived;
    }

    public Integer getCustomersAcquired() {
        return customersAcquired;
    }

    public void setCustomersAcquired(Integer customersAcquired) {
        this.customersAcquired = customersAcquired;
    }

    public String getUserReportedOutcome() {
        return userReportedOutcome;
    }

    public void setUserReportedOutcome(String userReportedOutcome) {
        this.userReportedOutcome = userReportedOutcome;
    }

    public String getLessonsLearned() {
        return lessonsLearned;
    }

    public void setLessonsLearned(String lessonsLearned) {
        this.lessonsLearned = lessonsLearned;
    }

    public boolean isIndependentlyVerified() {
        return independentlyVerified;
    }

    public void setIndependentlyVerified(boolean independentlyVerified) {
        this.independentlyVerified = independentlyVerified;
    }
}
