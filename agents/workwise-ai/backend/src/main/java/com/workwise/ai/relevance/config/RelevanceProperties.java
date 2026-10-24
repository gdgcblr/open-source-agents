package com.workwise.ai.relevance.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "workwise.relevance")
public class RelevanceProperties {

    private Weights weights = new Weights();
    private double threshold = 40;

    public Weights getWeights() {
        return weights;
    }

    public void setWeights(Weights weights) {
        this.weights = weights;
    }

    public double getThreshold() {
        return threshold;
    }

    public void setThreshold(double threshold) {
        this.threshold = threshold;
    }

    public static class Weights {
        private double jobIndustry = 0.30;
        private double economic = 0.25;
        private double actionability = 0.20;
        private double location = 0.10;
        private double recency = 0.10;
        private double goalAlignment = 0.05;

        public double getJobIndustry() {
            return jobIndustry;
        }

        public void setJobIndustry(double jobIndustry) {
            this.jobIndustry = jobIndustry;
        }

        public double getEconomic() {
            return economic;
        }

        public void setEconomic(double economic) {
            this.economic = economic;
        }

        public double getActionability() {
            return actionability;
        }

        public void setActionability(double actionability) {
            this.actionability = actionability;
        }

        public double getLocation() {
            return location;
        }

        public void setLocation(double location) {
            this.location = location;
        }

        public double getRecency() {
            return recency;
        }

        public void setRecency(double recency) {
            this.recency = recency;
        }

        public double getGoalAlignment() {
            return goalAlignment;
        }

        public void setGoalAlignment(double goalAlignment) {
            this.goalAlignment = goalAlignment;
        }
    }
}
