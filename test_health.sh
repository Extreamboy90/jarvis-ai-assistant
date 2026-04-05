#!/bin/bash
# Quick Health Plugin Test Script
# Tests all major endpoints without requiring Google Fit

set -e

USER="test_user"
BASE_URL="http://localhost:8000"
DATE=$(date +%Y-%m-%d)

echo "========================================"
echo "🏥 Health Plugin Test Suite"
echo "========================================"
echo ""
echo "Testing user: $USER"
echo "Date: $DATE"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

test_passed() {
    echo -e "${GREEN}✅ PASS${NC}: $1"
}

test_failed() {
    echo -e "${RED}❌ FAIL${NC}: $1"
    exit 1
}

# Test 1: Import mock data
echo "─────────────────────────────────────────"
echo "Test 1: Importing mock health data..."
echo "─────────────────────────────────────────"
RESPONSE=$(curl -s -X POST "$BASE_URL/health/$USER/import" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "'$USER'",
    "source": "generic",
    "file_content": "date,metric_type,value\n2026-03-30,steps,8523\n2026-03-30,calories,2100\n2026-03-30,sleep,7.5\n2026-03-30,heart_rate,68\n2026-03-29,steps,10234\n2026-03-29,calories,2300\n2026-03-29,sleep,8.2\n2026-03-29,heart_rate,65\n2026-03-28,steps,7891\n2026-03-28,sleep,6.7"
  }')

if echo "$RESPONSE" | grep -q '"success": true'; then
    test_passed "Data import"
    IMPORTED=$(echo "$RESPONSE" | grep -o '"data_points_imported": [0-9]*' | grep -o '[0-9]*')
    echo "   Imported: $IMPORTED data points"
else
    test_failed "Data import"
fi
echo ""

# Test 2: Set goals
echo "─────────────────────────────────────────"
echo "Test 2: Setting health goals..."
echo "─────────────────────────────────────────"
RESPONSE=$(curl -s -X POST "$BASE_URL/health/$USER/goals" \
  -H "Content-Type: application/json" \
  -d '{"steps": 10000, "sleep": 8, "workouts_per_week": 3}')

if echo "$RESPONSE" | grep -q '"success": true'; then
    test_passed "Set goals"
else
    test_failed "Set goals"
fi
echo ""

# Test 3: Get activity summary
echo "─────────────────────────────────────────"
echo "Test 3: Getting activity summary..."
echo "─────────────────────────────────────────"
RESPONSE=$(curl -s "$BASE_URL/health/$USER/activity?date=2026-03-30")

if echo "$RESPONSE" | grep -q '"success": true'; then
    test_passed "Activity summary"
    STEPS=$(echo "$RESPONSE" | grep -o '"steps": [0-9]*' | grep -o '[0-9]*')
    CALORIES=$(echo "$RESPONSE" | grep -o '"calories": [0-9]*' | grep -o '[0-9]*')
    echo "   Steps: $STEPS"
    echo "   Calories: $CALORIES"
else
    test_failed "Activity summary"
fi
echo ""

# Test 4: Sleep analysis
echo "─────────────────────────────────────────"
echo "Test 4: Analyzing sleep..."
echo "─────────────────────────────────────────"
RESPONSE=$(curl -s "$BASE_URL/health/$USER/sleep?days=3")

if echo "$RESPONSE" | grep -q '"success": true'; then
    test_passed "Sleep analysis"
    AVG_SLEEP=$(echo "$RESPONSE" | grep -o '"average_hours": [0-9.]*' | grep -o '[0-9.]*')
    QUALITY=$(echo "$RESPONSE" | grep -o '"quality_score": "[^"]*"' | grep -o '"[^"]*"' | tail -1 | tr -d '"')
    echo "   Average: ${AVG_SLEEP}h/night"
    echo "   Quality: $QUALITY"
else
    test_failed "Sleep analysis"
fi
echo ""

# Test 5: Heart rate trends
echo "─────────────────────────────────────────"
echo "Test 5: Checking heart rate trends..."
echo "─────────────────────────────────────────"
RESPONSE=$(curl -s "$BASE_URL/health/$USER/heart-rate?days=3")

if echo "$RESPONSE" | grep -q '"success": true'; then
    test_passed "Heart rate trends"
    AVG_HR=$(echo "$RESPONSE" | grep -o '"average_bpm": [0-9.]*' | grep -o '[0-9.]*')
    RESTING=$(echo "$RESPONSE" | grep -o '"resting_bpm": [0-9.]*' | grep -o '[0-9.]*')
    echo "   Average: ${AVG_HR} bpm"
    echo "   Resting: ${RESTING} bpm"
