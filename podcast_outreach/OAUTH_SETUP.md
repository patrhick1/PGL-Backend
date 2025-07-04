# OAuth Setup Guide

This guide explains how to set up Google OAuth authentication for your application.

## Prerequisites

1. Google Cloud Console account
2. Your application running locally or on a server

## Setup Steps

### 1. Run Database Migration

First, run the migration script to add OAuth tables to your database:

```bash
cd podcast_outreach
python migrate_oauth_tables.py
```

### 2. Install Dependencies

Install the required cryptography package:

```bash
pip install -r requirements.txt
```

### 3. Configure Google OAuth

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable Google+ API:
   - Go to "APIs & Services" > "Library"
   - Search for "Google+ API"
   - Enable it

4. Create OAuth 2.0 credentials:
   - Go to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "OAuth 2.0 Client ID"
   - Configure OAuth consent screen first if prompted
   - Application type: "Web application"
   - Add authorized redirect URIs:
     - For development: `http://localhost:8000/auth/oauth/google/callback`
     - For production: `https://yourdomain.com/auth/oauth/google/callback`

5. Copy your Client ID and Client Secret

### 4. Configure Environment Variables

Add the following to your `.env` file:

```env
# Google OAuth
GOOGLE_CLIENT_ID=your_actual_google_client_id_here
GOOGLE_CLIENT_SECRET=your_actual_google_client_secret_here

# OAuth Security (generate these)
TOKEN_ENCRYPTION_KEY=use_this_command_to_generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
OAUTH_STATE_SECRET=use_this_command_to_generate: python -c "import secrets; print(secrets.token_urlsafe(32))"

# Backend URL
BACKEND_URL=http://localhost:8000  # Change for production
```

### 5. Frontend Integration

Add Google login button to your frontend:

```javascript
// Example login button handler
async function loginWithGoogle() {
    try {
        const response = await fetch('http://localhost:8000/auth/oauth/google/authorize');
        const data = await response.json();
        
        if (data.authorization_url) {
            // Redirect to Google
            window.location.href = data.authorization_url;
        }
    } catch (error) {
        console.error('OAuth error:', error);
    }
}
```

## API Endpoints

### Authentication Endpoints

- `GET /auth/oauth/google/authorize` - Initiate Google login
- `GET /auth/oauth/google/callback` - OAuth callback (handled automatically)
- `GET /auth/oauth/providers` - List connected OAuth providers
- `POST /auth/oauth/google/link` - Link Google to existing account
- `DELETE /auth/oauth/google/disconnect` - Disconnect Google account
- `POST /auth/oauth/switch-to-oauth/google` - Switch from password to OAuth

### User Flow

1. **New User with Google:**
   - Click "Login with Google"
   - Authorize on Google
   - Account created automatically
   - Redirected to onboarding

2. **Existing Email User:**
   - Click "Login with Google" 
   - If email matches, OAuth is auto-linked
   - User logged in normally

3. **Link Google to Existing Account:**
   - Login with password first
   - Go to settings
   - Click "Link Google Account"
   - Authorize on Google
   - Account linked

4. **Switch to OAuth Only:**
   - Must have password set
   - Verify password
   - Link Google account
   - Can now login with Google

## Security Features

- CSRF protection via state parameter
- Token encryption for storage
- Automatic token refresh
- Session-based authentication maintained
- Email verification from provider

## Troubleshooting

1. **"Invalid client" error:**
   - Check GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET
   - Ensure redirect URI matches exactly

2. **"Redirect URI mismatch":**
   - Add your callback URL to Google Console
   - Check BACKEND_URL in .env

3. **Session issues:**
   - Ensure SESSION_SECRET_KEY is set
   - Check cookie settings for production

## Testing

1. Start your backend: `python main.py`
2. Navigate to: `http://localhost:8000/auth/oauth/status`
3. Should show Google as configured
4. Test login flow from frontend