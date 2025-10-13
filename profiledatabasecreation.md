

1. Objective

Define the system behavior so that user profile information persists in MongoDB across sessions and remains intact even after browser cache is cleared.
Ensure that when a user logs in or registers, the system:
	•	Creates a MongoDB document for their profile (if it doesn’t exist).
	•	Automatically loads the stored profile data when visiting the profile page.
	•	Updates the existing document upon profile edits.
	•	Removes unnecessary personal ID fields (Mobile, Aadhar, PAN).

⸻

2. Problem Summary

Currently, the profile data is stored only in temporary client memory (local state).
When the browser cache is cleared or the user re-logs in, the profile fields are reset.
MongoDB is not storing profile metadata (beyond core credentials), causing the user to lose their entered data.

⸻

3. Requirements
	•	Persistent Storage: Profile data must be stored in MongoDB, linked to the existing user record.
	•	Database Schema Update: Extend the users collection to include:
	•	first_name
	•	last_name
	•	username
	•	email
	•	occupation
	•	bio
	•	Field Removal: Delete mobile_number, aadhar_number, and pan_number from both frontend UI and backend schema.
	•	Data Retrieval: When a user logs in or visits /profile, load their data from MongoDB via GET /api/auth/me.
	•	Data Update: On save, send data to backend via PUT /api/auth/profile and update MongoDB.
	•	Database Initialization: When a user account is created (via /api/auth/complete-registration), automatically initialize an empty profile document for them.
	•	Uniqueness Filter: MongoDB operations must identify users by either:
	•	email (primary)
	•	username (secondary)

⸻

4. Functional Flow

A. On Registration
	1.	User completes registration (/api/auth/complete-registration).
	2.	Backend creates user record in users collection.
	3.	Immediately initialize an empty profile document with:

{
  "first_name": "",
  "last_name": "",
  "email": "<user_email>",
  "username": "<username>",
  "occupation": "",
  "bio": "",
  "created_at": "<timestamp>",
  "updated_at": "<timestamp>"
}



B. On Login
	1.	User logs in and receives access + refresh tokens.
	2.	Frontend stores tokens and navigates to the Profile page.
	3.	React frontend calls:

api.get('/api/auth/me', { headers: { Authorization: `Bearer ${token}` }})


	4.	Flask fetches user data from MongoDB using get_user_by_id() and returns profile fields.

C. On Profile Update
	1.	User edits profile fields and clicks “Save”.
	2.	Frontend sends PUT /api/auth/profile with JSON body:

{
  "first_name": "Rudresh",
  "last_name": "Tiwari",
  "occupation": "Software Developer",
  "bio": "Building AI-powered finance solutions at WelthWest"
}


	3.	Flask verifies JWT → updates existing MongoDB document.
	4.	Returns updated user data → frontend updates UI immediately.

D. On Reload

When user revisits or reloads:
	•	/api/auth/me auto-loads persisted profile data.
	•	React populates fields from server response.

⸻

5. Database Schema

Collection: users

{
  "_id": ObjectId,
  "username": "rudresh",
  "email": "rudresh@example.com",
  "password": "<bcrypt hash>",
  "first_name": "Rudresh",
  "last_name": "Tiwari",
  "occupation": "Software Developer",
  "bio": "Building financial AI tools.",
  "created_at": "2025-10-13T13:30:00Z",
  "updated_at": "2025-10-13T13:35:00Z"
}

✅ Remove fields: mobile_number, aadhar_number, pan_number

⸻

6. Backend API Design

GET /api/auth/me

Purpose: Fetch current user profile.
Auth: @jwt_required()

Response:

{
  "user": {
    "email": "rudresh@example.com",
    "username": "rudresh",
    "first_name": "Rudresh",
    "last_name": "Tiwari",
    "occupation": "Developer",
    "bio": "Finance + AI enthusiast."
  }
}

PUT /api/auth/profile

Purpose: Update user profile.
Auth: @jwt_required()

Request:

{
  "first_name": "Rudresh",
  "last_name": "Tiwari",
  "occupation": "Engineer",
  "bio": "Love working on WelthWest."
}

Response:

{
  "message": "Profile updated successfully",
  "user": { ...updated profile data... }
}

Backend Implementation Notes
	•	Modify UserService → update_user_profile() to update only allowed fields.
	•	Use:

self.users.update_one({"_id": ObjectId(user_id)}, {"$set": update_data})


	•	On registration, after user insertion:

self.users.update_one({"_id": result.inserted_id}, {"$set": {"first_name": "", "last_name": "", "occupation": "", "bio": ""}})



⸻

7. Frontend Integration

Files to Modify
	•	src/pages/ProfilePage.tsx
	•	src/services/api.ts

Steps
	1.	Remove Fields:
	•	Delete input components for Mobile, Aadhar, PAN.
	2.	Auto Load Data:

useEffect(() => {
  api.get('/api/auth/me').then(res => setFormData(res.data.user));
}, []);


	3.	Save Profile:

const handleSave = async () => {
  const res = await api.put('/api/auth/profile', formData);
  toast.success(res.data.message);
};


	4.	TypeScript Interface:

interface UserProfile {
  first_name: string;
  last_name: string;
  email: string;
  username: string;
  occupation: string;
  bio: string;
}



⸻

8. Error Handling
	•	401 Unauthorized: Invalid or expired JWT → redirect to login.
	•	400 Bad Request: Missing fields or invalid data.
	•	500 Internal Server Error: Log MongoDB issues to console.

⸻

9. Security & Validation
	•	Sanitize and validate all input strings (bio, name, occupation).
	•	Restrict updateable fields to profile-only.
	•	Do not allow users to modify email, username, or _id.
	•	JWT-protected endpoints only.
	•	Use HTTPS for data in transit.

⸻

10. Testing Plan
	•	✅ Register new user → confirm database entry with empty profile fields.
	•	✅ Update profile → verify MongoDB document updates.
	•	✅ Log out / log back in → ensure data loads.
	•	✅ Clear browser cache → confirm persistence.
	•	✅ API returns correct profile JSON.

⸻

11. Future Enhancements
	
	•	Add preferences like theme or notification settings.
	•	Add audit trail for profile edits.

⸻

