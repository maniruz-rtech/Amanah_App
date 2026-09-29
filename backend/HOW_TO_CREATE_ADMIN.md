# How to Create Admin Users

## Quick Start

There's a Python script in the backend folder to create admin users:

```bash
cd ~/amanah/backend
source venv/bin/activate
python3 create_admin.py
```

Follow the prompts (or press Enter for defaults):
- **Username**: admin
- **Password**: admin123
- **Full Name**: Admin User  
- **Phone**: +1234567890
- **Email**: admin@amanah.local

## Login to Admin Panel

Once created, you can login at:

🔗 **http://localhost:3000/admin/login**

**Default Credentials:**
- Username: `admin`
- Password: `admin123`

## What the Script Does

1. Creates a default organization ("Default Organization")
2. Creates a default region ("Default Region" with UTC timezone)
3. Creates the admin user with:
   - Encrypted PII fields (phone, email, full name)
   - Hashed lookups for phone/email
   - Argon2id password hash
   - Active and verified status
4. Creates an "admin" role with full access
5. Assigns the admin role to the user

## Database Structure

The user is created in these tables:
- `organizations` - Default org
- `regions` - Default region  
- `users` - Admin user with encrypted PII
- `roles` - Admin role
- `user_roles` - Role assignment

## Security Features

✅ **Passwords**: Argon2id hashing (not bcrypt)  
✅ **PII**: AES-256-GCM encryption for phone, email, full name  
✅ **Lookups**: SHA-256 hashes for phone/email  
✅ **Verification**: User is pre-verified and active  
✅ **Roles**: Full admin permissions granted

## Troubleshooting

**Q: "User already exists"**  
A: The username is already taken. Use a different username or delete the existing user from the database.

**Q: "Database connection error"**  
A: Make sure PostgreSQL is running on port 5433:
```bash
sudo systemctl status postgresql
```

**Q: "Cannot encrypt"**  
A: Check that your `.env` file has `ENCRYPTION_KEY` set (32+ characters).

## Multiple Admins

You can run the script multiple times with different usernames to create multiple admin accounts.

---

*Last updated: 2026-04-06*
