# Debugging Admin 403 Forbidden Error

## Current Status
- ✅ User `test1112@email.com` has admin role in database
- ❌ Getting 403 Forbidden when calling admin endpoints
- User ID: `6903a168fd1481a618e04a62`

---

## Quick Fix Steps

### Step 1: Restart Server
The enhanced logging has been added. Restart your Flask server:

```bash
cd WelthWestServer_sharing_
python3 server.py
```

### Step 2: Run Test Script
```bash
python3 test_admin_auth.py
```

Enter your password when prompted. This will test the full flow and show you exactly where it's failing.

### Step 3: Check Server Logs

Look for these log lines:

**Success Pattern:**
```
INFO - Admin check for user_id: 6903a168fd1481a618e04a62
INFO - User 6903a168fd1481a618e04a62 has role: admin
INFO - Admin access granted for user 6903a168fd1481a618e04a62
```

**Failure Patterns:**

**Pattern A: User not found**
```
INFO - Admin check for user_id: 6903a168fd1481a618e04a62
WARNING - User not found with ID: 6903a168fd1481a618e04a62
```
**Solution:** JWT token contains wrong user ID

**Pattern B: Wrong role**
```
INFO - Admin check for user_id: 6903a168fd1481a618e04a62
INFO - User 6903a168fd1481a618e04a62 has role: user
WARNING - User 6903a168fd1481a618e04a62 attempted admin action with role: user
```
**Solution:** Run `python3 make_admin.py test1112@email.com` again

**Pattern C: Invalid ObjectId**
```
INFO - Admin check for user_id: some_email@email.com
ERROR - Error converting user_id to ObjectId: ...
```
**Solution:** JWT is storing email instead of user ID

---

## Manual Testing with Postman

### 1. Login

**POST** `http://localhost:5000/api/auth/login`

**Body:**
```json
{
  "username_or_email": "test1112@email.com",
  "password": "your_password"
}
```

**Response:**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJh...",
  "user": {
    "id": "6903a168fd1481a618e04a62",
    ...
  }
}
```

**IMPORTANT:** Check if the response contains `user.id` or `user_id`. Save this value.

### 2. Test Manual Credit

**POST** `http://localhost:5000/api/admin/manual-credit`

**Headers:**
```
Authorization: Bearer YOUR_ACCESS_TOKEN
Content-Type: application/json
```

**Body:**
```json
{
  "user_id": "6903a168fd1481a618e04a62",
  "plan": "PRO",
  "duration": "monthly",
  "note": "Testing"
}
```

**Check:**
1. What HTTP status code did you get?
2. What's in the response body?
3. What's in the server logs?

---

## Common Issues & Solutions

### Issue 1: JWT stores email instead of user ID

**Symptom:** Server logs show:
```
ERROR - Error converting user_id to ObjectId: 'test1112@email.com' is not a valid ObjectId
```

**Solution:** Check your user_service.py login function. It should store ObjectId string, not email:

```python
# ❌ Wrong
access_token = create_access_token(identity=user['email'])

# ✅ Correct
access_token = create_access_token(identity=str(user['_id']))
```

### Issue 2: User ID format mismatch

**Symptom:** User not found even though it exists

**Solution:** Check if the JWT identity is a string representation of ObjectId:

```bash
python3 -c "
from flask_jwt_extended import decode_token
token = 'YOUR_ACCESS_TOKEN_HERE'
decoded = decode_token(token)
print(decoded['sub'])  # Should be: 6903a168fd1481a618e04a62
"
```

### Issue 3: Role not set correctly

**Symptom:** Server logs show `role: user` or `role: NOT SET`

**Solution:** Run the admin script again:
```bash
python3 make_admin.py test1112@email.com
```

---

## Step-by-Step Debug Process

### 1. Verify Database
```bash
mongo
use welthwest
db.users.findOne({ email: "test1112@email.com" }, { _id: 1, email: 1, role: 1 })
```

**Expected:**
```javascript
{
  "_id": ObjectId("6903a168fd1481a618e04a62"),
  "email": "test1112@email.com",
  "role": "admin"
}
```

### 2. Check JWT Token Content

Create a file `decode_jwt.py`:
```python
from flask_jwt_extended import decode_token
import sys

token = sys.argv[1] if len(sys.argv) > 1 else input("Enter JWT token: ")

try:
    decoded = decode_token(token)
    print("JWT Contents:")
    print(f"  sub (identity): {decoded['sub']}")
    print(f"  type: {decoded.get('type')}")
    print(f"  exp: {decoded.get('exp')}")
except Exception as e:
    print(f"Error decoding: {e}")
```

Run:
```bash
python3 decode_jwt.py YOUR_ACCESS_TOKEN
```

**Expected output:**
```
JWT Contents:
  sub (identity): 6903a168fd1481a618e04a62
  type: access
  exp: 1234567890
```

### 3. Check Server Logs

While testing, watch server logs in real-time:
```bash
tail -f logs/server.log
# Or if logging to console, just watch the terminal
```

### 4. Test with Curl

```bash
# Login
curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username_or_email":"test1112@email.com","password":"YOUR_PASSWORD"}' \
  | jq .

# Save token from response

# Test admin endpoint
curl -X POST http://localhost:5000/api/admin/manual-credit \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "6903a168fd1481a618e04a62",
    "plan": "PRO",
    "duration": "monthly",
    "note": "Test"
  }' | jq .
```

---

## If Still Getting 403

### Check 1: JWT Secret Key
Make sure server hasn't been restarted with a different JWT_SECRET_KEY. Tokens signed with one key won't work with another.

**Solution:** Get a fresh token after server restart.

### Check 2: Token Expiration
JWT tokens expire. Default is 1 hour.

**Solution:** Login again to get a fresh token.

### Check 3: MongoDB Connection
Make sure the admin decorator is connecting to the same MongoDB instance.

**Verify:**
```python
python3 -c "
from config import get_config
print(get_config().MONGODB_URI)
print(get_config().DB_NAME)
"
```

### Check 4: Case Sensitivity
Check if email is exact match (case-sensitive):

```bash
mongo
use welthwest
db.users.find({ email: /test1112/i }, { email: 1, role: 1 })
```

---

## Expected Working Flow

```
1. User logs in with test1112@email.com
   ↓
2. Backend creates JWT with identity=user_id (ObjectId as string)
   ↓
3. User calls /api/admin/manual-credit with JWT
   ↓
4. admin_required decorator extracts user_id from JWT
   ↓
5. Looks up user in MongoDB by ObjectId(user_id)
   ↓
6. Checks if user.role == 'admin'
   ↓
7. If yes: Allows request
   If no: Returns 403
```

---

## Quick Test Commands

```bash
# 1. Verify admin in DB
mongo welthwest --eval "db.users.findOne({email:'test1112@email.com'}, {role:1})"

# 2. Re-apply admin (safe to run multiple times)
python3 make_admin.py test1112@email.com

# 3. Run comprehensive test
python3 test_admin_auth.py

# 4. Check server logs
grep -i "admin" server.log | tail -20
```

---

## Contact Support If

After trying all above steps, if you still get 403:

1. Save these outputs:
   - Server logs when calling admin endpoint
   - JWT token decode output
   - MongoDB user document
   - Full Postman request/response

2. Share the exact error message from server logs

The enhanced logging should now show exactly where it's failing!

---

**Note:** The server must be restarted after the middleware changes for the enhanced logging to take effect.
