import streamlit as st
import pandas as pd
from weather_agent_node import GlobalEventPlannerAgent

# Page Config
st.set_page_config(
    page_title="Global Outdoor Event Planner Agent",
    page_icon="🌍",
    layout="wide"
)

# Sidebar Options & Theme Toggle
st.sidebar.title("⚙️ Dashboard Controls")
theme = st.sidebar.radio("🎨 Select App Theme Mode:", ["Light Mode ☀️", "Dark Mode 🌙"])

# Robust Theme Injection Styles ensuring explicit text visibility
if theme == "Dark Mode 🌙":
    st.markdown("""
        <style>
        .stApp { 
            background-color: #0E1117 !important; 
            color: #FAFAFA !important; 
        }
        p, span, label, div, h1, h2, h3, h4, h5, h6 { 
            color: #FAFAFA !important; 
        }
        .stMetric {
            background-color: #1E222D !important;
            padding: 15px;
            border-radius: 10px;
            border: 1px solid #313745;
        }
        </style>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
        <style>
        .stApp { 
            background-color: #FFFFFF !important; 
            color: #111111 !important; 
        }
        p, span, label, div, h1, h2, h3, h4, h5, h6 { 
            color: #111111 !important; 
        }
        .stMetric {
            background-color: #F8F9FA !important;
            padding: 15px;
            border-radius: 10px;
            border: 1px solid #E9ECEF;
        }
        </style>
    """, unsafe_allow_html=True)

# Main Title & Contributor Header
st.title("🌍 Global Outdoor Event Planner Agent")
st.caption("AI Agent Tooling with Real-Time Meteorological & Air Quality (AQI) Telemetry Analysis")
st.markdown("👨‍💻 **Contributor:** **Sheetal G.** | *Enterprise AI & Agentic Architect*")
st.markdown("---")

# City Selector Sidebar
st.sidebar.subheader("🎯 Location Parameters")
selected_cities = st.sidebar.multiselect(
    "Select Target Event Cities:",
    options=[
        "Bengaluru", "Tokyo", "Barcelona", "San Francisco", "London", 
        "Sydney", "Singapore", "New York", "Paris", "Berlin", "Dubai"
    ],
    default=["Bengaluru", "Tokyo", "Barcelona", "San Francisco"]
)

custom_city = st.sidebar.text_input("Add a custom city on the fly:")
if custom_city and custom_city not in selected_cities:
    selected_cities.append(custom_city)

# Run Agent Workflow
if st.button("🚀 Execute Weather & AQI Agent Check", type="primary"):
    if not selected_cities:
        st.warning("Please select at least one city to analyze.")
    else:
        with st.spinner("🤖 Agent fetching real-time weather & AQI telemetry across global hubs..."):
            agent = GlobalEventPlannerAgent(target_cities=selected_cities)
            result = agent.execute_workflow()

        st.subheader("📌 Decision Summary")
        col1, col2, col3 = st.columns(3)
        
        col1.metric("Cities Analyzed", result["total_analyzed"])
        col2.metric("Greenlit Venues", result["shortlisted_count"])
        col3.metric("Pass Rate", f"{(result['shortlisted_count']/result['total_analyzed'])*100:.0f}%")

        if result["top_candidates"]:
            st.success(f"✅ **Recommended Outdoor Event Locations:** {', '.join(result['top_candidates'])}")
        else:
            st.warning("⚠️ No cities currently pass all outdoor weather and AQI standards. Review indoor backup options below.")

        st.markdown("---")
        st.subheader("📊 Detailed Telemetry, Air Quality & Venue Recommendations")
        
        for item in result["detailed_telemetry"]:
            if "error" in item:
                st.error(f"❌ {item['city']}: {item['error']}")
                continue

            status_icon = "✅ OUTDOOR APPROVED" if item["outdoor_event_suitable"] else "❌ OUTDOOR FLAGGED"
            
            with st.expander(f"{status_icon} — {item['city']}", expanded=True):
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Temperature", f"{item['temperature_celsius']} °C")
                c2.metric("Precipitation", f"{item['precipitation_mm']} mm")
                c3.metric("Wind Speed", f"{item['wind_speed_kmh']} km/h")
                c4.metric("US AQI (PM2.5)", f"{item['us_aqi']} AQI ({item['pm2_5']} µg/m³)")

                st.markdown(f"**Condition:** `{item['condition']}`")
                st.markdown(f"**Agent Diagnostics:** {item['recommendation_reason']}")
                
                if not item["outdoor_event_suitable"]:
                    st.info(f"🏛️ **Venue Backup Suggestion:** {item['venue_backup_suggestion']}")

        with st.expander("🔍 View Raw Agent Output Payload"):
            st.json(result)