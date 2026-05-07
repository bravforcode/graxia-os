#!/bin/bash
# Security Audit Script for Graxia OS

set -e

echo "🔒 Starting Security Audit for Graxia OS..."
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 1. Check for exposed secrets
echo "1️⃣ Checking for exposed secrets..."
if grep -r "password.*=.*['\"]" backend/app/ --include="*.py" | grep -v "hashed_password" | grep -v "POSTGRES_PASSWORD" | grep -v "test"; then
    echo -e "${RED}⚠️  Found potential hardcoded passwords${NC}"
else
    echo -e "${GREEN}✅ No hardcoded passwords found${NC}"
fi
echo ""

# 2. Check for SQL injection vulnerabilities
echo "2️⃣ Checking for SQL injection vulnerabilities..."
if grep -r "execute.*f\"" backend/app/ --include="*.py" | grep -v "# safe"; then
    echo -e "${YELLOW}⚠️  Found potential SQL injection points (f-strings in execute)${NC}"
else
    echo -e "${GREEN}✅ No obvious SQL injection vulnerabilities${NC}"
fi
echo ""

# 3. Check for missing input validation
echo "3️⃣ Checking API endpoints for input validation..."
ENDPOINTS_WITHOUT_VALIDATION=$(grep -r "@router\." backend/app/api/ --include="*.py" -A 5 | grep -v "Depends\|BaseModel\|Query\|Path" | grep "async def" | wc -l)
echo -e "${YELLOW}ℹ️  Found $ENDPOINTS_WITHOUT_VALIDATION potential endpoints without explicit validation${NC}"
echo ""

# 4. Check for CORS configuration
echo "4️⃣ Checking CORS configuration..."
if grep -r "allow_origins=\[\"*\"\]" backend/ --include="*.py"; then
    echo -e "${RED}⚠️  CORS allows all origins (*)${NC}"
else
    echo -e "${GREEN}✅ CORS configuration looks restrictive${NC}"
fi
echo ""

# 5. Check for debug mode in production
echo "5️⃣ Checking for debug mode..."
if grep -r "debug=True" backend/ --include="*.py" | grep -v "test\|# "; then
    echo -e "${RED}⚠️  Debug mode enabled${NC}"
else
    echo -e "${GREEN}✅ No debug mode found${NC}"
fi
echo ""

# 6. Check environment variables
echo "6️⃣ Checking environment variable usage..."
if [ -f ".env" ]; then
    if grep -q "changeme\|password123\|secret123" .env; then
        echo -e "${RED}⚠️  Default/weak credentials found in .env${NC}"
    else
        echo -e "${GREEN}✅ No obvious weak credentials in .env${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  No .env file found${NC}"
fi
echo ""

# 7. Check for rate limiting
echo "7️⃣ Checking rate limiting implementation..."
if grep -r "RateLimitMiddleware" backend/app/ --include="*.py"; then
    echo -e "${GREEN}✅ Rate limiting middleware found${NC}"
else
    echo -e "${RED}⚠️  No rate limiting found${NC}"
fi
echo ""

# 8. Check for authentication
echo "8️⃣ Checking authentication implementation..."
if grep -r "AuthMiddleware\|Depends.*get_current_user" backend/app/ --include="*.py" | head -1; then
    echo -e "${GREEN}✅ Authentication middleware found${NC}"
else
    echo -e "${YELLOW}⚠️  Authentication implementation unclear${NC}"
fi
echo ""

# 9. Check for HTTPS enforcement
echo "9️⃣ Checking HTTPS enforcement..."
if grep -r "COOKIE_SECURE.*True" backend/ --include="*.py"; then
    echo -e "${GREEN}✅ Secure cookies enabled${NC}"
else
    echo -e "${YELLOW}⚠️  Secure cookies not enforced${NC}"
fi
echo ""

# 10. Check dependencies for known vulnerabilities
echo "🔟 Checking Python dependencies..."
if command -v safety &> /dev/null; then
    cd backend
    safety check --json || echo -e "${YELLOW}⚠️  Some vulnerabilities found${NC}"
    cd ..
else
    echo -e "${YELLOW}ℹ️  'safety' not installed. Install with: pip install safety${NC}"
fi
echo ""

# Summary
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔒 Security Audit Complete"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📋 Recommendations:"
echo "1. Review all warnings above"
echo "2. Run: pip install safety && safety check"
echo "3. Run: pip install bandit && bandit -r backend/app/"
echo "4. Enable HTTPS in production"
echo "5. Use strong secrets in production"
echo ""
