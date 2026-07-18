# Amazon Cognito authentication setup

Backend currently supports two authentication modes:

- `AUTH_PROVIDER=demo`: use local demo users from `backend/routes/auth.py`.
- `AUTH_PROVIDER=cognito`: use Amazon Cognito User Pool login and JWT verification.

## 1. Create a Cognito User Pool

In AWS Console:

1. Open Amazon Cognito.
2. Create a User Pool.
3. Choose username sign-in.
4. Create an app client.
5. Enable `ALLOW_USER_PASSWORD_AUTH` for the app client.
6. Create users for the application.

For admin users, add them to a Cognito group named `admin`, or change `COGNITO_ADMIN_GROUP`.

## 2. Configure backend environment

Copy `backend/.env.example` to `backend/.env`, then set:

```env
AUTH_PROVIDER=cognito
AWS_REGION=ap-southeast-1
COGNITO_USER_POOL_ID=ap-southeast-1_xxxxxxxx
COGNITO_CLIENT_ID=your-app-client-id
COGNITO_ADMIN_GROUP=admin
COGNITO_TOKEN_USE=access
COGNITO_AUTH_FLOW=USER_PASSWORD_AUTH
```

If the app client has a secret, also set:

```env
COGNITO_CLIENT_SECRET=your-app-client-secret
```

Keep the existing S3, DynamoDB, and Lambda variables in the same `.env` file.

## 3. Required IAM permission

The backend AWS credentials or EC2 instance role need this permission:

```json
{
  "Effect": "Allow",
  "Action": "cognito-idp:InitiateAuth",
  "Resource": "arn:aws:cognito-idp:ap-southeast-1:<account-id>:userpool/<user-pool-id>"
}
```

## 4. Login flow

The frontend still calls:

```http
POST /api/login
```

When Cognito is enabled, backend returns the Cognito access token as `token`. All protected APIs continue to use:

```http
Authorization: Bearer <token>
```

Backend verifies the token against Cognito JWKS and maps roles as follows:

- User in Cognito group `admin`: role is `admin`.
- Otherwise `custom:role` or `role` claim is used if present.
- Fallback role is `user`.
