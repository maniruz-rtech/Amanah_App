#!/usr/bin/env python3
"""
Create initial admin user for Amanah platform.
Run this script once to set up the first admin account.

Usage:
    python create_admin.py
"""

import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.core.security import encrypt_field, hash_contact, hash_password
from app.db.base import generate_ulid


def hash_contact_info(value: str) -> str:
    """SHA-256 lookup hash for phone/email (same normalisation as the ORM model)."""
    return hash_contact(value)


async def create_admin_user():
    """Create the initial admin user with proper encryption."""
    
    print("=" * 60)
    print("Amanah Admin User Creation")
    print("=" * 60)
    print()
    
    # Get user input
    username = input("Enter admin username [admin]: ").strip() or "admin"
    password = input("Enter admin password [admin123]: ").strip() or "admin123"
    full_name = input("Enter full name [Admin User]: ").strip() or "Admin User"
    phone = input("Enter phone number [+1234567890]: ").strip() or "+1234567890"
    email = input("Enter email [admin@amanah.local]: ").strip() or "admin@amanah.local"
    
    print()
    print("Creating admin user...")
    print()
    
    # Create database connection
    engine = create_async_engine(str(settings.database_url), echo=False)
    
    try:
        async with engine.connect() as conn:
            # Check if user already exists
            result = await conn.execute(
                text("SELECT id FROM users WHERE username = :username"),
                {"username": username}
            )
            if result.fetchone():
                print(f"❌ Error: User '{username}' already exists!")
                return
            
            # Generate IDs
            org_id = generate_ulid("org_")
            region_id = generate_ulid("reg_")
            user_id = generate_ulid("usr_")
            role_id = generate_ulid("rol_")
            user_role_id = generate_ulid("ur_")
            
            # Encrypt sensitive fields
            phone_encrypted = encrypt_field(phone)
            email_encrypted = encrypt_field(email)
            full_name_encrypted = encrypt_field(full_name)
            phone_hash = hash_contact_info(phone)
            email_hash = hash_contact_info(email)
            password_hash = hash_password(password)
            
            # Create organization
            await conn.execute(
                text("""
                    INSERT INTO organizations (id, name, is_active)
                    VALUES (:id, :name, TRUE)
                """),
                {"id": org_id, "name": "Default Organization"}
            )
            
            # Create region
            await conn.execute(
                text("""
                    INSERT INTO regions (id, organization_id, name, timezone, is_active)
                    VALUES (:id, :org_id, :name, :tz, TRUE)
                """),
                {"id": region_id, "org_id": org_id, "name": "Default Region", "tz": "UTC"}
            )
            
            # Create admin user
            await conn.execute(
                text("""
                    INSERT INTO users (
                        id, organization_id, region_id, username, display_name,
                        full_name_encrypted, phone_encrypted, phone_hash,
                        email_encrypted, email_hash, password_hash,
                        status, is_active, is_verified, is_suspended, mfa_enabled,
                        failed_login_attempts
                    )
                    VALUES (
                        :id, :org_id, :region_id, :username, :display_name,
                        :full_name_enc, :phone, :phone_hash,
                        :email, :email_hash, :password_hash,
                        'active', TRUE, TRUE, FALSE, FALSE,
                        0
                    )
                """),
                {
                    "id": user_id,
                    "org_id": org_id,
                    "region_id": region_id,
                    "username": username,
                    "display_name": full_name,  # Use as display name
                    "full_name_enc": full_name_encrypted,
                    "phone": phone_encrypted,
                    "phone_hash": phone_hash,
                    "email": email_encrypted,
                    "email_hash": email_hash,
                    "password_hash": password_hash,
                }
            )
            
            # The RBAC layer (app/core/permissions.py) knows `super_admin` and
            # `regional_admin`; the bootstrap account must hold `super_admin` or every
            # admin endpoint answers 403. Upsert so re-running never collides.
            role_id = (
                await conn.execute(
                    text("""
                        INSERT INTO roles (id, name, description)
                        VALUES (:id, 'super_admin', 'System administrator with full access')
                        ON CONFLICT (name) DO UPDATE SET description = EXCLUDED.description
                        RETURNING id
                    """),
                    {"id": role_id},
                )
            ).scalar_one()

            # Assign role to user
            await conn.execute(
                text("""
                    INSERT INTO user_roles (id, user_id, role_id, assigned_by_id)
                    VALUES (:id, :user_id, :role_id, :assigned_by_id)
                """),
                {
                    "id": user_role_id,
                    "user_id": user_id,
                    "role_id": role_id,
                    "assigned_by_id": user_id,
                }
            )
            
            # Commit transaction
            await conn.commit()
            
            print("✅ Admin user created successfully!")
            print()
            print("=" * 60)
            print("Login Credentials:")
            print("=" * 60)
            print(f"  Username: {username}")
            print(f"  Password: {password}")
            print(f"  Full Name: {full_name}")
            print()
            print("You can now login at: http://localhost:3000/admin/login")
            print("=" * 60)
            
    except Exception as e:
        print(f"❌ Error creating admin user: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(create_admin_user())