else
    test_failed "Heart rate trends"
fi
echo ""

# Test 6: Get goals
echo "─────────────────────────────────────────"
echo "Test 6: Retrieving goals..."
echo "─────────────────────────────────────────"
RESPONSE=$(curl -s "$BASE_URL/health/$USER/goals")

if echo "$RESPONSE" | grep -q '"success": true'; then
    test_passed "Get goals"
    GOAL_COUNT=$(echo "$RESPONSE" | grep -o '"goals":' | wc -l)
    echo "   Goals set: $GOAL_COUNT"
else
    test_failed "Get goals"
fi
echo ""

# Test 7: Workout suggestion
echo "─────────────────────────────────────────"
echo "Test 7: Getting workout suggestion..."
echo "─────────────────────────────────────────"
RESPONSE=$(curl -s "$BASE_URL/health/$USER/workout-suggestion")

if echo "$RESPONSE" | grep -q '"success": true'; then
    test_passed "Workout suggestion"
    echo "   ℹ️  Suggestion generated (check response for details)"
else
    test_failed "Workout suggestion"
fi
echo ""

# Test 8: Detect anomalies
echo "─────────────────────────────────────────"
echo "Test 8: Detecting anomalies..."
echo "─────────────────────────────────────────"
RESPONSE=$(curl -s "$BASE_URL/health/$USER/anomalies")

if echo "$RESPONSE" | grep -q '"success": true'; then
    test_passed "Anomaly detection"
    if echo "$RESPONSE" | grep -q '"anomalies_detected": true'; then
        ANOMALY_COUNT=$(echo "$RESPONSE" | grep -o '"count": [0-9]*' | grep -o '[0-9]*')
        echo "   ⚠️  Found $ANOMALY_COUNT anomalies"
    else
        echo "   ✓ No anomalies detected"
    fi
else
    test_failed "Anomaly detection"
fi
echo ""

# Test 9: Wellness report
echo "─────────────────────────────────────────"
echo "Test 9: Generating wellness report..."
echo "─────────────────────────────────────────"
RESPONSE=$(curl -s "$BASE_URL/health/$USER/wellness-report?period=week")

if echo "$RESPONSE" | grep -q '"success": true'; then
    test_passed "Wellness report"
    SCORE=$(echo "$RESPONSE" | grep -o '"overall_score": [0-9]*' | grep -o '[0-9]*')
    echo "   Overall Score: $SCORE/100"
else
    test_failed "Wellness report"
fi
echo ""

# Test 10: Track nutrition
echo "─────────────────────────────────────────"
echo "Test 10: Tracking nutrition..."
echo "─────────────────────────────────────────"
RESPONSE=$(curl -s -X POST "$BASE_URL/health/$USER/nutrition?meal_description=pasta+al+pomodoro+150g")

if echo "$RESPONSE" | grep -q '"success": true'; then
    test_passed "Nutrition tracking"
    CALORIES=$(echo "$RESPONSE" | grep -o '"calories": [0-9]*' | grep -o '[0-9]*' | head -1)
    echo "   Estimated calories: $CALORIES"
else
    test_failed "Nutrition tracking"
fi
echo ""

# Test 11: Health-memory correlations
echo "─────────────────────────────────────────"
echo "Test 11: Analyzing correlations..."
echo "─────────────────────────────────────────"
RESPONSE=$(curl -s "$BASE_URL/health/$USER/correlations?metric=all&days=3")

if echo "$RESPONSE" | grep -q '"success": true'; then
    test_passed "Correlations analysis"
    MEMORIES=$(echo "$RESPONSE" | grep -o '"memories_count": [0-9]*' | grep -o '[0-9]*')
    echo "   Memories analyzed: $MEMORIES"
else
    test_failed "Correlations analysis"
fi
echo ""

# Summary
echo "========================================"
echo "🎉 All Tests Passed!"
echo "========================================"
echo ""
echo "Plugin is working correctly."
echo ""
echo "Next steps:"
echo "  1. Setup Google Fit OAuth (optional)"
echo "  2. Read full docs: HEALTH_PLUGIN.md"
echo "  3. Try chat integration:"
echo "     curl -X POST '$BASE_URL/chat' \\"
echo "       -H 'Content-Type: application/json' \\"
echo "       -d '{\"message\":\"Come ho dormito?\",\"user_id\":\"$USER\"}'"
echo ""
